import numpy as np
import pandas as pd
import pytest

from factors.evaluation import analyze_factors, normalize_factor_panel


def _panel(periods: int = 18, assets: int = 30) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.date_range("2023-01-31", periods=periods, freq="ME")
    rows = []
    for date in dates:
        factor = rng.normal(size=assets)
        noise = rng.normal(scale=0.01, size=assets)
        for number in range(assets):
            rows.append(
                {
                    "date": date,
                    "symbol": f"A{number:03d}",
                    "quality": factor[number],
                    "noise": rng.normal(),
                    "fwd_ret": 0.02 * factor[number] + noise[number],
                    "layer": "large" if number < assets / 2 else "small",
                }
            )
    return pd.DataFrame(rows)


def test_factor_analysis_detects_predictive_direction_and_frequency():
    result = analyze_factors(_panel(), factors=["quality", "noise"])
    whole = result.summary[result.summary["layer"] == "ALL"].set_index("factor")

    assert result.periods_per_year == 12
    assert whole.loc["quality", "rank_ic_mean"] > 0.8
    assert whole.loc["quality", "long_short_ann_return"] > 0
    assert abs(whole.loc["quality", "icir_ann"]) > abs(
        whole.loc["noise", "icir_ann"]
    )
    assert len(result.ic_series["ALL|pearson|quality"]) == 18


def test_factor_analysis_rejects_duplicate_panel_keys():
    panel = _panel(periods=2)
    duplicate = pd.concat([panel, panel.iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate"):
        normalize_factor_panel(duplicate)


def test_factor_analysis_requires_valid_method_and_group_count():
    panel = _panel(periods=2)

    with pytest.raises(ValueError, match="ic_method"):
        analyze_factors(panel, ic_method="kendall")
    with pytest.raises(ValueError, match="n_groups"):
        analyze_factors(panel, n_groups=1)
