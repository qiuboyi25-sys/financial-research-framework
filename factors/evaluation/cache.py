"""因子面板的 Parquet 缓存、DuckDB 查询和字段说明输出。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DISPLAY_COLUMNS = [
    "factor_name",
    "date",
    "symbol",
    "definition",
    "asset_class",
    "data_source",
    "frequency",
    "forward_return_definition",
    "calculation_version",
]


def write_factor_parquet(
    panel: pd.DataFrame,
    output_path: str | Path,
) -> tuple[Path, str]:
    """通过统一 DuckDB 引擎将因子长表保存为 Parquet。"""
    import duckdb

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    try:
        connection.register("factor_panel", panel)
        escaped = str(output).replace("'", "''")
        connection.execute(
            f"COPY factor_panel TO '{escaped}' "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
    finally:
        connection.close()
    return output, "duckdb"


def read_factor_parquet(
    parquet_path: str | Path,
    *,
    columns: list[str] | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """用统一 DuckDB 引擎投影查询 Parquet。"""
    import duckdb

    path = Path(parquet_path).resolve()
    projection = ", ".join(f'"{column}"' for column in columns) if columns else "*"
    limit_sql = f" LIMIT {int(limit)}" if limit is not None else ""
    escaped = str(path).replace("'", "''")
    return duckdb.sql(
        f"SELECT {projection} FROM read_parquet('{escaped}')"
        f" ORDER BY date, symbol{limit_sql}"
    ).df()


def factor_field_preview(panel: pd.DataFrame, rows: int = 8) -> pd.DataFrame:
    """返回适合终端打印和 Markdown 展示的因子字段前几行。"""
    available = [column for column in DISPLAY_COLUMNS if column in panel.columns]
    return panel.loc[:, available].head(rows).copy()


def write_factor_markdown(
    panel: pd.DataFrame,
    output_path: str | Path,
    *,
    parquet_path: str | Path,
    storage_engine: str,
    rows: int = 8,
) -> Path:
    """生成包含数据来源、定义、缓存用法和样例字段的 Markdown。"""
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    preview = factor_field_preview(panel, rows=rows)
    factor_names = ", ".join(panel["factor_name"].dropna().astype(str).unique())
    sources = ", ".join(panel["data_source"].dropna().astype(str).unique())
    definitions = "; ".join(panel["definition"].dropna().astype(str).unique())
    asset_classes = ", ".join(panel["asset_class"].dropna().astype(str).unique())
    date_start = pd.to_datetime(panel["date"]).min().date()
    date_end = pd.to_datetime(panel["date"]).max().date()
    markdown = f"""# 换手率因子字段说明

## 数据与定义

| 项目 | 内容 |
| --- | --- |
| 因子名称 | {factor_names} |
| 日期范围 | {date_start} 至 {date_end} |
| 因子定义 | {definitions} |
| 资产类别 | {asset_classes} |
| 数据来源 | {sources} |
| 前瞻收益 | {panel["forward_return_definition"].iloc[0]} |
| 缓存文件 | `{Path(parquet_path).name}` |
| 本次写入引擎 | {storage_engine} |

换手率原始单位沿用用户提供的数据，计算前不再乘除100。真实研究应记录复权方式、股票池、停牌、上市天数和异常值
处理规则。当前 `fwd_ret` 是月末收盘到下一月末收盘收益，仅用于评价，不参与因子计算。

标准CSV/Parquet可通过公开文件Provider读取：

```python
from data_providers import FileDataProvider

provider = FileDataProvider("path/to/daily_bars.parquet")
daily_bars = provider.fetch_daily_bars(
    ["600000.SH", "000001.SZ"],
    "2020-01-01",
    "2025-12-31",
    fields=["close", "turnover"],
    adjust="none"
)
```

## 字段前几行

{preview.to_markdown(index=False)}

## DuckDB 查询 Parquet

```sql
SELECT
    factor_name, date, symbol, definition, asset_class,
    data_source, frequency, turnover_20d_mean, fwd_ret
FROM read_parquet('{Path(parquet_path).name}')
ORDER BY date, symbol
LIMIT 20;
```

Python 中可以直接查询：

```python
import duckdb

preview = duckdb.sql(\"\"\"
    SELECT *
    FROM read_parquet('{Path(parquet_path).name}')
    ORDER BY date, symbol
    LIMIT 10
\"\"\").df()
print(preview)
```
"""
    output.write_text(markdown, encoding="utf-8")
    return output
