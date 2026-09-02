"""把标准行情转换为第三方回测库输入。"""
from .backtrader_adapter import to_backtrader_feeds, to_backtrader_frames
from .bt_adapter import (
    align_target_weights_to_prices,
    build_dynamic_weight_backtest,
    build_monthly_weight_backtest,
    to_bt_prices,
)

__all__ = [
    "build_monthly_weight_backtest",
    "build_dynamic_weight_backtest",
    "align_target_weights_to_prices",
    "to_backtrader_feeds",
    "to_backtrader_frames",
    "to_bt_prices",
]
