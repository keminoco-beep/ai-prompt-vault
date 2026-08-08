"""v3.2 测试：西班牙语(es) / 日语(ja) 界面语言完整性。

覆盖：
1. es/ja 翻译表 key 集合 == en 表 key 集合（无缺无多，缺 key 会回退中文属缺陷）
2. LANGUAGES 含 4 种语言（zh/en/es/ja），设置对话框可自动填充
3. 抽检关键 key（设置/删除/我的作品/界面语言）在 es/ja 非空且非中文原文
4. 模拟切换语言：i18n.set_language 直接切（无需重启），t() 返回对应语言

运行：python tests/test_v32_langs.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import i18n

FAIL = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {detail}")
        FAIL.append(name)


def main():
    print("[v3.2] 多语言完整性：es / ja")

    # ---------- 1. key 集合一致性 ----------
    print("\n[1] es/ja 表 key 集合 == en 表 key 集合")
    en_keys = set(i18n._LANG_TABLES["en"].keys())
    es_keys = set(i18n._LANG_TABLES["es"].keys())
    ja_keys = set(i18n._LANG_TABLES["ja"].keys())

    check("es 无缺失 key", en_keys - es_keys == set(),
          f"缺失 {sorted(en_keys - es_keys)[:10]}")
    check("es 无多余 key", es_keys - en_keys == set(),
          f"多余 {sorted(es_keys - en_keys)[:10]}")
    check("ja 无缺失 key", en_keys - ja_keys == set(),
          f"缺失 {sorted(en_keys - ja_keys)[:10]}")
    check("ja 无多余 key", ja_keys - en_keys == set(),
          f"多余 {sorted(ja_keys - en_keys)[:10]}")
    check(f"es 覆盖 {len(es_keys)} 个 key / ja 覆盖 {len(ja_keys)} 个 key",
          len(es_keys) == len(en_keys) == len(ja_keys))

    # 占位符一致性：{n}/{err}/{name}... 一个都不能丢（丢了 tr_format 会回退中文）
    import re
    ph = re.compile(r"\{[^}]+\}")
    ph_bad = []
    for lang in ("es", "ja"):
        tab = i18n._LANG_TABLES[lang]
        for k, en_v in i18n._LANG_TABLES["en"].items():
            if set(ph.findall(en_v)) != set(ph.findall(tab.get(k, ""))):
                ph_bad.append(f"{lang}:{k}")
    check("es/ja 全部 {占位符} 均保留", not ph_bad, ph_bad[:10])

    # 翻译值本身不能是中文原文（否则等于没翻译）。
    # 注：日语允许汉字（Kanji，如 設定/削除），西语为拉丁字母语言不得含中文。
    # 西语：严格检查——翻译值不得含 CJK 字符（漏翻/错填中文即缺陷）
    es_cjk = [k for k, v in i18n._LANG_TABLES["es"].items()
              if any(0x4E00 <= ord(c) <= 0x9FFF for c in v)]
    check("es 翻译值无中文字符", not es_cjk, f"含中文的 key: {es_cjk[:10]}")
    # 日语：仅检查"逐字照抄中文 key 且无假名"的明显漏翻。
    # 放行两类合法情形：① 全语言通用技术词（CFG/VAE/ControlNet，en 值也等于 key）
    #                   ② 中日语共通的汉字词（保存/分/秒）
    _JA_SHARED = {"保存", "分", "秒"}
    ja_suspect = [k for k, v in i18n._LANG_TABLES["ja"].items()
                  if v == k and i18n._LANG_TABLES["en"].get(k) != k
                  and k not in _JA_SHARED]
    check("ja 无逐字照抄中文 key 的漏翻", not ja_suspect, f"疑似漏翻: {ja_suspect[:10]}")

    # ---------- 2. LANGUAGES ----------
    print("\n[2] LANGUAGES 含 4 种语言")
    check("LANGUAGES 长度 == 4", len(i18n.LANGUAGES) == 4, repr(i18n.LANGUAGES))
    check("LANGUAGES 含 zh/en/es/ja",
          {"zh", "en", "es", "ja"} <= set(i18n.LANGUAGES.keys()))
    check("语言显示名正确",
          i18n.LANGUAGES.get("es") == "Español" and i18n.LANGUAGES.get("ja") == "日本語",
          repr(i18n.LANGUAGES))

    # ---------- 3. 抽检关键 key ----------
    print("\n[3] 抽检关键 key（设置/删除/我的作品/界面语言）")
    SPOT = {
        "设置": {"es": "Ajustes", "ja": "設定"},
        "删除": {"es": "Eliminar", "ja": "削除"},
        "我的作品": {"es": "Mis Obras", "ja": "マイ作品"},
        "界面语言": {"es": "Idioma de la interfaz", "ja": "表示言語"},
    }
    for key, expect in SPOT.items():
        for lang, exp in expect.items():
            val = i18n._LANG_TABLES[lang].get(key, "")
            check(f"{lang}「{key}」= {val!r}",
                  val and val != key and val == exp, f"期望 {exp!r}")

    # ---------- 4. 切换语言不重启验证 ----------
    print("\n[4] i18n.set_language 直接切换，t() 返回对应语言")
    tmp = Path(tempfile.mkdtemp()) / "settings.json"
    i18n.init(tmp, "zh")
    assert i18n.current_lang() == "zh"

    check("set_language(es) 返回 True", i18n.set_language("es"))
    check("t(设置) 返回西语", i18n.t("设置") == "Ajustes", repr(i18n.t("设置")))
    check("t(我的作品) 返回西语", i18n.t("我的作品") == "Mis Obras",
          repr(i18n.t("我的作品")))
    check("rev(Ajustes) 反查回中文 key", i18n.rev("Ajustes") == "设置",
          repr(i18n.rev("Ajustes")))

    check("set_language(ja) 返回 True", i18n.set_language("ja"))
    check("t(设置) 返回日语", i18n.t("设置") == "設定", repr(i18n.t("设置")))
    check("t(我的作品) 返回日语", i18n.t("我的作品") == "マイ作品",
          repr(i18n.t("我的作品")))
    check("t(界面语言) 返回日语", i18n.t("界面语言") == "表示言語",
          repr(i18n.t("界面语言")))

    # 带占位符 key：翻译后格式化仍可用（tr_format）
    i18n.set_language("es")
    check("tr_format(已保存 {n} 条 ✓) 西语含数字",
          i18n.tr_format("已保存 {n} 条 ✓", n=3) == "Guardados 3 elemento(s) ✓",
          repr(i18n.tr_format("已保存 {n} 条 ✓", n=3)))
    i18n.set_language("ja")
    check("tr_format(图片下载失败（{err}）) 日语含占位符替换",
          i18n.tr_format("图片下载失败（{err}）", err="timeout")
          == "画像のダウンロードに失敗（timeout）",
          repr(i18n.tr_format("图片下载失败（{err}）", err="timeout")))

    # 恢复默认语言，避免影响后续测试
    i18n.init(tmp, "zh")

    print()
    print("v3.2 多语言完整性", "全部通过 ✓" if not FAIL else f"存在失败 ✗ {FAIL}")
    sys.exit(0 if not FAIL else 1)


if __name__ == "__main__":
    main()
