"""Credential-free CSV/Parquet daily-bar provider."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd

from .contracts import CORE_BAR_FIELDS, normalize_symbols, validate_daily_bars


class FileDataProvider:
    """Read a standardized local file without copying it into the repository."""

    provider_name = "file"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()

    def _read(self) -> pd.DataFrame:
        suffix = self.path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(self.path)
        if suffix in {".parquet", ".pq"}:
            return pd.read_parquet(self.path)
        raise ValueError("file provider supports only CSV and Parquet")

    def fetch_trading_dates(
        self, start_date: str, end_date: str, *, force_refresh: bool = False
    ) -> pd.DataFrame:
        del force_refresh
        bars = self._read()
        if "date" not in bars:
            raise ValueError("daily-bar file must contain a date column")
        dates = pd.to_datetime(bars["date"], errors="raise").dt.normalize()
        mask = dates.between(pd.Timestamp(start_date), pd.Timestamp(end_date))
        return pd.DataFrame({"date": dates[mask].drop_duplicates().sort_values()})

    def fetch_daily_bars(
        self,
        symbols: str | Sequence[str],
        start_date: str,
        end_date: str,
        fields: Sequence[str] | None = None,
        *,
        adjust: str = "none",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        del force_refresh
        if adjust != "none":
            raise ValueError(
                "FileDataProvider does not infer adjustment; provide adjusted data "
                "and keep adjust='none'"
            )
        selected_fields = tuple(fields or CORE_BAR_FIELDS)
        bars = validate_daily_bars(self._read(), selected_fields)
        requested = normalize_symbols(symbols)
        mask = (
            bars["symbol"].isin(requested)
            & bars["date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
        )
        return bars.loc[mask].reset_index(drop=True)
