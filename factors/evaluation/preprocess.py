"""Cross-sectional preprocessing for point-in-time factor panels."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _winsorize(values: pd.Series, method: str, threshold: float) -> pd.Series:
    valid = values.dropna()
    if valid.empty:
        return values
    if method == "none":
        return values
    if method == "mad":
        median = float(valid.median())
        mad = float((valid - median).abs().median())
        if not np.isfinite(mad) or mad == 0:
            return values
        width = threshold * 1.4826 * mad
        return values.clip(median - width, median + width)
    if method == "quantile":
        if not 0 < threshold < 0.5:
            raise ValueError("quantile threshold must be between 0 and 0.5")
        lower, upper = valid.quantile([threshold, 1 - threshold])
        return values.clip(float(lower), float(upper))
    raise ValueError("method must be 'mad', 'quantile', or 'none'")


def cross_sectional_preprocess(
    panel: pd.DataFrame,
    factor: str,
    *,
    date_column: str = "date",
    method: str = "mad",
    threshold: float = 3.0,
) -> pd.DataFrame:
    """Replace non-finite values, winsorize, and z-score within each date.

    Original values are preserved. Two columns are added:
    ``<factor>_winsorized`` and ``<factor>_zscore``.
    """
    if factor not in panel:
        raise KeyError(f"factor column not found: {factor}")
    if date_column not in panel:
        raise KeyError(f"date column not found: {date_column}")
    if method == "mad" and threshold <= 0:
        raise ValueError("MAD threshold must be positive")

    result = panel.copy()
    result[date_column] = pd.to_datetime(result[date_column], errors="raise")
    numeric = pd.to_numeric(result[factor], errors="coerce")
    result[factor] = numeric.replace([np.inf, -np.inf], np.nan)
    winsorized_name = f"{factor}_winsorized"
    zscore_name = f"{factor}_zscore"

    result[winsorized_name] = result.groupby(date_column, sort=False)[factor].transform(
        lambda values: _winsorize(values, method, threshold)
    )

    def zscore(values: pd.Series) -> pd.Series:
        standard_deviation = values.std(ddof=0)
        if not np.isfinite(standard_deviation) or standard_deviation == 0:
            return pd.Series(np.nan, index=values.index, dtype=float)
        return (values - values.mean()) / standard_deviation

    result[zscore_name] = result.groupby(date_column, sort=False)[
        winsorized_name
    ].transform(zscore)
    return result
