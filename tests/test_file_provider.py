import pandas as pd

from data_providers import FileDataProvider


def test_file_provider_filters_symbols_dates_and_fields(tmp_path):
    path = tmp_path / "bars.csv"
    pd.DataFrame(
        {
            "date": ["2025-01-02", "2025-01-03", "2025-01-03"],
            "symbol": ["asset_a", "asset_a", "asset_b"],
            "close": [10.0, 10.5, 20.0],
        }
    ).to_csv(path, index=False)

    provider = FileDataProvider(path)
    result = provider.fetch_daily_bars(
        "ASSET_A", "2025-01-03", "2025-01-03", fields=["close"]
    )

    assert result[["symbol", "close"]].to_dict("records") == [
        {"symbol": "ASSET_A", "close": 10.5}
    ]
