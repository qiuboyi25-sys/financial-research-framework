# Financial Research Framework

一个用于展示“如何把量化研究做成可信、可复现、可测试工程”的 Python 项目。

它不是一份只保留最终收益曲线的策略代码，而是把研究拆成数据契约、时点控制、因子构造、横截面预处理、统计评价、组合权重、成交延迟和报告输出等独立模块。仓库提供一个完全离线的换手率因子示例，可以从合成日行情开始，一条命令生成因子缓存、字段说明、统计结果和自包含 HTML 报告。完整研究环境已经完成多项全天候、风险平价、利率择时和简单配置研究，公开版提供[脱敏后的成果与局限说明](docs/reproduction_results.md)。

> 公开仓库只包含通用代码、研究规范、合成示例和测试，不包含真实市场数据、授权材料、访问凭据、商业数据接口或特定研究材料中的证券清单。所有输出仅用于研究方法展示，不构成投资建议。

## 1. 这个项目展示什么

本项目重点展示的不是某个因子过去赚了多少钱，而是下面五项可迁移的研究能力。

### 1.1 可复现的单因子研究闭环

```text
标准日行情
  → 原始因子
  → NaN / inf处理
  → 横截面去极值
  → 横截面z-score
  → 下一期收益错期
  → IC / Rank IC
  → 分组多空
  → Parquet / CSV / Markdown / HTML
```

公开示例使用过去20个交易日平均换手率：

```text
turnover_20d_mean(i,t)
    = mean(turnover(i,t-19), ..., turnover(i,t))
```

月末因子只使用月末及之前的数据，收益标签使用本月最后交易日收盘到下一月最后交易日收盘收益：

```text
fwd_ret(i,t) = close(i,t+1) / close(i,t) - 1
```

因子和收益标签在代码中分开生成，便于检查是否发生未来价格泄漏。

### 1.2 能发现数据错误的契约层

`data_providers/contracts.py`提供：

- 日期和证券代码标准化；
- 日行情必需字段验证；
-`date + symbol`重复键拒绝；
- 数值字段强制转换；
- 交易日覆盖率和缺口报告；
- 宏观数据`period_date + available_at + indicator`时点约束；
- 禁止宏观发布日期早于统计期日期。

这些检查不会自动“修好”可疑数据，而是尽早报错，让研究者决定应该排除、回补还是修改口径。

### 1.3 可检查的横截面因子评价

`factors/evaluation/`当前实现：

- 原始值保留；
-`NaN`、正无穷和负无穷处理；
- MAD去极值；
- 分位数截尾；
- 每期横截面z-score；
- Pearson IC；
- Spearman Rank IC；
- IC均值、标准差、ICIR和年化ICIR；
- IC为正的期数比例；
- 因子有效覆盖率；
- 五组或十组最高组减最低组的等权多空收益；
- 全样本与预定义市场分层的独立评价；
- IC时间序列和多空累计净值。

评价函数返回结构化对象，而不是只生成图片，因此统计结果还可以继续进入筛选、组合或测试流程。

### 1.4 防止未来信息的多资产研究组件

公开仓库保留了与具体证券清单无关的多资产研究组件：

| 组件 | 文件 | 已实现内容 |
| --- | --- | --- |
| 宏观趋势 | `factors/asset_allocation/macro.py` | 每个调仓日只读取`available_at <= rebalance_date`的观测；保留实际使用期数审计 |
| 低延迟趋势 | `factors/asset_allocation/technical.py` | LLT趋势线、相对动量和均值动量 |
| 估值状态 | 同上 | 滚动历史分位数映射为离散得分 |
| 资金流变化 | 同上 | 当期资金流相对过去窗口的意外变化 |
| 动态权重 | `portfolio/dynamic_weights.py` | 中枢权重、战术偏离、上下限约束和现金剩余吸收 |
| 延迟成交 | `backtest_adapters/bt_adapter.py` | 把月末信号映射至下一可用价格日，避免假设月末收盘后仍能按同一收盘价成交 |

这些是可以复用和单独测试的“策略零件”。完整研究环境已经使用这些能力生成真实历史回测报告；公开版提供经核验的结果摘要，但没有保留依赖受限数据和特定证券清单的完整策略配置，因此无法仅凭公开仓库重新生成这些历史结果。

### 1.5 工程化与审计

- 因子面板保存为ZSTD压缩Parquet；
- DuckDB用于投影查询研究缓存；
- HTML报告将图片嵌入Base64，单文件即可打开；
- 输入、缓存和输出目录默认不进入Git；
- 研究字段保存定义、数据来源、频率、收益标签口径和计算版本；
- GitHub Actions自动运行代码检查和单元测试；
- 全部测试不访问网络、不需要密钥。

## 2. 当前已经完成的研究成果

这里把“实证收益结论”和“研究工程成果”分开说明。

### 2.1 已完成：换手率因子最小研究闭环

公开示例已经打通以下步骤：

1. 从标准日行情构造20日平均换手率原始值；
2. 每只证券独立滚动，避免证券之间数据串联；
3. 每月选取各证券最后一个有效交易日；
4. 原始因子经过MAD去极值和横截面z-score；
5. 下一月收益单独向后对齐；
6. 计算Pearson IC、Rank IC、ICIR、胜率和有效覆盖率；
7. 构造最高组减最低组的等权多空收益和累计净值；
8. 输出机器可读结果和供人工阅读的HTML报告。

这证明同一框架能够接收真实CSV/Parquet输入，而无需把数据源逻辑写进因子函数。

### 2.2 已完成：合成信号检出测试

Demo使用固定随机种子生成2021-01至2025-12、40个虚拟资产的日行情。数据生成过程中人为设置“前一期换手率状态与下一期收益正相关”，目的是验证评价框架能否识别已知方向，而不是模拟真实市场。

当前版本的确定性Demo结果如下：

| 指标 | 结果 | 解释 |
| --- | ---: | --- |
| 月度横截面期数 | 59 | 最后一期没有下一月收益，因此不进入有效评价 |
| 有效覆盖率 | 98.33% | 主要缺失来自最后一期前瞻收益 |
| Pearson IC均值 | 0.4061 | 成功识别人为注入的线性正相关 |
| Pearson ICIR | 3.2670 | 合成关系稳定，不能外推至真实市场 |
| Spearman Rank IC均值 | 0.3615 | 排序方向也被正确识别 |
| Rank ICIR | 2.5251 | 仅用于验证秩相关计算 |
| IC为正比例 | 100% | 是数据生成机制的结果，不是实证胜率 |
| 五分组多空年化 | 41.80% | 是合成收益关系的结果，不代表可交易收益 |

这组数字的研究意义只有一个：当数据中确实存在一个已知的横截面关系时，框架能够稳定识别其方向、排序和分组收益。如果框架无法通过这个测试，就不应拿它分析真实因子。

### 2.3 已完成：未来信息防护测试

自动化测试验证了：

- 宏观数据在调仓日尚未发布时不会被使用；
- 月末因子对应下一月收益，而不是当月收益；
- 重复的`date + asset`面板键会直接报错；
- 正负无穷会转为缺失，不会进入排序；
- MAD去极值不覆盖原始因子；
- 每期标准化后的横截面均值接近0；
- 现金不足时，正向战术偏离按比例缩小；
- 目标权重每期合计为1且不为负；
- 月末信号默认在下一可用价格日执行。

当前共有9项离线测试，全部通过。

### 2.4 已完成：可复用输出

运行Demo后生成：

```text
output/turnover_demo/
├── cache/
│   └── turnover_factor_panel.parquet
├── turnover_factor_fields.md
├── turnover_factor_report.csv
└── turnover_factor_report.html
```

| 输出 | 展示内容 | 适用场景 |
| --- | --- | --- |
| `turnover_factor_panel.parquet` | 原始因子、去极值值、z-score、前瞻收益和研究元数据 | 后续分析、复算、批量研究 |
| `turnover_factor_fields.md` | 因子定义、日期、数据来源、收益口径和字段样例 | 人工审计、研究交接 |
| `turnover_factor_report.csv` | IC、Rank IC、ICIR、覆盖率、胜率和多空年化汇总 | 比较因子、程序化筛选 |
| `turnover_factor_report.html` | 汇总表、分层ICIR、IC时序图、多空净值图和研究备注 | 项目展示、单因子复盘 |

生成结果被`.gitignore`排除，避免把本地输入或衍生数据意外提交到公开仓库。

### 2.5 已完成：多类策略复现与报告归档

完整研究环境中已经留存多项最终 HTML、CSV 或 JSON 报告。公开版依据这些最终产物重新核验并脱敏汇总，不把临时调参报告或未经留出的高指标当成已验证策略。

| 代表性研究 | 完成性质 | 样本区间 | 年化收益 | 最大回撤 | Sharpe |
| --- | --- | --- | ---: | ---: | ---: |
| 多元配置全天候（点时 ETF 池） | 原始数据重建 | 2017-01—2025-07 | 5.30% | 2.74% | 1.78 |
| 利率综合择时 | 代理复现 | 2018-01—2026-05 | 2.94% | 3.27% | 1.43 |
| 久期轮动 | 代理复现 | 2018-01—2026-05 | 5.61% | 9.32% | 1.31 |
| 中国全天候 ETF 短样本 | 策略基准 | 2023-07—2026-07 | 9.76% | 7.59% | 1.36 |
| 全球多资产 ERC | 策略基准 | 2018-01—2026-06 | 8.61% | 13.94% | 1.16 |
| 三资产逆波动率 | 策略基准 | 2018-01—2026-06 | 4.73% | 2.53% | 1.95 |

全天候点时重建还保存了月胜率67.65%、平均月换手率5.43%以及0—0.30%双边费率敏感性；利率项目对2,099个日频观测完成了可用日期、`t+1`收益、信号完整性和净值有效性校验。

完整结果、方法差异、简单配置基线、样本内参数探索及不能公开的部分见：

- [已完成的策略复现与回测成果](docs/reproduction_results.md)
- [脱敏 HTML 成果总览](docs/reports/reproduction_showcase.html)

这里的“成功复现”表示能够从底层输入独立生成信号、权重、收益和审计记录，不表示所有代理口径都与参考材料逐项完全相同，也不表示未来或样本外一定有效。

## 3. 公开版与完整研究环境的区别

这个仓库来自一个更完整的本地研究环境，但公开时没有做简单的全量复制。以下内容因授权、隐私、可复现性或展示必要性被删除。

| 删除内容 | 删除原因 | 公开版替代方案 |
| --- | --- | --- |
| 本地真实行情、财务、状态、宏观和基金数据 | 数据量大，且可能受授权和再分发限制 | 使用固定随机种子的合成数据；用户自行提供CSV/Parquet |
| Parquet、IPC、数据库文件和数据缓存 | 可能包含完整历史样本和上游字段 | `.gitignore`统一排除数据格式和`data/`目录 |
| 数据库地址、账号、密码及环境文件 | 属于访问凭据和本地基础设施信息 | 仓库只保留无密钥的`.env.example` |
| 需要账户授权的商业数据接口 | 其他用户无法直接运行，也不适合公开凭据和响应结构 | 提供不联网的`FileDataProvider`和标准Provider协议 |
| 商业数据服务的整套本地文档 | 可能受许可限制，而且会掩盖项目自身代码 | 仅保留本项目的数据契约和输入格式说明 |
| 与内部数据表强绑定的数据目录和字段映射 | 暴露本地表结构，离开原环境无法运行 | 公共字段统一为`date, symbol, open, high, low, close, volume`等 |
| 特定研究材料的证券清单、产品名称、权重和参数 | 可能暴露来源特征，也不具备普遍适用性 | 保留通用宏观、技术和动态权重算法，不保留专属配置 |
| 与特定材料绑定的完整策略装配目录 | 缺少受限数据后无法诚实复现真实结果 | 将其中可迁移能力拆成独立模块和测试 |
| 原始真实回测HTML、CSV和中间缓存 | 可能间接泄露样本、标的、路径和数据范围 | 不上传原文件；公开经核验的脱敏汇总和重新生成的HTML总览 |
| 连通性测试、抓取脚本和一次性数据整理脚本 | 依赖本地网络、授权或特定文件结构 | 公开测试全部使用内存数据或临时CSV |
| 内部工作流、研究技能文件和数据库数据字典 | 属于本地研究辅助资产，不是运行框架所必需 | README和`docs/`只说明公开研究规范 |
| 原本地仓库的提交历史 | 历史版本可能残留已删除文件或敏感配置 | 目标仓库使用独立、干净的公开提交历史 |

删除这些内容不是为了隐藏研究方法，而是为了确保公开仓库满足三个条件：别人能够运行、不会泄露访问能力、不会违规再分发数据。

## 4. 当前尚未完成或没有公开的部分

为了让项目展示与实际代码一致，以下能力当前不能宣称已经完成：

- 没有随仓库提供真实市场原始数据、逐期持仓和可直接复跑全部历史结果的专属策略配置；
- 没有提供历史股票池、上市天数、ST、停牌和涨跌停状态数据；
- 没有实现行业中性、行业加市值中性或Beta中性；
- 没有提供反转、BP和利润增长三个完整公开示例；
- 当前评价内核计算最高组减最低组，但尚未输出每一组的完整收益序列和单调性分数；
- HTML尚未包含交易成本、组合换手率、分年度收益和多头/空头贡献拆分；
- 没有实现下一日开盘、VWAP等真实成交价格标签；
- 回测适配器是第三方引擎的输入桥梁，本项目不自建撮合系统；
- 多资产研究已经完成本地实证并公开脱敏指标摘要，但原始报告和完整专属配置没有公开。

因此，当前版本更准确的定位是：

> 一个已经跑通、能够发现基础错误的公开研究内核，加上可复现的单因子最小示例和经核验的历史策略成果摘要；不是完整的量化产品，也不把历史回测表述为未来有效的投资策略。

## 5. 项目结构

```text
financial-research-framework/
├── data_providers/
│   ├── contracts.py          # 行情、宏观时点与覆盖率契约
│   ├── file_provider.py      # 无凭据CSV/Parquet数据源
│   └── base.py               # 通用Parquet缓存基础类
├── factors/
│   ├── evaluation/
│   │   ├── preprocess.py     # MAD、分位数截尾、z-score
│   │   ├── core.py           # IC、Rank IC、ICIR和分组多空
│   │   ├── cache.py          # Parquet、DuckDB和字段Markdown
│   │   └── report.py         # 自包含HTML报告
│   ├── liquidity/
│   │   └── turnover.py       # 20日平均换手率示例
│   └── asset_allocation/
│       ├── macro.py          # point-in-time宏观趋势
│       └── technical.py      # LLT、动量、分位数和资金流
├── portfolio/
│   └── dynamic_weights.py    # 中枢权重和战术偏离约束
├── backtest_adapters/
│   ├── bt_adapter.py         # bt输入与延迟成交日期
│   └── backtrader_adapter.py # Backtrader行情Feed
├── scripts/
│   └── run_turnover_factor_research.py
├── docs/
│   ├── research_spec.md
│   ├── public_data_policy.md
│   ├── reproduction_results.md
│   └── reports/
│       └── reproduction_showcase.html
├── tests/
├── .github/workflows/tests.yml
└── pyproject.toml
```

## 6. 安装

要求Python 3.10+。

```bash
git clone https://github.com/qiuboyi25-sys/financial-research-framework.git
cd financial-research-framework
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,report]'
```

Windows PowerShell激活环境：

```powershell
.venv\Scripts\Activate.ps1
```

`bt`与Backtrader为可选依赖：

```bash
python -m pip install -e '.[backtest]'
```

## 7. 运行离线因子Demo

```bash
python -m scripts.run_turnover_factor_research \
  --demo \
  --output-dir output/turnover_demo
```

Demo无需联网、无需数据文件、无需任何API密钥。

参数说明：

| 参数 | 含义 | 默认值 |
| --- | --- | --- |
| `--demo` | 使用确定性合成数据 | 未提供输入文件时也使用Demo |
| `--input` | 用户日行情CSV或Parquet | 无 |
| `--output-dir` | 结果目录 | `output/turnover_factor` |
| `--data-source` | 写入研究血缘的数据来源名称 | 输入文件名或合成数据标识 |
| `--window` | 换手率回看交易日数 | 20 |

## 8. 使用自己的数据

输入CSV或Parquet至少需要：

| 字段 | 类型建议 | 含义 |
| --- | --- | --- |
| `date` | date/datetime/string | 交易日期 |
| `symbol` | string | 资产代码 |
| `close` | numeric | 收盘价 |
| `turnover` | numeric | 日换手率；单位必须在研究记录中固定 |
| `asset_class` | string，可选 | 市场或样本分层 |

```bash
python -m scripts.run_turnover_factor_research \
  --input path/to/daily_bars.parquet \
  --data-source user_supplied \
  --window 20 \
  --output-dir output/my_research
```

文件Provider也可以单独使用：

```python
from data_providers import FileDataProvider

provider = FileDataProvider("path/to/daily_bars.parquet")
bars = provider.fetch_daily_bars(
    ["ASSET_A", "ASSET_B"],
    "2020-01-01",
    "2025-12-31",
    fields=["close", "turnover"],
)
```

框架不会猜测输入是否前复权、后复权或总收益口径。数据提供者必须在研究规范和`data_source`中明确记录。

## 9. Python研究示例

```python
import pandas as pd

from factors.evaluation import analyze_factors, cross_sectional_preprocess
from factors.liquidity import build_turnover_factor_panel

bars = pd.read_parquet("path/to/daily_bars.parquet")

# 原始因子与下一期收益
panel = build_turnover_factor_panel(
    bars,
    window=20,
    data_source="user_supplied",
)

# 保留原始值，增加winsorized和zscore列
panel = cross_sectional_preprocess(
    panel,
    "turnover_20d_mean",
    method="mad",
    threshold=3.0,
)

# 对处理后的因子做全样本和分层评价
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

`FactorAnalysisResult`包含：

```text
summary             汇总统计DataFrame
ic_series           各层、各方法、各因子的IC序列
long_short_returns  各层、各因子的多空收益序列
long_short_nav      各层、各因子的累计净值
periods_per_year    根据观察频率推断的年化期数
```

## 10. 研究可信度规则

- 在查看结果前固定股票池、调仓频率、持有期和成交时点；
- 因子计算不得使用调仓日之后的数据；
- 财务和宏观数据按实际发布日期对齐；
- 原始因子、清洗因子和标准化因子同时保留；
- 不把缺失值无条件填0；
- 不以单一最优参数作为因子有效证据；
- 同时检查IC、分组单调性、多头端和空头端；
- 延迟成交、剔除小市值和改变参数后仍需重新检验；
- 合成数据只能验证程序，不能验证经济逻辑；
- 所有真实研究都应记录数据版本和生成时间。

详细口径见[研究规范](docs/research_spec.md)，公开边界见[公开数据策略](docs/public_data_policy.md)。

## 11. 验证项目

```bash
pytest -q
ruff check .
```

当前本地验证结果：

```text
Ruff:   passed
Pytest: 9 passed
Demo:   Parquet + Markdown + CSV + HTML generated successfully
```

GitHub Actions会在每次push和pull request时重新运行Ruff与Pytest。

## 12. 下一步计划

公开版后续优先补齐：

1. 分组1至5/10的完整收益序列、收益柱状图和单调性指标；
2. 多头超额、空头贡献和股票池等权基准；
3. 组合换手率、交易成本和延迟成交版本；
4. 分年度IC和收益表现；
5. 反转、估值和盈利成长三个公开因子示例；
6. 市值、波动率、过去收益和流动性分层；
7. 行业、市值和Beta中性化接口；
8. 数据质量报告自动生成器。

这些扩展仍将遵循同一原则：先保证时点正确、结果可复算和假设可证伪，再比较收益表现。

## License

MIT
