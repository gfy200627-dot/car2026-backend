"""确定性随机数工具（与前端 src/mock/random.ts 同源的 mulberry32 实现）

用于种子数据与预测扰动：同一个 seed 每次生成同一份结果，保证可复现。
"""

import math

_MASK = 0xFFFFFFFF


def _imul(x: int, y: int) -> int:
    """32 位整数乘法（等价 Math.imul）"""
    return (x * y) & _MASK


def hash_string(s: str) -> int:
    """FNV-1a 变体，与前端 hashString 对齐"""
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = _imul(h, 16777619)
    return h


def mulberry32(seed: int):
    """返回 next() -> [0,1)"""
    state = seed & _MASK

    def nxt() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & _MASK
        t = state
        t = _imul(t ^ (t >> 15), t | 1)
        t ^= (t + _imul(t ^ (t >> 7), t | 61)) & _MASK
        return ((t ^ (t >> 14)) & _MASK) / 4294967296

    return nxt


class Rng:
    """与前端 createRng 等价：next/float/int/pick/bool"""

    def __init__(self, seed):
        self._next = mulberry32(seed if isinstance(seed, int) else hash_string(str(seed)))

    def next(self) -> float:
        return self._next()

    def float(self, lo: float, hi: float) -> float:
        return lo + self.next() * (hi - lo)

    def int(self, lo: int, hi: int) -> int:
        return math.floor(self.float(lo, hi + 1))

    def pick(self, arr):
        return arr[math.floor(self.next() * len(arr))]

    def bool(self, p: float = 0.5) -> bool:
        return self.next() < p


def round(value: float, digits: int = 2) -> float:
    """与前端 round 一致：四舍五入到指定小数位"""
    p = 10 ** digits
    return math.floor(value * p + 0.5) / p


def clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))
