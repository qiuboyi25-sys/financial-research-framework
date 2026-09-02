"""bt 组合回测适配器。"""
from __future__ import annotations

from typing import Mapping

import pandas as pd

from data_providers.contracts import validate_daily_bars
from portfolio import validate_weight_matrix


def to_bt_prices(bars: pd.DataFrame, price_field: str = "close") -> pd.DataFrame:
    """将标准长表转换为 bt 要求的 date × symbol 价格矩阵。"""
    normalized = validate_daily_bars(bars, (price_field,))
    prices = normalized.pivot(index="date", columns="symbol", values=price_field)
    prices = prices.sort_index().sort_index(axis=1)
    if prices.empty:
        raise ValueError("cannot build bt prices from empty bars")
    return prices


def build_monthly_weight_backtest(
    prices: pd.DataFrame,
    weights: Mapping[str, float],
    *,
    name: str = "monthly_weight_strategy",
    commissions=None,
):
    """使用 bt 原生 Algo 创建月度目标权重回测，不实现自有撮合逻辑。"""
    try:
        import bt
    except ImportError as exc:
        raise ImportError("install the 'backtest' extra to use bt") from exc

    clean_weights = {str(symbol): float(weight) for symbol, weight in weights.items() if weight > 0}
    if not clean_weights or abs(sum(clean_weights.values()) - 1.0) > 1e-8:
        raise ValueError("positive bt weights must sum to 1")
    missing = sorted(set(clean_weights) - set(prices.columns))
    if missing:
        raise ValueError(f"bt prices are missing weighted symbols: {missing}")

    strategy = bt.Strategy(
        name,
        [
            bt.algos.RunMonthly(run_on_first_date=True),
            bt.algos.SelectThese(list(clean_weights)),
            bt.algos.WeighSpecified(**clean_weights),
            bt.algos.Rebalance(),
        ],
    )
    kwargs = {"integer_positions": False}
    if commissions is not None:
        kwargs["commissions"] = commissions
    return bt.Backtest(strategy, prices.loc[:, list(clean_weights)], **kwargs)


def build_dynamic_weight_backtest(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    *,
    name: str = "dynamic_weight_strategy",
    commissions=None,
    execution_delay: int = 1,
):
    """使用 bt 原生 WeighTarget 回测按日期变化的目标权重。

    execution_delay=1 表示月末信号在下一可用价格日执行。
    """
    try:
        import bt
    except ImportError as exc:
        raise ImportError("install the 'backtest' extra to use bt") from exc

    weights = align_target_weights_to_prices(
        target_weights, prices.index, execution_delay=execution_delay
    )
    missing = sorted(set(weights.columns) - set(prices.columns))
    if missing:
        raise ValueError(f"bt prices are missing weighted symbols: {missing}")
    if weights.index.min() < prices.index.min() or weights.index.max() > prices.index.max():
        raise ValueError("target-weight dates must fall inside the price history")

    strategy = bt.Strategy(
        name,
        [
            bt.algos.RunOnDate(*weights.index.to_pydatetime()),
            bt.algos.SelectThese(list(weights.columns)),
            bt.algos.WeighTarget(weights),
            bt.algos.Rebalance(),
        ],
    )
    kwargs = {"integer_positions": False}
    if commissions is not None:
        kwargs["commissions"] = commissions
    return bt.Backtest(strategy, prices.loc[:, list(weights.columns)], **kwargs)


def align_target_weights_to_prices(
    target_weights: pd.DataFrame,
    price_dates: pd.DatetimeIndex,
    *,
    execution_delay: int = 1,
) -> pd.DataFrame:
    """把信号日期映射到同日或之后第 N 个可交易价格日。"""
    if execution_delay < 0:
        raise ValueError("execution_delay cannot be negative")
    weights = validate_weight_matrix(target_weights)
    dates = pd.DatetimeIndex(pd.to_datetime(price_dates)).normalize().sort_values().unique()
    if dates.empty:
        raise ValueError("price_dates cannot be empty")

    execution_dates = []
    for signal_date in weights.index:
        side = "left" if execution_delay == 0 else "right"
        position = int(dates.searchsorted(signal_date, side=side))
        if execution_delay > 1:
            position += execution_delay - 1
        if position >= len(dates):
            raise ValueError(f"no execution price date after signal date: {signal_date.date()}")
        execution_dates.append(dates[position])
    if len(set(execution_dates)) != len(execution_dates):
        raise ValueError("multiple signal dates map to the same execution date")
    result = weights.copy()
    result.index = pd.DatetimeIndex(execution_dates, name="execution_date")
    return result
