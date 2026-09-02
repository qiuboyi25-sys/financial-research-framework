"""通用截面因子评价接口。"""

from .cache import (
    factor_field_preview,
    read_factor_parquet,
    write_factor_markdown,
    write_factor_parquet,
)
from .core import (
    FactorAnalysisResult,
    analyze_factors,
    infer_factor_columns,
    normalize_factor_panel,
)
from .preprocess import cross_sectional_preprocess

__all__ = [
    "FactorAnalysisResult",
    "analyze_factors",
    "infer_factor_columns",
    "normalize_factor_panel",
    "factor_field_preview",
    "read_factor_parquet",
    "write_factor_markdown",
    "write_factor_parquet",
    "cross_sectional_preprocess",
]
