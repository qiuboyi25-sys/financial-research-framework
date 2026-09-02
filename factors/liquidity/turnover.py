"""换手率因子。

输入为框架标准日行情长表，输出为可直接交给 ``factors.evaluation`` 的月频
截面面板。计算只使用调仓日及之前的数据，下一期收益单独向后对齐。
"""
from __future__ import annotations

import pandas as pd

FACTOR_NAME = "turnover_20d_mean"
FACTOR_DEFINITION = "月末时点向前20个交易日换手率的算术平均值"
FORWARD_RETURN_DEFINITION = "本月最后交易日收盘至下一月最后交易日收盘收益率"


def build_turnover_factor_panel(
    daily_bars: pd.DataFrame,
    *,
    window: int = 20,
    minimum_periods: int | None = None,
    data_source: str = "unknown",
    default_asset_class: str = "A股",
) -> pd.DataFrame:
    """构建月频换手率因子与下一期收益面板。

    Args:
        daily_bars: 至少含 date、symbol、close、turnover；asset_class 可选。
        window: 日换手率均值回看交易日数。
        minimum_periods: 最少有效观测数，默认与 window 相同。
        data_source: 写入缓存血缘的数据源名称。
        default_asset_class: 输入没有 asset_class 时使用的资产类别。

    Returns:
        每行对应一个月末和资产，包含因子值、前瞻收益及字段定义。
    """
    required = {"date", "symbol", "close", "turnover"}
    missing = sorted(required - set(daily_bars.columns))
    if missing:
        raise ValueError(f"turnover input is missing columns: {missing}")
    if window < 1:
        raise ValueError("window must be positive")
    required_periods = window if minimum_periods is None else minimum_periods
    if not 1 <= required_periods <= window:
        raise ValueError("minimum_periods must be between 1 and window")

    frame = daily_bars.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["turnover"] = pd.to_numeric(frame["turnover"], errors="coerce")
    if frame.duplicated(["date", "symbol"]).any():
        raise ValueError("turnover input contains duplicate date/symbol rows")
    if (frame["turnover"].dropna() < 0).any():
        raise ValueError("turnover cannot be negative")
    if "asset_class" not in frame:
        frame["asset_class"] = default_asset_class
    frame["asset_class"] = frame["asset_class"].fillna(default_asset_class).astype(str)
    frame = frame.sort_values(["symbol", "date"])

    # 每个证券独立滚动；因子时点只使用当日及历史换手率。
    frame[FACTOR_NAME] = (
        frame.groupby("symbol", sort=False)["turnover"]
        .rolling(window, min_periods=required_periods)
        .mean()
        .reset_index(level=0, drop=True)
    )
    frame["month"] = frame["date"].dt.to_period("M")
    month_end_rows = (
        frame.groupby(["symbol", "month"], sort=True)["date"].idxmax().to_numpy()
    )
    monthly = frame.loc[
        month_end_rows,
        ["date", "symbol", "asset_class", "close", "turnover", FACTOR_NAME],
    ].sort_values(["symbol", "date"])

    # 月末因子对应下一月月末收益，不把未来价格用于因子本身。
    monthly["fwd_ret"] = monthly.groupby("symbol", sort=False)["close"].shift(-1)
    monthly["fwd_ret"] = monthly["fwd_ret"] / monthly["close"] - 1.0
    monthly["factor_name"] = FACTOR_NAME
    monthly["definition"] = FACTOR_DEFINITION.replace("20", str(window), 1)
    monthly["data_source"] = data_source
    monthly["frequency"] = "monthly"
    monthly["forward_return_definition"] = FORWARD_RETURN_DEFINITION
    monthly["calculation_version"] = "1.0"
    return monthly.reset_index(drop=True)
