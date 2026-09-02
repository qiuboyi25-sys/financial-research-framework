import numpy as np
import pandas as pd

from backtest_adapters import align_target_weights_to_prices
from factors.asset_allocation import MacroRule, build_macro_scores
from portfolio import AssetWeightRule, build_dynamic_weights


def test_macro_score_uses_only_available_observations():
    observations = pd.DataFrame(
        {
            "period_date": ["2024-12-31", "2025-01-31"],
            "available_at": ["2025-01-02", "2025-02-10"],
            "indicator": ["activity", "activity"],
            "value": [50.0, 51.0],
        }
    )
    scores, audit = build_macro_scores(
        observations,
        pd.DatetimeIndex(["2025-02-05", "2025-02-15"]),
        [MacroRule("equity", "activity", 1, 1)],
    )
    assert scores.loc[pd.Timestamp("2025-02-05"), "equity"] == 0.0
    assert scores.loc[pd.Timestamp("2025-02-15"), "equity"] == 1.0
    assert audit.iloc[0]["latest_period"] == pd.Timestamp("2024-12-31")


def test_weights_and_next_price_date_execution():
    signals = pd.DataFrame(
        {"equity": [1.0], "bond": [1.0]},
        index=pd.to_datetime(["2025-01-31"]),
    )
    rules = [
        AssetWeightRule("equity", 0.4, 0.2),
        AssetWeightRule("bond", 0.5, 0.2),
    ]
    weights = build_dynamic_weights(
        signals, rules, cash_symbol="cash", cash_central_weight=0.1
    )
    execution = align_target_weights_to_prices(
        weights, pd.to_datetime(["2025-01-31", "2025-02-03"])
    )
    assert np.allclose(execution.sum(axis=1), 1.0)
    assert execution.index.tolist() == [pd.Timestamp("2025-02-03")]
