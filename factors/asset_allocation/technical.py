"""大类资产月频技术指标。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _numeric_series(values: pd.Series, name: str) -> pd.Series:
    result = pd.to_numeric(values, errors="coerce").copy()
    result.index = pd.DatetimeIndex(pd.to_datetime(result.index)).normalize()
    result = result[~result.index.duplicated(keep="last")].sort_index()
    result.name = name
    return result


def _monthly_last(values: pd.Series) -> pd.Series:
    return values.resample("ME").last().dropna()


def _sign(values: pd.Series) -> pd.Series:
    return np.sign(values).where(values.notna()).astype(float)


def low_lag_trend(prices: pd.Series, alpha: float = 0.2) -> pd.Series:
    """计算低延迟趋势线（LLT）；alpha 为显式研究假设。"""
    if not 0 < alpha < 1:
        raise ValueError("LLT alpha must be between 0 and 1")
    source = _numeric_series(prices, "price")
    result = pd.Series(np.nan, index=source.index, dtype=float, name="llt")
    if len(source) < 3:
        return result
    result.iloc[:2] = source.iloc[:2]
    a2 = alpha * alpha
    for position in range(2, len(source)):
        current = source.iloc[position]
        previous = source.iloc[position - 1]
        before_previous = source.iloc[position - 2]
        if pd.isna(current) or pd.isna(previous) or pd.isna(before_previous):
            continue
        result.iloc[position] = (
            (alpha - a2 / 4) * current
            + a2 / 2 * previous
            - (alpha - 3 * a2 / 4) * before_previous
            + 2 * (1 - alpha) * result.iloc[position - 1]
            - (1 - alpha) ** 2 * result.iloc[position - 2]
        )
    return result


def relative_momentum_score(
    prices: pd.Series,
    *,
    recent_months: int,
    baseline_months: int,
) -> tuple[pd.Series, pd.Series]:
    """近期平均月收益减去更早月份平均月收益。"""
    if recent_months < 1 or baseline_months < 1:
        raise ValueError("momentum windows must be positive")
    monthly_return = _monthly_last(_numeric_series(prices, "price")).pct_change()
    recent = monthly_return.rolling(recent_months, min_periods=recent_months).mean()
    older = monthly_return.shift(recent_months).rolling(
        baseline_months, min_periods=baseline_months
    ).mean()
    raw = recent - older
    return raw, _sign(raw)


def llt_relative_momentum_score(
    prices: pd.Series,
    *,
    alpha: float = 0.2,
    recent_months: int = 2,
    baseline_months: int = 11,
) -> tuple[pd.Series, pd.Series]:
    monthly_llt = _monthly_last(low_lag_trend(prices, alpha=alpha))
    return relative_momentum_score(
        monthly_llt, recent_months=recent_months, baseline_months=baseline_months
    )


def mean_momentum_score(
    prices: pd.Series, *, months: int
) -> tuple[pd.Series, pd.Series]:
    if months < 1:
        raise ValueError("months must be positive")
    monthly_return = _monthly_last(_numeric_series(prices, "price")).pct_change()
    raw = monthly_return.rolling(months, min_periods=months).mean()
    return raw, _sign(raw)


def rolling_percentile_score(
    values: pd.Series,
    *,
    window_months: int = 60,
    min_periods: int | None = None,
) -> tuple[pd.Series, pd.Series]:
    """将滚动历史分位数映射为 -2 至 2；高值视为正向。"""
    monthly = _monthly_last(_numeric_series(values, "value"))
    required = min_periods if min_periods is not None else window_months

    def percentile(window: pd.Series) -> float:
        if window.isna().all():
            return np.nan
        return float(window.rank(pct=True).iloc[-1])

    raw = monthly.rolling(window_months, min_periods=required).apply(percentile, raw=False)
    score = pd.cut(
        raw,
        bins=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
        labels=[-2.0, -1.0, 0.0, 1.0, 2.0],
        include_lowest=True,
    ).astype(float)
    return raw, score


def flow_surprise_score(
    monthly_flow: pd.Series,
    *,
    baseline_months: int = 6,
) -> tuple[pd.Series, pd.Series]:
    """当月资金流减去此前 baseline_months 个月均值。"""
    if baseline_months < 1:
        raise ValueError("baseline_months must be positive")
    flow = _monthly_last(_numeric_series(monthly_flow, "flow"))
    baseline = flow.shift(1).rolling(baseline_months, min_periods=baseline_months).mean()
    raw = flow - baseline
    return raw, _sign(raw)
