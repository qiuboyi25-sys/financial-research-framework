import numpy as np
import pandas as pd

from factors.liquidity import build_turnover_factor_panel
from factors.liquidity.turnover import FACTOR_NAME


def test_turnover_factor_uses_trailing_observations_and_next_month_return():
    dates = pd.bdate_range("2025-01-01", "2025-03-31")
    bars = pd.DataFrame(
        {
            "date": np.tile(dates, 2),
            "symbol": np.repeat(["A", "B"], len(dates)),
            "close": np.concatenate(
                [np.linspace(100, 130, len(dates)), np.linspace(80, 88, len(dates))]
            ),
            "turnover": np.concatenate(
                [np.arange(1, len(dates) + 1), np.full(len(dates), 2.0)]
            ),
        }
    )

    panel = build_turnover_factor_panel(
        bars, window=5, data_source="unit-test"
    )
    asset_a = panel[panel["symbol"] == "A"].reset_index(drop=True)

    january_dates = dates[dates.month == 1]
    expected = np.arange(1, len(january_dates) + 1)[-5:].mean()
    assert asset_a.loc[0, FACTOR_NAME] == expected
    assert asset_a.loc[0, "fwd_ret"] == (
        asset_a.loc[1, "close"] / asset_a.loc[0, "close"] - 1
    )
    assert asset_a.loc[0, "definition"] == "月末时点向前5个交易日换手率的算术平均值"
    assert asset_a.loc[0, "asset_class"] == "A股"
