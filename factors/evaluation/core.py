"""截面因子评价内核。

本模块只负责数据校验和指标计算，不负责取数、写文件或绘图。研究入口可以把
结果交给报告生成器，也可以直接用于筛选、组合和自动化测试。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

DEFAULT_METADATA_COLUMNS = frozenset(
    {
        "fwd_ret",
        "layer",
        "close",
        "stock_code",
        "order_book_id",
        "date",
        "symbol",
        "name",
        "full_name",
    }
)


@dataclass(frozen=True)
class FactorAnalysisResult:
    """一次因子评价的结构化结果。"""

    summary: pd.DataFrame
    ic_series: dict[str, pd.Series]
    long_short_returns: dict[str, pd.Series]
    long_short_nav: dict[str, pd.Series]
    periods_per_year: int


def normalize_factor_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """标准化为唯一、升序的 ``(date, asset_id)`` 二级索引面板。"""
    if panel.empty:
        raise ValueError("factor panel cannot be empty")
    frame = panel.copy()
    if isinstance(frame.index, pd.MultiIndex) and frame.index.nlevels == 2:
        dates = pd.to_datetime(frame.index.get_level_values(0), errors="raise")
        assets = frame.index.get_level_values(1).astype(str)
        frame.index = pd.MultiIndex.from_arrays(
            [dates, assets], names=["date", "asset_id"]
        )
    else:
        columns = {str(column).lower(): column for column in frame.columns}
        date_column = columns.get("date")
        asset_column = (
            columns.get("asset_id")
            or columns.get("order_book_id")
            or columns.get("asset")
            or columns.get("symbol")
            or columns.get("code")
        )
        if date_column is None or asset_column is None:
            raise ValueError(
                "factor panel must use a two-level (date, asset) index or "
                "contain date and asset_id/order_book_id/symbol columns"
            )
        frame[date_column] = pd.to_datetime(frame[date_column], errors="raise")
        frame[asset_column] = frame[asset_column].astype(str)
        frame = frame.set_index([date_column, asset_column])
        frame.index = frame.index.set_names(["date", "asset_id"])
    if frame.index.has_duplicates:
        duplicates = int(frame.index.duplicated(keep=False).sum())
        raise ValueError(f"factor panel contains {duplicates} duplicate date-asset rows")
    return frame.sort_index()


def infer_factor_columns(
    panel: pd.DataFrame,
    factors: Sequence[str] | None = None,
    *,
    metadata_columns: Sequence[str] = DEFAULT_METADATA_COLUMNS,
) -> list[str]:
    """校验显式因子列，或从数值列中排除元数据后自动识别。"""
    if factors is not None:
        selected = list(dict.fromkeys(factors))
        missing = sorted(set(selected) - set(panel.columns))
        if missing:
            raise KeyError(f"factor columns not found: {missing}")
    else:
        metadata = set(metadata_columns)
        selected = [
            str(column)
            for column in panel.columns
            if column not in metadata and pd.api.types.is_numeric_dtype(panel[column])
        ]
    if not selected:
        raise ValueError("no numeric factor columns found")
    non_numeric = [
        factor
        for factor in selected
        if not pd.api.types.is_numeric_dtype(panel[factor])
    ]
    if non_numeric:
        raise TypeError(f"factor columns must be numeric: {non_numeric}")
    return selected


def _periods_per_year(dates: pd.DatetimeIndex) -> int:
    unique = dates.unique().sort_values()
    if len(unique) < 2:
        return 12
    median_days = float(np.median(np.diff(unique.asi8)) / 86_400_000_000_000)
    if median_days <= 2:
        return 252
    if median_days <= 10:
        return 52
    if median_days <= 45:
        return 12
    if median_days <= 100:
        return 4
    return 1


def _ic_by_date(
    panel: pd.DataFrame,
    factor: str,
    return_column: str,
    method: str,
    minimum_assets: int,
) -> pd.Series:
    def correlation(cross_section: pd.DataFrame) -> float:
        valid = cross_section[[factor, return_column]].dropna()
        if len(valid) < minimum_assets:
            return np.nan
        if valid[factor].nunique() < 2 or valid[return_column].nunique() < 2:
            return np.nan
        return float(valid[factor].corr(valid[return_column], method=method))

    result = panel.groupby(level="date", sort=True).apply(correlation)
    result.name = factor
    return result


def _long_short_by_date(
    panel: pd.DataFrame,
    factor: str,
    return_column: str,
    groups: int,
    minimum_assets: int,
) -> pd.Series:
    required = max(minimum_assets, groups * 2)

    def group_spread(cross_section: pd.DataFrame) -> float:
        valid = cross_section[[factor, return_column]].dropna()
        if len(valid) < required or valid[factor].nunique() < groups:
            return np.nan
        buckets = pd.qcut(
            valid[factor].rank(method="first"), groups, labels=False
        )
        high = valid.loc[buckets == groups - 1, return_column].mean()
        low = valid.loc[buckets == 0, return_column].mean()
        return float(high - low)

    result = panel.groupby(level="date", sort=True).apply(group_spread)
    result.name = factor
    return result


def _compound_annual_return(returns: pd.Series, periods_per_year: int) -> float:
    valid = returns.dropna()
    if valid.empty or (valid <= -1).any():
        return np.nan
    growth = float((1.0 + valid).prod())
    return growth ** (periods_per_year / len(valid)) - 1.0


def analyze_factors(
    panel: pd.DataFrame,
    factors: Sequence[str] | None = None,
    *,
    fwd_ret_col: str = "fwd_ret",
    layer_col: str | None = "layer",
    n_groups: int = 5,
    ic_method: str = "both",
    minimum_assets: int = 5,
    periods_per_year: int | None = None,
) -> FactorAnalysisResult:
    """计算全样本及可选分层的 IC、RankIC、覆盖率和分组多空收益。"""
    frame = normalize_factor_panel(panel)
    if fwd_ret_col not in frame.columns:
        raise KeyError(f"forward-return column not found: {fwd_ret_col}")
    if not pd.api.types.is_numeric_dtype(frame[fwd_ret_col]):
        raise TypeError(f"{fwd_ret_col} must be numeric")
    if n_groups < 2:
        raise ValueError("n_groups must be at least 2")
    if minimum_assets < 2:
        raise ValueError("minimum_assets must be at least 2")
    methods = {
        "pearson": ("pearson",),
        "spearman": ("spearman",),
        "both": ("pearson", "spearman"),
    }.get(ic_method)
    if methods is None:
        raise ValueError("ic_method must be 'pearson', 'spearman', or 'both'")

    selected = infer_factor_columns(frame, factors)
    annual_periods = periods_per_year or _periods_per_year(
        pd.DatetimeIndex(frame.index.get_level_values("date"))
    )
    if annual_periods < 1:
        raise ValueError("periods_per_year must be positive")

    scopes: list[tuple[str, pd.DataFrame]] = [("ALL", frame)]
    if layer_col and layer_col in frame.columns:
        layer_values = frame[layer_col].dropna().astype(str)
        for layer in sorted(layer_values.unique()):
            scopes.append((layer, frame[frame[layer_col].astype(str) == layer]))

    rows: list[dict[str, object]] = []
    ic_series: dict[str, pd.Series] = {}
    long_short_returns: dict[str, pd.Series] = {}
    long_short_nav: dict[str, pd.Series] = {}
    for scope, scoped in scopes:
        for factor in selected:
            valid_observations = scoped[[factor, fwd_ret_col]].dropna()
            row: dict[str, object] = {
                "layer": scope,
                "factor": factor,
                "coverage": len(valid_observations) / len(scoped),
            }
            period_counts: list[int] = []
            for method in methods:
                series = _ic_by_date(
                    scoped, factor, fwd_ret_col, method, minimum_assets
                )
                ic_series[f"{scope}|{method}|{factor}"] = series
                valid = series.dropna()
                mean = float(valid.mean()) if not valid.empty else np.nan
                std = float(valid.std(ddof=1)) if len(valid) > 1 else np.nan
                prefix = "ic" if method == "pearson" else "rank_ic"
                row[f"{prefix}_mean"] = mean
                row[f"{prefix}_std"] = std
                row[f"{prefix}ir"] = mean / std if std > 0 else np.nan
                row[f"{prefix}ir_ann"] = (
                    mean / std * np.sqrt(annual_periods) if std > 0 else np.nan
                )
                row[f"{prefix}_positive_ratio"] = (
                    float((valid > 0).mean()) if not valid.empty else np.nan
                )
                period_counts.append(len(valid))
            row["n_periods"] = min(period_counts, default=0)

            spread = _long_short_by_date(
                scoped, factor, fwd_ret_col, n_groups, minimum_assets
            )
            long_short_returns[f"{scope}|{factor}"] = spread
            long_short_nav[f"{scope}|{factor}"] = (1.0 + spread.dropna()).cumprod()
            row["long_short_ann_return"] = _compound_annual_return(
                spread, annual_periods
            )
            rows.append(row)

    summary = pd.DataFrame(rows)
    rank_column = "icir_ann" if "icir_ann" in summary else "rank_icir_ann"
    summary = (
        summary.assign(_rank=summary[rank_column].abs())
        .sort_values(["layer", "_rank", "factor"], ascending=[True, False, True])
        .drop(columns="_rank")
        .reset_index(drop=True)
    )
    return FactorAnalysisResult(
        summary=summary,
        ic_series=ic_series,
        long_short_returns=long_short_returns,
        long_short_nav=long_short_nav,
        periods_per_year=annual_periods,
    )
