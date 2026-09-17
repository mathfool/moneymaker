# MoneyMaker · 选股买卖信号

本地运行的美股选股 / 买卖信号工具。左侧股票列表（自选 + 全市场扫描），中间 K 线 + 信号标记，右侧当前策略的条件检查、关键价位、仓位计算和回测。

## 启动

```bash
./start.sh
```

然后浏览器打开 <http://localhost:5173>（开发版）或 <http://localhost:8000>（打包版，`start.sh` 每次启动会重新打包，两者功能一致）。首次启动会自动创建 Python 虚拟环境并安装依赖。

- 后端：FastAPI + yfinance（免费，无需 API key），行情缓存在 `backend/data/market.sqlite`，6 小时内不重复下载。
- 前端：React + TradingView lightweight-charts。
- 股票池：S&P 500 + Nasdaq-100（约 520 只），名单缓存 7 天。

## 五个策略

| 键 | 交易者 | 核心逻辑 | 买入 | 卖出 |
|---|---|---|---|---|
| `minervini` | Mark Minervini | 趋势模板 8 条 + VCP 收缩 | 收紧后放量突破 20 日枢轴 | 两日收于 50 日线下 / 止损 ≤ 8% / 盈利 20% 后跌破 10EMA |
| `weinstein` | Stan Weinstein | 周线 30 周均线阶段分析 | Stage 1→2 放量突破 26 周阻力 | 周收盘跌破 30 周线进入 Stage 3/4 |
| `kullamagi` | Kristjan Kullamägi | 强势股旗形 + Episodic Pivot | 前置涨幅 ≥30% 后旗形放量突破，或跳空 ≥10% 且量 ≥3× | 两日收于 20EMA 下 / 突破日低点止损 / 盈利 10% 后跌破 10EMA |
| `kell` | Oliver Kell | 10/20 EMA 价格行为周期 | Wedge Pop / EMA Crossback / Base n' Break | Wedge Drop / Exhaustion Extension |
| `jlaw` | J Law 劳建华 | 多重优势叠加（趋势+RS+板块+量能+动量+大盘） | 回踩 10/21 EMA 缩量后放量收复，或放量突破 20 日高点 | 两日收于 21EMA 下 / 10EMA 下穿 21EMA / 止损 ≤ 5% / 盈利 15% 后跌破 10EMA |

## 基本面

每只票从 Yahoo Finance 拉 `info` + 季度利润表（缓存 3 天）：最新季度 EPS / 营收同比（上季对比、是否加速）、净利率、ROE、前瞻 EPS 增速、PE、市值、机构持股、空头比例、下次财报日。

- Minervini 条件里加了 EPS 同比 ≥ 25%、营收 ≥ 10%、EPS 加速；J Law 加了 EPS ≥ 20%、营收 ≥ 15%；Kullamägi 加了 EPS/营收 ≥ 20%（权重减半）。Weinstein 和 Kell 是纯技术派，只展示不计分。数据缺失时条件显示 `?`，不扣分。
- 扫描结果标签里有"基本面"开关，可以按 EPS / 营收同比阈值过滤。
- 7 天内要出财报的票会标黄色 ⚠。

## 新闻 & 公告

右侧面板"新闻 & 公告"区块合并三个免费来源，缓存 30 分钟：

- **Yahoo Finance**（走 yfinance，只保留标题提到该公司的）
- **Google News RSS**（按代码 + 公司名搜索，覆盖最广）
- **SEC EDGAR 8-K 公告**（官方；Item 2.02 = 财报，1.01 = 重大协议，5.02 = 高管变动）

标题按关键词打标签：财报、评级、并购、合同/产品、监管/诉讼、高管/内部、公告，可按标签筛选。发生在买卖信号 ±1.5 天内的新闻会标"↔ 信号"，方便判断突破或跳空是否有催化剂（Kullamägi 的 EP 尤其看这个）。8-K 公告和财报类新闻同时在 K 线上方用小圆点标出。

策略代码在 `backend/app/strategies/`，每个文件顶部有规则说明，阈值都是普通常量，可以直接改。

J Law 的规则是根据他公开访谈整理的**个人解读**（M.E.T.S. 课程内容未公开），不是官方规则。

## 回测

右侧面板"回测"按钮：近 3 年、全仓进出、入场当日收盘买入、止损按策略、止损/卖出信号/移动止盈三种离场。命令行批量评估：

```bash
cd backend && .venv/bin/python tools/eval.py            # 五个策略 × 30 只票
cd backend && .venv/bin/python tools/eval.py jlaw -v    # 单个策略，显示每只票
```

### 当前版本回测参考（30 只大中盘股 × 近 3 年，2026-09-14 计算）

| 策略 | 交易数 | 胜率 | 平均 R | 平均盈利 | 平均亏损 | 盈亏比 PF |
|---|---|---|---|---|---|---|
| Minervini | 59 | 34% | 0.64 | +27.3% | -7.1% | 1.98 |
| Weinstein | 28 | 39% | 0.65 | +69.5% | -14.3% | 3.14 |
| Kullamägi | 103 | 36% | 0.77 | +20.3% | -4.6% | 2.46 |
| Kell | 481 | 40% | 0.30 | +11.5% | -4.8% | 1.60 |
| J Law | 51 | 25% | 0.32 | +20.6% | -4.8% | 1.47 |

这是"信号本身"的粗略质量，不含分批止盈、仓位管理，样本也只有 30 只票，只用来比较规则改动前后的好坏，不代表实盘预期。

## 扫描

左侧"扫描结果"标签 → "扫描 S&P500 + NDX100"。首次约 1-2 分钟（下载 520 只票 3 年日线），之后约 30 秒。扫描同时计算 RS 相对强度排名（IBD 式：2×3月 + 6月 + 9月 + 12月收益的百分位）和板块排名，Minervini / J Law 的 RS 条件依赖它。

## 接口

- `GET /api/stock/{symbol}?strategy=jlaw` K 线 + 策略结果 + 五策略概览
- `GET /api/backtest/{symbol}?strategy=kell`
- `GET /api/scan?strategy=minervini&min_score=60`，`POST /api/scan/run`
- `GET /api/watchlist`，`POST/DELETE /api/watchlist/{symbol}`
- `GET /api/market` 大盘状态（SPY/QQQ 均线位置、Stage、市场宽度）
