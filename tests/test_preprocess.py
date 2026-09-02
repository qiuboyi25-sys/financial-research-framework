import numpy as np
import pandas as pd

from factors.evaluation import cross_sectional_preprocess


def test_mad_preprocess_preserves_raw_values_and_standardizes_each_date():
    panel = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-31"] * 6 + ["2025-02-28"] * 6),
            "factor": [1, 2, 3, 4, 5, 1000, 2, 3, 4, 5, 6, 7],
        }
    )
    original = panel["factor"].copy()
    result = cross_sectional_preprocess(panel, "factor")

    assert result["factor"].equals(original)
    assert result.loc[5, "factor_winsorized"] < 1000
    means = result.groupby("date")["factor_zscore"].mean()
    assert np.allclose(means, 0.0)


def test_preprocess_replaces_non_finite_values_with_missing():
    panel = pd.DataFrame(
        {"date": ["2025-01-31"] * 4, "factor": [1.0, 2.0, np.inf, -np.inf]}
    )
    result = cross_sectional_preprocess(panel, "factor", method="none")
    assert result["factor"].isna().sum() == 2
