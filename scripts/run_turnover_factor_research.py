"""运行换手率因子案例：构建面板、缓存、字段说明和 HTML 评价报告。"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from factors.evaluation import (
    cross_sectional_preprocess,
    factor_field_preview,
    write_factor_markdown,
    write_factor_parquet,
)
from factors.evaluation.report import write_factor_report
from factors.liquidity import build_turnover_factor_panel
from factors.liquidity.turnover import FACTOR_NAME


def build_demo_daily_bars(
    *,
    start_date: str = "2021-01-01",
    end_date: str = "2025-12-31",
    assets: int = 40,
) -> pd.DataFrame:
    """生成确定性 A 股形态样例；只用于验证研究链路。"""
    rng = np.random.default_rng(20260728)
    dates = pd.bdate_range(start_date, end_date)
    months = dates.to_period("M").unique()
    symbols = [f"{600000 + number:06d}.SH" for number in range(assets)]
    latent_turnover = rng.lognormal(mean=1.2, sigma=0.55, size=(len(months), assets))
    rows: list[dict[str, object]] = []
    prices = np.full(assets, 10.0)

    for month_number, month in enumerate(months):
        month_dates = dates[dates.to_period("M") == month]
        activity = latent_turnover[month_number]
        previous = latent_turnover[max(month_number - 1, 0)]
        standardized = (previous - previous.mean()) / previous.std()
        monthly_return = 0.012 * standardized + rng.normal(0.0, 0.025, assets)
        daily_growth = np.power(1.0 + monthly_return, 1.0 / len(month_dates))
        for date in month_dates:
            prices *= daily_growth
            daily_turnover = np.maximum(
                activity + rng.normal(0.0, 0.12, assets), 0.01
            )
            for asset_number, symbol in enumerate(symbols):
                rows.append(
                    {
                        "date": date,
                        "symbol": symbol,
                        "close": prices[asset_number],
                        "turnover": daily_turnover[asset_number],
                        "asset_class": "A股",
                    }
                )
    return pd.DataFrame(rows)


def read_daily_bars(path: str | Path) -> pd.DataFrame:
    """读取 CSV 或 Parquet 日行情输入。"""
    source = Path(path)
    if source.suffix.lower() == ".parquet":
        return pd.read_parquet(source)
    if source.suffix.lower() == ".csv":
        return pd.read_csv(source)
    raise ValueError("input must be a .csv or .parquet file")


def run_turnover_research(
    daily_bars: pd.DataFrame,
    *,
    output_dir: str | Path,
    data_source: str,
    window: int = 20,
) -> dict[str, Path]:
    """执行换手率因子研究并返回全部交付文件路径。"""
    output = Path(output_dir).resolve()
    cache_dir = output / "cache"
    panel = build_turnover_factor_panel(
        daily_bars,
        window=window,
        data_source=data_source,
        default_asset_class="A股",
    )
    panel = cross_sectional_preprocess(panel, FACTOR_NAME, method="mad", threshold=3.0)
    evaluated_factor = f"{FACTOR_NAME}_zscore"
    parquet_path, engine = write_factor_parquet(
        panel, cache_dir / "turnover_factor_panel.parquet"
    )
    markdown_path = write_factor_markdown(
        panel,
        output / "turnover_factor_fields.md",
        parquet_path=parquet_path,
        storage_engine=engine,
    )

    notes = (
        f"数据源：{data_source}；样本池：输入文件中的 A 股；"
        f"因子：过去 {window} 个交易日换手率均值；"
        "评价频率：月频；fwd_ret：本月末收盘至下一月末收盘收益；"
        "换手率单位沿用源数据；横截面采用MAD去极值和z-score；"
        "未做行业/市值中性化。"
    )
    report_path = write_factor_report(
        panel,
        output / "turnover_factor_report.html",
        title="换手率因子分析报告",
        subtitle=f"{data_source} · 月频截面评价",
        notes=notes,
        factors=[evaluated_factor],
        fwd_ret_col="fwd_ret",
        layer_col="asset_class",
        n_groups=5,
        ic_method="both",
    )
    return {
        "parquet": parquet_path,
        "markdown": markdown_path,
        "html": report_path,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="换手率因子研究案例")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--demo", action="store_true", help="使用确定性样例数据")
    source.add_argument("--input", help="真实日行情 CSV/Parquet")
    parser.add_argument(
        "--output-dir", default="output/turnover_factor", help="输出目录"
    )
    parser.add_argument("--data-source", default=None, help="真实输入的数据源说明")
    parser.add_argument("--window", type=int, default=20, help="换手率回看交易日")
    args = parser.parse_args(argv)

    if args.input:
        bars = read_daily_bars(args.input)
        data_source = args.data_source or f"本地文件：{Path(args.input).name}"
    else:
        bars = build_demo_daily_bars()
        data_source = "synthetic_demo（确定性合成数据，非真实行情）"

    outputs = run_turnover_research(
        bars,
        output_dir=args.output_dir,
        data_source=data_source,
        window=args.window,
    )
    panel = pd.read_parquet(outputs["parquet"])
    print("\n因子缓存字段前几行：")
    print(factor_field_preview(panel).to_string(index=False))
    print("\n输出文件：")
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
