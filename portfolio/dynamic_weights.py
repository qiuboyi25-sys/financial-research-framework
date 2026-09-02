"""将月度资产信号转换为满足约束的目标权重矩阵。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AssetWeightRule:
    symbol: str
    central_weight: float
    adjustment: float

    def __post_init__(self) -> None:
        if self.central_weight < 0 or self.adjustment < 0:
            raise ValueError("weight rule values must be non-negative")
        if self.central_weight + self.adjustment > 1:
            raise ValueError("central weight plus adjustment cannot exceed 1")

    @property
    def lower_bound(self) -> float:
        return max(0.0, self.central_weight - self.adjustment)

    @property
    def upper_bound(self) -> float:
        return self.central_weight + self.adjustment


def build_dynamic_weights(
    signals: pd.DataFrame,
    rules: Sequence[AssetWeightRule],
    *,
    cash_symbol: str,
    cash_central_weight: float,
) -> pd.DataFrame:
    """按中枢加战术偏离生成权重；现金吸收剩余权重。

    当所有正向战术偏离超过现金可提供的空间时，仅按比例缩小正向偏离，
    保留负向信号释放的现金，不改变各资产的权重中枢。
    """
    if not 0 <= cash_central_weight <= 1:
        raise ValueError("cash_central_weight must be between 0 and 1")
    if cash_symbol in {rule.symbol for rule in rules}:
        raise ValueError("cash_symbol must not appear in tactical rules")
    if signals.columns.duplicated().any() or signals.index.duplicated().any():
        raise ValueError("signals must have unique dates and assets")

    expected = [rule.symbol for rule in rules]
    missing = [symbol for symbol in expected if symbol not in signals.columns]
    if missing:
        raise ValueError(f"signals are missing assets: {missing}")
    central_total = sum(rule.central_weight for rule in rules) + cash_central_weight
    if abs(central_total - 1.0) > 1e-10:
        raise ValueError("central asset and cash weights must sum to 1")

    clean_signals = signals.loc[:, expected].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    clean_signals = clean_signals.clip(-1.0, 1.0).sort_index()
    rows: list[dict[str, float]] = []
    for _, signal_row in clean_signals.iterrows():
        deltas = {
            rule.symbol: rule.adjustment * float(signal_row[rule.symbol]) for rule in rules
        }
        positive_total = sum(max(delta, 0.0) for delta in deltas.values())
        negative_total = sum(min(delta, 0.0) for delta in deltas.values())
        positive_capacity = cash_central_weight - negative_total
        scale = min(1.0, positive_capacity / positive_total) if positive_total > 0 else 1.0

        weights: dict[str, float] = {}
        for rule in rules:
            delta = deltas[rule.symbol]
            if delta > 0:
                delta *= scale
            weights[rule.symbol] = float(
                np.clip(rule.central_weight + delta, rule.lower_bound, rule.upper_bound)
            )
        weights[cash_symbol] = max(0.0, 1.0 - sum(weights.values()))
        rows.append(weights)

    result = pd.DataFrame(rows, index=clean_signals.index)
    result.index.name = signals.index.name or "rebalance_date"
    return validate_weight_matrix(result)


def validate_weight_matrix(weights: pd.DataFrame, *, tolerance: float = 1e-10) -> pd.DataFrame:
    if weights.empty:
        raise ValueError("weight matrix cannot be empty")
    result = weights.apply(pd.to_numeric, errors="raise").copy()
    result.index = pd.DatetimeIndex(pd.to_datetime(result.index)).normalize()
    result = result.sort_index()
    if result.index.has_duplicates or result.columns.duplicated().any():
        raise ValueError("weight matrix dates and symbols must be unique")
    if result.isna().any().any() or (result < -tolerance).any().any():
        raise ValueError("weight matrix must contain finite non-negative values")
    if not np.allclose(result.sum(axis=1).to_numpy(), 1.0, atol=tolerance, rtol=0):
        raise ValueError("each target-weight row must sum to 1")
    return result.clip(lower=0.0)
