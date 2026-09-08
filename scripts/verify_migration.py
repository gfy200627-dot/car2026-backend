"""Alembic 深度验证：
1. 全新临时库执行 alembic upgrade head
2. 逐表比对迁移结果与 ORM metadata（表集合 / 列名与类型 / 主键 / 外键 / 索引）
3. alembic downgrade base 可回滚
只读验证，不触碰任何现有数据库。
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect  # noqa: E402

from app.database.session import Base  # noqa: E402

tmp = Path(tempfile.mkdtemp()) / "alembic_verify.db"
env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp.as_posix()}"}

r = subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    cwd=str(ROOT), env=env, capture_output=True, text=True,
)
if r.returncode != 0:
    print(r.stdout)
    print(r.stderr)
    raise SystemExit("FAIL: alembic upgrade head 执行失败")
print("✅ alembic upgrade head 执行成功")

# 让本进程按迁移库连接（重新以 URL 建引擎）
from sqlalchemy import create_engine  # noqa: E402

import app.models  # noqa: E402,F401  触发全部模型注册进 Base.metadata

engine = create_engine(f"sqlite:///{tmp.as_posix()}")
insp = inspect(engine)
metadata = Base.metadata

errors = []

expected_tables = set(metadata.tables.keys())
actual_tables = set(insp.get_table_names()) - {"alembic_version"}
missing = expected_tables - actual_tables
extra = actual_tables - expected_tables
if missing:
    errors.append(f"缺表: {sorted(missing)}")
if extra:
    errors.append(f"多表: {sorted(extra)}")
print(f"✅ 表数量: {len(actual_tables)}（metadata 期望 {len(expected_tables)}）")

TYPE_ALIASES = {"INTEGER": {"INTEGER", "BIGINT", "SMALLINT", "INT"}, "VARCHAR": {"VARCHAR"}}


def norm_type(t: str) -> str:
    return t.split("(")[0].upper()


for table in sorted(expected_tables & actual_tables):
    md_cols = metadata.tables[table].columns
    db_cols = {c["name"]: c for c in insp.get_columns(table)}
    for col in md_cols:
        if col.name not in db_cols:
            errors.append(f"{table}.{col.name} 缺列")
            continue
        db_type = norm_type(str(db_cols[col.name]["type"]))
        md_type = norm_type(col.type.compile(engine.dialect))
        if db_type != md_type:
            errors.append(f"{table}.{col.name} 类型不符: 库={db_type} 模型={md_type}")
    for extra_col in set(db_cols) - {c.name for c in md_cols}:
        errors.append(f"{table}.{extra_col} 多余列")

    db_pk = {c["name"] for c in insp.get_columns(table) if c.get("primary_key")}
    md_pk = {c.name for c in md_cols if c.primary_key}
    if db_pk != md_pk:
        errors.append(f"{table} 主键不符: 库={db_pk} 模型={md_pk}")

    db_fk = {(tuple(fk["constrained_columns"]), tuple(fk["referred_columns"]), fk["referred_table"])
             for fk in insp.get_foreign_keys(table)}
    md_fk = set()
    for fk in metadata.tables[table].foreign_keys:
        parent = (fk.parent.name,)
        child = (fk.column.name,)
        referred_table = fk.column.table.name
        md_fk.add((parent, child, referred_table))
    if db_fk != md_fk:
        errors.append(f"{table} 外键不符: 库={db_fk} 模型={md_fk}")

    db_idx = {i["name"]: set(i["column_names"]) for i in insp.get_indexes(table)}
    md_idx = {i.name: {c.name for c in i.columns} for i in metadata.tables[table].indexes}
    for name, cols in md_idx.items():
        if name not in db_idx:
            errors.append(f"{table} 缺索引 {name}")
        elif db_idx[name] != cols:
            errors.append(f"{table} 索引 {name} 列不符")
    for name in db_idx:
        if name not in md_idx and not name.startswith("sqlite_autoindex"):
            errors.append(f"{table} 多余索引 {name}")

r2 = subprocess.run(
    [sys.executable, "-m", "alembic", "downgrade", "base"],
    cwd=str(ROOT), env=env, capture_output=True, text=True,
)
if r2.returncode != 0:
    errors.append(f"downgrade base 失败: {r2.stderr[-500:]}")
else:
    print("✅ alembic downgrade base 回滚成功")

print()
if errors:
    print("❌ 结构差异：")
    for e in errors:
        print("  -", e)
    raise SystemExit(1)
print(f"🎉 迁移结构与 ORM 模型完全一致（{len(actual_tables)} 张表，列/主键/外键/索引逐项核对通过）")
