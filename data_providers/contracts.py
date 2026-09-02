"""Provider 统一契约与标准数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

import pandas as pd

CORE_BAR_FIELDS = ("open", "high", "low", "close", "volume")
BAR_KEY_COLUMNS = ("date", "symbol")
MACRO_KEY_COLUMNS = ("period_date", "available_at", "indicator")


class MarketDataProvider(Protocol):
    provider_name: str

    def fetch_trading_dates(
        self, start_date: str, end_date: str, *, force_refresh: bool = False
    ) -> pd.DataFrame: ...

    def fetch_daily_bars(
        self,
        symbols: str | Sequence[str],
        start_date: str,
        end_date: str,
        fields: Sequence[str] | None = None,
        *,
        adjust: str = "none",
        force_refresh: bool = False,
    ) -> pd.DataFrame: ...


class DatasetProvider(Protocol):
    provider_name: str

    def fetch_dataset(self, dataset: str, **kwargs: Any) -> pd.DataFrame: ...


@dataclass(frozen=True)
class DateCoverageReport:
    """基于显式交易日历的日期覆盖审计结果。"""

    summary: pd.DataFrame
    missing_keys: pd.DataFrame

    @property
    def complete(self) -> bool:
        return self.missing_keys.empty


@dataclass(frozen=True)
class RoutedData:
    """多源路由结果；data 与来源信息分离，避免污染回测输入。"""

    data: pd.DataFrame
    lineage: pd.DataFrame
    missing_symbols: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return not self.missing_symbols

    @property
    def coverage(self) -> pd.DataFrame:
        """按证券汇总实际覆盖区间；不把行数误当作完整交易日历。"""
        if "symbol" not in self.data.columns or "date" not in self.data.columns:
            return pd.DataFrame(columns=["symbol", "rows", "start_date", "end_date"])
        return (
            self.data.groupby("symbol", as_index=False)
            .agg(rows=("date", "size"), start_date=("date", "min"), end_date=("date", "max"))
            .sort_values("symbol")
            .reset_index(drop=True)
        )

    def audit_dates(
        self,
        expected_dates: pd.DataFrame | Sequence[Any],
        symbols: str | Sequence[str] | None = None,
    ) -> DateCoverageReport:
        """报告预期交易日中缺少的 (date, symbol)，不自动补数。

        expected_dates 应在调用前按上市区间、停牌及资产日历口径过滤。
        """
        if isinstance(expected_dates, pd.DataFrame):
            calendar = validate_trading_dates(expected_dates)
        else:
            values = [expected_dates] if isinstance(expected_dates, str) else expected_dates
            calendar = validate_trading_dates(pd.DataFrame({"date": list(values)}))

        if symbols is None:
            symbol_values = self.metadata.get("requested_symbols", ())
            if not symbol_values and "symbol" in self.data.columns:
                symbol_values = self.data["symbol"].dropna().astype(str).tolist()
        else:
            symbol_values = symbols
        requested_symbols = normalize_symbols(symbol_values) if symbol_values else []

        expected_count = len(calendar)
        summary = pd.DataFrame({"symbol": requested_symbols})
        summary["expected_rows"] = expected_count
        if not requested_symbols or calendar.empty:
            summary["actual_rows"] = 0 if expected_count else expected_count
            summary["missing_rows"] = 0
            summary["coverage_ratio"] = 1.0
            return DateCoverageReport(
                summary=summary,
                missing_keys=pd.DataFrame(columns=["date", "symbol"]),
            )

        expected = pd.MultiIndex.from_product(
            [calendar["date"], requested_symbols], names=["date", "symbol"]
        ).to_frame(index=False)
        actual = self.data.loc[:, ["date", "symbol"]].copy()
        actual["date"] = pd.to_datetime(actual["date"], errors="raise").dt.normalize()
        actual["symbol"] = actual["symbol"].astype(str).str.upper()
        actual = actual.drop_duplicates()

        matched = expected.merge(actual, on=["date", "symbol"], how="left", indicator=True)
        missing_keys = (
            matched.loc[matched["_merge"] == "left_only", ["date", "symbol"]]
            .sort_values(["date", "symbol"])
            .reset_index(drop=True)
        )
        missing_counts = missing_keys.groupby("symbol").size()
        summary["missing_rows"] = summary["symbol"].map(missing_counts).fillna(0).astype(int)
        summary["actual_rows"] = summary["expected_rows"] - summary["missing_rows"]
        summary["coverage_ratio"] = summary["actual_rows"] / summary["expected_rows"]
        summary = summary[
            ["symbol", "expected_rows", "actual_rows", "missing_rows", "coverage_ratio"]
        ]
        return DateCoverageReport(summary=summary, missing_keys=missing_keys)


class DataCoverageError(RuntimeError):
    def __init__(self, message: str, result: RoutedData):
        super().__init__(message)
        self.result = result


def normalize_symbols(symbols: str | Sequence[str]) -> list[str]:
    values = [symbols] if isinstance(symbols, str) else list(symbols)
    normalized = [str(symbol).strip().upper() for symbol in values if str(symbol).strip()]
    if not normalized:
        raise ValueError("symbols cannot be empty")
    return list(dict.fromkeys(normalized))


def validate_trading_dates(data: pd.DataFrame) -> pd.DataFrame:
    if "date" not in data.columns:
        raise ValueError("trading-date data must contain a 'date' column")
    result = data.loc[:, ["date"]].copy()
    result["date"] = pd.to_datetime(result["date"], errors="raise").dt.normalize()
    return result.drop_duplicates().sort_values("date").reset_index(drop=True)


def validate_daily_bars(data: pd.DataFrame, fields: Sequence[str]) -> pd.DataFrame:
    required = [*BAR_KEY_COLUMNS, *fields]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"daily-bar data is missing columns: {missing}")

    result = data.loc[:, required].copy()
    result["date"] = pd.to_datetime(result["date"], errors="raise").dt.normalize()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    for field_name in fields:
        result[field_name] = pd.to_numeric(result[field_name], errors="coerce")
    if result.duplicated(["date", "symbol"]).any():
        raise ValueError("daily-bar data contains duplicate date/symbol rows")
    return result.sort_values(["date", "symbol"]).reset_index(drop=True)


def validate_macro_observations(data: pd.DataFrame) -> pd.DataFrame:
    """校验带发布日期的宏观长表，供 point-in-time 因子计算使用。"""
    required = [*MACRO_KEY_COLUMNS, "value"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"macro data is missing columns: {missing}")

    result = data.loc[:, required].copy()
    result["period_date"] = pd.to_datetime(result["period_date"], errors="raise").dt.normalize()
    result["available_at"] = pd.to_datetime(result["available_at"], errors="raise").dt.normalize()
    result["indicator"] = result["indicator"].astype(str)
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    if result.duplicated(["period_date", "available_at", "indicator"]).any():
        raise ValueError("macro data contains duplicate point-in-time observations")
    if (result["available_at"] < result["period_date"]).any():
        raise ValueError("macro available_at cannot be earlier than period_date")
    return result.sort_values(["indicator", "available_at", "period_date"]).reset_index(drop=True)
