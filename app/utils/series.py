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


def prev_year_month(month: str) -> str:
    """2026-06 → 2025-06（上一年同月）"""
    return f"{int(month[:4]) - 1}-{month[5:7]}"


def prev_month(month: str) -> str:
    """2026-01 → 2025-12（日历上一月）"""
    y, m = int(month[:4]), int(month[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def calc_yoy(monthly: dict[str, float], window: list[str]) -> float:
    """同比：仅当上一年同月在 monthly 中真实存在时才计入比较，避免用缺失月当 0"""
    cur = prev = 0.0
    for m in window:
        pm = prev_year_month(m)
        if pm in monthly:
            cur += monthly.get(m, 0) or 0
            prev += monthly[pm] or 0
    return round((cur - prev) / prev * 100, 1) if prev else 0.0