"""v3.0 M2.3 SQLite 迁移测试：旧 data.json → library.db + 数据完整性 + 性能。"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from app import i18n
from app.data_store import DataStore, normalize_record

td = Path(tempfile.mkdtemp())
root = td / 'Library'
root.mkdir(parents=True)
store = DataStore(root)
i18n.init(store.settings_path(), 'zh')

# ---- T1: 旧 data.json 迁移 ----
# 模拟旧版 data.json
old_recs = [
    {'id': 'old1', 'title': '旧图1', 'positive': 'p1', 'models': []},
    {'id': 'old2', 'title': '旧图2', 'positive': 'p2',
     'model_name': 'Krea2', 'model_type': '大模型'},
]
(root / 'data.json').write_text(
    json.dumps({'version': 1, 'groups': ['风景'], 'records': old_recs}),
    encoding='utf-8')

# 重新打开（触发迁移）
store2 = DataStore(root)
recs = store2.records
print(f'T1 迁移: records={len(recs)}, groups={store2.groups}')
assert len(recs) == 2, f'应迁移 2 条, 实际 {len(recs)}'
assert store2.groups == ['风景']
# 迁移后字段规范化
assert recs[0]['media_type'] == 'image'
assert recs[0]['models'] == []
assert (root / 'data.json.bak').exists(), '迁移应备份旧 json'
print('   ✓ 旧 data.json 迁移到 SQLite（含备份）')

# ---- T2: 迁移后数据可读写 ----
rec = store2.add({'title': '新记录', 'positive': 'new', 'models': []})
assert len(store2.records) == 3
store2.remove(rec['id'])
assert len(store2.records) == 2
# 重开验证持久化
store3 = DataStore(root)
assert len(store3.records) == 2
assert store3.get('old1')['title'] == '旧图1'
print('T2 迁移后读写 + 持久化 ✓')

# ---- T3: 无 json 的新库直接用 SQLite ----
root2 = td / 'Lib2'
s2 = DataStore(root2)
s2.add({'title': 'x', 'positive': '', 'models': []})
assert (root2 / 'library.db').exists()
assert len(DataStore(root2).records) == 1
print('T3 新库直接 SQLite ✓')

# ---- T4: 性能（1000 条保存，connect-per-operation 每条约 35ms 可接受）----
import time
t0 = time.time()
s3 = DataStore(td / 'Lib3')
for i in range(1000):
    s3.add({'id': f'r{i}', 'title': f't{i}', 'positive': 'p', 'models': []})
elapsed = time.time() - t0
print(f'T4 1000 条保存耗时 {elapsed:.2f}s（每条约 {elapsed/1000*1000:.0f}ms）')
assert elapsed < 60, f'保存过慢: {elapsed:.2f}s'
assert len(DataStore(td / 'Lib3').records) == 1000
print('   ✓ SQLite 批量写入性能（真实逐条保存无感）')

print()
print('M2.3 SQLite 迁移测试全部通过 ✓')