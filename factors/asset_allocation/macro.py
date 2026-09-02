"""带发布日期约束的宏观趋势打分。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from data_providers.contracts import validate_macro_observations


@dataclass(frozen=True)
class MacroRule:
    asset: str
    indicator: str
    trend_months: int
    direction: int

    def __post_init__(self) -> None:
        if self.trend_months < 1:
            raise ValueError("trend_months must be positive")
        if self.direction not in {-1, 1}:
            raise ValueError("direction must be -1 or 1")


def build_macro_scores(
    observations: pd.DataFrame,
    rebalance_dates: pd.DatetimeIndex | Sequence[object],
    rules: Sequence[MacroRule],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """按每个调仓日当时已发布的数据计算资产宏观得分。

    返回资产平均得分矩阵及逐指标审计长表。修订值只有在其 available_at
    不晚于调仓日时才会参与计算。
    """
    data = validate_macro_observations(observations)
    dates = pd.DatetimeIndex(pd.to_datetime(list(rebalance_dates))).normalize().sort_values()
    if dates.has_duplicates:
        raise ValueError("rebalance_dates cannot contain duplicates")

    records: list[dict[str, object]] = []
    for date in dates:
        available = data[data["available_at"] <= date]
        for rule in rules:
            history = available[available["indicator"] == rule.indicator]
            if history.empty:
                score = np.nan
                raw_trend = np.nan
                latest_period = pd.NaT
            else:
                history = (
                    history.sort_values(["period_date", "available_at"])
                    .drop_duplicates("period_date", keep="last")
                    .sort_values("period_date")
                )
                values = history["value"].dropna()
                window = rule.trend_months
                if len(values) < window + 1:
                    score = np.nan
                    raw_trend = np.nan
                else:
                    current_mean = float(values.iloc[-window:].mean())
                    previous_mean = float(values.iloc[-window - 1 : -1].mean())
                    raw_trend = current_mean - previous_mean
                    score = float(np.sign(raw_trend) * rule.direction)
                latest_period = history["period_date"].max()
            records.append(
                {
                    "rebalance_date": date,
                    "asset": rule.asset,
                    "indicator": rule.indicator,
                    "latest_period": latest_period,
                    "trend_months": rule.trend_months,
                    "direction": rule.direction,
                    "raw_trend": raw_trend,
                    "score": score,
                }
            )

    audit = pd.DataFrame.from_records(records)
    if audit.empty:
        return pd.DataFrame(index=dates), audit
    scores = (
        audit.assign(effective_score=audit["score"].fillna(0.0))
        .groupby(["rebalance_date", "asset"])["effective_score"]
        .mean()
        .unstack("asset")
        .reindex(dates)
    )
    return scores, audit.sort_values(["rebalance_date", "asset", "indicator"]).reset_index(
        drop=True
    )
