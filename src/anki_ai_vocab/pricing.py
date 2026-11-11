"""Local CNY cost estimates, without API calls or access to account balances.

Price snapshot checked on 2026-11-11:
https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
Use the published off-peak/peak range instead of guessing holiday discounts.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .cache import Cache


@dataclass(frozen=True)
class TokenPrice:
    """CNY per million tokens; official peak prices are twice off-peak prices."""

    cached_input: Decimal
    uncached_input: Decimal
    output: Decimal


FLASH_PRICE = TokenPrice(Decimal("0.02"), Decimal("1"), Decimal("4"))
PRICES = {
    "deepseek-flash": FLASH_PRICE,
    "deepseek-v4-flash": FLASH_PRICE,
    "deepseek-v4-flash-vision-exp": FLASH_PRICE,
    "deepseek-v4-pro": TokenPrice(Decimal("0.15"), Decimal("4.5"), Decimal("13.5")),
}


@dataclass(frozen=True)
class CostEstimate:
    minimum_cny: Decimal
    maximum_cny: Decimal
    requests: int
    unpriced_requests: int

    def display(self) -> str:
        if self.requests and self.unpriced_requests == self.requests:
            return (
                f"累计 API 花费：暂无法估算（{self.requests} 次请求，模型未配置价格）"
            )
        amount = f"¥{self.minimum_cny:.6f}"
        if self.minimum_cny != self.maximum_cny:
            amount += f"～¥{self.maximum_cny:.6f}"
        text = f"累计 API 花费（估算）：{amount} · {self.requests} 次请求"
        if self.unpriced_requests:
            text += f"（其中 {self.unpriced_requests} 次未计价）"
        return text


def estimate_cost(rows: list[dict[str, Any]]) -> CostEstimate:
    minimum = Decimal(0)
    requests = unpriced = 0
    for row in rows:
        requests += row["requests"]
        price = PRICES.get(row["model"])
        if price is None:
            unpriced += row["requests"]
            continue
        cached = row["cached_tokens"]
        uncached = row["prompt_tokens"] - cached
        minimum += (
            cached * price.cached_input
            + uncached * price.uncached_input
            + row["completion_tokens"] * price.output
        ) / Decimal(1_000_000)
    return CostEstimate(minimum, minimum * 2, requests, unpriced)


def read_cost(path: Path) -> CostEstimate:
    return estimate_cost(Cache.read_usage(path))
