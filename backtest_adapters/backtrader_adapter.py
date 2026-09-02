"""Backtrader Pandas Data Feed 适配器。"""
from __future__ import annotations

from typing import Dict

import pandas as pd

from data_providers.contracts import CORE_BAR_FIELDS, validate_daily_bars


def to_backtrader_frames(bars: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """按证券拆分为 Backtrader PandasData 所需的 OHLCV 表。"""
    normalized = validate_daily_bars(bars, CORE_BAR_FIELDS)
    frames: Dict[str, pd.DataFrame] = {}
    for symbol, group in normalized.groupby("symbol", sort=True):
        frame = group.set_index("date").loc[:, list(CORE_BAR_FIELDS)].sort_index()
        frame["openinterest"] = 0.0
        frames[str(symbol)] = frame
    return frames


def to_backtrader_feeds(bars: pd.DataFrame):
    """创建按证券命名的 Backtrader PandasData；策略和 Cerebro 由调用方负责。"""
    try:
        import backtrader as bt
    except ImportError as exc:
        raise ImportError("install the 'backtest' extra to use Backtrader") from exc

    return {
        symbol: bt.feeds.PandasData(dataname=frame, name=symbol)
        for symbol, frame in to_backtrader_frames(bars).items()
    }
