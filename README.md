# Financial Research Framework

一个面向可复现量化研究的轻量 Python 框架。项目把数据校验、因子构造、横截面预处理、IC/Rank IC、分组多空、HTML 报告与组合权重拆分为可测试模块，并提供完全基于合成数据的离线示例。

> 本仓库只包含代码与合成示例，不包含真实行情、授权数据、访问凭据或商业数据接口。输出仅用于研究方法展示，不构成投资建议。

## 核心能力

- 标准日行情与宏观数据契约，拒绝重复键和错误时点。
- 横截面 MAD 去极值、分位数截尾和 z-score 标准化。
- 月度 Pearson IC、Spearman Rank IC、ICIR、胜率和分层统计。
- 五组/十组等权检验与多空净值。
- 带`available_at`约束的 point-in-time 宏观信号。
- 目标权重约束、信号延迟成交日期对齐。
- 自包含 HTML 因子报告和 Parquet 研究缓存。
- 不依赖网络和真实数据的确定性 Demo 与单元测试。

## 研究链路

```text
用户提供的 CSV / Parquet
          ↓
字段契约与唯一键校验
          ↓
原始因子构造（只使用信号时点及以前数据）
          ↓
无效值 → 去极值 → 横截面标准化
          ↓
下一期收益严格错期
          ↓
IC / Rank IC / 分组多空 / 分层诊断
          ↓
Parquet + Markdown + 自包含 HTML
```

## 目录

```text
financial-research-framework/
├── data_providers/          # 文件数据源与标准数据契约
├── factors/
│   ├── evaluation/          # 预处理、IC、分组检验、HTML报告
│   ├── liquidity/           # 换手率因子示例
│   └── asset_allocation/    # 宏观与技术信号组件
├── portfolio/               # 动态目标权重
├── backtest_adapters/       # bt / Backtrader 输入适配
├── scripts/                 # 可直接运行的研究入口
├── docs/                    # 研究口径与公开数据策略
└── tests/                   # 离线自动化测试
```

## 安装

要求 Python 3.10+。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,report]'
```

`bt`与 Backtrader 是可选依赖：

```bash
python -m pip install -e '.[backtest]'
```

## 运行离线因子 Demo

```bash
python -m scripts.run_turnover_factor_research \
  --demo \
  --output-dir output/turnover_demo
```

Demo 使用固定随机种子生成合成日行情，随后：

1. 构造过去20个交易日平均换手率原始因子；
2. 按月横截面做 MAD 去极值和 z-score；
3. 将因子与下一月月末收益严格错期；
4. 计算 IC、Rank IC、ICIR和五分组多空；
5. 输出 Parquet、字段说明 Markdown、汇总 CSV 和自包含 HTML。

生成物位于`output/`，该目录默认不纳入版本控制。

## 使用自己的数据

输入 CSV 或 Parquet 至少需要以下字段：

| 字段 | 含义 |
| --- | --- |
| `date` | 交易日期 |
| `symbol` | 资产代码 |
| `close` | 收盘价 |
| `turnover` | 日换手率，单位须在研究记录中固定 |
| `asset_class` | 可选的样本分层 |

```bash
python -m scripts.run_turnover_factor_research \
  --input path/to/daily_bars.parquet \
  --data-source user_supplied \
  --window 20 \
  --output-dir output/my_research
```

输入文件不会被提交；`.gitignore`默认排除`data/`和`output/`。

## Python 示例

```python
import pandas as pd

from factors.evaluation import analyze_factors, cross_sectional_preprocess
from factors.liquidity import build_turnover_factor_panel

bars = pd.read_parquet("path/to/daily_bars.parquet")
panel = build_turnover_factor_panel(bars, window=20, data_source="user_supplied")
panel = cross_sectional_preprocess(panel, "turnover_20d_mean", method="mad")

result = analyze_factors(
    panel,
    factors=["turnover_20d_mean_zscore"],
    fwd_ret_col="fwd_ret",
    layer_col="asset_class",
    n_groups=5,
    ic_method="both",
)
print(result.summary)
```

## 研究可信度约束

- 因子函数与前瞻收益计算分离，避免误用未来价格。
- 宏观数据必须提供`period_date`和`available_at`。
- 不自动填补缺失因子值；缺失原因应在上游记录。
- 分组前先验证横截面资产数量和唯一值数量。
- 交易信号默认在下一可用价格日执行。
- 合成 Demo 只验证代码链路，不能用于评价真实因子收益。

更完整的固定口径见[研究规范](docs/research_spec.md)，数据公开边界见[公开数据策略](docs/public_data_policy.md)。

## 测试

```bash
pytest -q
```

测试不访问网络，不需要任何 API 密钥。

## License

MIT
