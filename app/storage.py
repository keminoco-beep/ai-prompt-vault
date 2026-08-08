"""SQLite 存储引擎（v3.0 数据层）。

设计目标：DataStore 对外 API 完全不变，内部从 JSON 切换为 SQLite。
- 首次启动时若存在旧版 data.json 自动迁移（保留备份 data.json.bak）
- settings 仍走 settings.json（i18n/API Key 加密依赖该文件），本引擎只管 records + groups
- 每次操作独立连接（connect-per-operation）：数据量小开销可忽略，
  且不残留文件锁（避免 Windows 下临时目录删除失败）
"""
import json
import shutil
import sqlite3
from contextlib import closing
import time
from pathlib import Path


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class SqliteStore:
    """records + groups 的 SQLite 持久化。"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.db_path = self.root / "library.db"
        self.json_path = self.root / "data.json"
        self._init_schema()
        self._migrate_if_needed()

    def _conn(self) -> sqlite3.Connection:
        # 每次操作独立连接（connect-per-operation）：不残留文件锁。
        # synchronous=OFF：索引写入内存同步（崩溃最多丢最后几条索引，
        # 图片/视频文件本身安全）；避免每次事务 fsync 拖慢批量保存。
        c = sqlite3.connect(str(self.db_path), check_same_thread=True,
                            timeout=10)
        c.execute("PRAGMA synchronous=OFF")
        return c

    # ---------- schema ----------
    def _init_schema(self):
        with closing(self._conn()) as c, c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS records ("
                " id TEXT PRIMARY KEY,"
                " data TEXT NOT NULL,"
                " created_at TEXT DEFAULT '',"
                " updated_at TEXT DEFAULT '')")
            c.execute(
                "CREATE TABLE IF NOT EXISTS groups (name TEXT PRIMARY KEY)")

    def _migrate_if_needed(self):
        """旧版 data.json → SQLite 一次性迁移（成功后备份 json）。

        v3.4 修复：**仅当 SQLite records 表为空时执行迁移**。
        旧实现只要 data.json 存在就每次启动全量 upsert，而 data.json 是迁移源、
        从不删除——用户在 SQLite 里删除的记录（查重清理等）会在下次启动被
        data.json 里的旧索引「复活」（幽灵记录）。加空表守卫后：
        - 首次转换（SQLite 空 + data.json 有数据）→ 正常迁移
        - 已迁移并投入使用（SQLite 非空）→ 跳过，SQLite 为权威，删除持久生效
        """
        if not self.json_path.exists():
            return
        try:
            with closing(self._conn()) as c:
                cnt = c.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            if cnt > 0:
                return   # 已迁移过：SQLite 是权威，data.json 仅历史索引，不再回灌
            data = json.loads(self.json_path.read_text(encoding="utf-8"))
            recs = data.get("records", []) if isinstance(data, dict) else data
            groups = data.get("groups", []) if isinstance(data, dict) else []
            with closing(self._conn()) as c, c:
                for r in recs:
                    if isinstance(r, dict) and r.get("id"):
                        self._upsert_record(c, r)
                for g in groups:
                    if isinstance(g, str) and g.strip():
                        c.execute("INSERT OR IGNORE INTO groups(name) VALUES (?)", (g,))
            # 迁移成功备份 json
            try:
                shutil.copy2(self.json_path, self.json_path.with_suffix(".json.bak"))
            except Exception:
                pass
        except Exception:
            pass  # json 损坏：保持 SQLite 空库，不影响使用

    # ---------- records ----------
    @staticmethod
    def _upsert_record(c, rec: dict):
        rec = dict(rec)
        rid = rec.get("id") or ""
        if not rid:
            return
        rec["id"] = rid
        created = rec.get("created_at") or _now()
        updated = rec.get("updated_at") or ""
        c.execute(
            "INSERT INTO records(id, data, created_at, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (rid, json.dumps(rec, ensure_ascii=False), created, updated))

    def load_records(self) -> list:
        try:
            with closing(self._conn()) as c, c:
                rows = c.execute("SELECT data FROM records").fetchall()
            return [json.loads(r[0]) for r in rows if r[0]]
        except Exception:
            return []

    def save_records(self, records: list):
        """全量替换（事务）。数据量不大时简单可靠。"""
        with closing(self._conn()) as c, c:
            c.execute("DELETE FROM records")
            for r in records:
                if isinstance(r, dict) and r.get("id"):
                    self._upsert_record(c, r)

    def upsert_record(self, rec: dict):
        with closing(self._conn()) as c, c:
            self._upsert_record(c, rec)

    def remove_record(self, rid: str):
        with closing(self._conn()) as c, c:
            c.execute("DELETE FROM records WHERE id=?", (rid,))

    # ---------- groups ----------
    def load_groups(self) -> list:
        try:
            with closing(self._conn()) as c, c:
                rows = c.execute("SELECT name FROM groups ORDER BY name").fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def save_groups(self, groups: list):
        with closing(self._conn()) as c, c:
            c.execute("DELETE FROM groups")
            for g in groups:
                if isinstance(g, str) and g.strip():
                    c.execute("INSERT OR IGNORE INTO groups(name) VALUES (?)", (g,))

    def close(self):
        pass  # connect-per-operation：无持久连接，无需 close