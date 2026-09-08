"""通用工具：时间序列构建等"""

from datetime import date, timedelta
from typing import List

from app.core.config import settings


def build_months(count: int, end_year: int | None = None, end_month: int | None = None) -> List[str]:
    """生成最近 count 个月份（对齐 Mock 的 MONTHS 口径）"""
    y = end_year or settings.LATEST_YEAR
    m = end_month or settings.LATEST_MONTH
    out = []
    for _ in range(count):
        out.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))


def recent_months(n: int = 12) -> List[str]:
    """取最近 n 个月"""
    return build_months(n)


def to_month_str(d: date) -> str:
    """Date → YYYY-MM"""
    return d.strftime("%Y-%m")


def parse_month(s: str) -> date:
    """YYYY-MM → Date(当月 1 日)"""
    return date(int(s[:4]), int(s[5:7]), 1)