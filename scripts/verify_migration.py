"""验证 alembic upgrade head 后的库结构完整（与 Base.metadata 一致）"""

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB = ROOT / "_alembic_up.db"
con = sqlite3.connect(DB)
tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
con.close()

from app.database.session import Base  # noqa: E402

expected = set(Base.metadata.tables.keys())
missing = expected - tables
print("migration tables:", len(tables - {"alembic_version"}))
print("missing vs models:", missing or "无")
assert not missing, f"缺少表: {missing}"
print("✅ alembic upgrade head 建表完整")
