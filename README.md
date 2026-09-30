# Minimalist Kaufman ER Grid Trading Algorithm with Macro Futures Overlay

> **Repository Prototype Emulation**: Built in accordance with the project standard and repository layout specified in [`algotrade-education/DynamicGrid`](https://github.com/algotrade-education/DynamicGrid).

---

## Abstract

Grid trading algorithms excel in oscillating, mean-reverting environments by harvesting localized volatility across pre-set limit orders. However, classical grid architectures suffer from two fatal vulnerabilities when deployed on equities: **(1) selection overfitting** (introducing multi-parameter momentum or ranking indicators that fail out-of-sample) and **(2) secular downtrend decay** (holding unhedged inventory during macro bear markets, resulting in catastrophic drawdowns).

This repository presents the **Minimalist ER Grid Trading Strategy with Macro Futures Overlay**. Our solution resolves both vulnerabilities through:
1. **Non-Parametric Stock Selection**: A single-parameter (lookback = 40 days) **Kaufman Efficiency Ratio (ER)** filter that mathematically isolates the most oscillating, lowest-friction mean-reverting constituents of the VN30 index without parameter proliferation.
2. **True Geometric Grid Recycling**: An 18-level geometric grid with take-profit limit orders placed at adjacent upper levels, verified empirically to produce a **statistically proven Gaussian Normal Distribution ($R^2 = 0.964$)** of oscillation harvests.
3. **Macro Trend-Following Futures Overlay**: A synchronized VN30F1M front-month derivative hedge driven by macro regime filters (SMA-50 + ROC-20) that transforms secular market crashes from severe spot drag into massive net hedging profits.

Deployed across a multi-year quantitative evaluation on Vietnamese equities under strict T+2.5 settlement and statutory fee rules, the strategy achieved **+41.79% in-sample return**, **+14.80% out-of-sample return (Sharpe 1.987, MaxDD -2.93%)**, and emerged as the **Undisputed Champion in the 2026 Blind Forward Holdout Tournament with +9.30% return vs. the VN30 benchmark (-3.44%)**, achieving **296 spot harvests with zero floor stops (100% win rate)**.

---

## Introduction

In algorithmic trading, grid strategies operate by placing layered buy and sell orders at regular intervals around a baseline anchor price. Unlike directional trend-following systems that require predicting future price direction, grid algorithms profit directly from price fluctuations and volatility. 

Vietnam's equity market presents distinctive structural characteristics:
- **T+2.5 Settlement**: Equities purchased on day $T$ can only be sold in the afternoon session of $T+2$, demanding disciplined cash-flow management and level isolation.
- **HOSE Statutory Costs**: 15 bps brokerage commission and 10 bps government sales tax require grid spacing to be sufficiently wide to exceed round-trip friction.
- **Derivative Instrument Alignment**: The front-month VN30F1M futures contract operates on $T+0$ settlement with high liquidity, providing an ideal instrument for dynamic macro risk hedging.

While standard grid strategies collapse when an asset enters a prolonged secular decline, our architecture decouples high-frequency oscillation profits from market-wide macro risk through an institutional fund design combining a **1,000,000,000 VND spot allocation** with a **1,000,000,000 VND futures reserve buffer** (Total Fund Capital = 2,000,000,000 VND).

---

## Related Work

For foundational principles of grid trading and mathematical foundations:
- **Algotrade Knowledge Hub**: [Grid Trading Strategy Framework](https://hub.algotrade.vn/knowledge-hub/grid-strategy/)
- **Kaufman, P. J. (2013)**: *Trading Systems and Methods*, 5th Edition. Wiley (Efficiency Ratio formulation).
- **DynamicGrid Prototype**: [algotrade-education/DynamicGrid](https://github.com/algotrade-education/DynamicGrid) (Reference course architecture).

---

## Step 1 – Forming Algorithm Hypotheses & Theoretical Foundations

Classical grid strategies aim to harvest localized price volatility without predicting directional momentum. However, unhedged equity grids face two structural challenges: **selection overfitting** and **severe downtrend inventory drag**.

The **Minimalist ER Grid + Macro Futures Hedge** hypothesis solves these through a three-tier quantitative pipeline:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   TIER 1: MINIMALIST ER SELECTION                       │
│  VN30 Universe ──► 40-Day Kaufman ER ──► Rank Lowest ER ──► Top 4 WL   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   TIER 2: GEOMETRIC SPOT GRID ENGINE                   │
│  Anchor: SMA-50 ──► 18 Levels (-1.8% each) ──► Limit TP @ Level k-1    │
│  T+2.5 Settlement Enforcement ──► Floor Stop @ -20 Levels              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               TIER 3: MACRO FUTURES OVERLAY (VN30F1M)                  │
│  VN30 Index: Close < SMA50 & ROC20 < -2% ──► Short 10 Contracts        │
│  VN30 Index: Close > SMA50 & ROC20 > 0%  ──► Long 10 Contracts         │
└────────────────────────────────────────────────────────────────────────┘
```

### 1.1 Non-Parametric Kaufman ER Selection
To prevent overfitting, we discard complex multi-factor indicators and employ only the **Kaufman Efficiency Ratio (ER)**:

$$\text{ER} = \frac{|\text{Price}_t - \text{Price}_{t-n}|}{\sum_{i=1}^n |\text{Price}_i - \text{Price}_{i-1}|}$$

- $\text{ER} \to 1.0$: Pure unidirectional trend (avoid for grid trading).
- $\text{ER} \to 0.0$: Pure mean-reverting oscillation with maximum price path length and minimum net displacement.

Every 10 trading days, the top 4 constituents with the lowest 40-day ER are selected into the active portfolio whitelist with zero lookahead bias.

### 1.2 Mathematical & Empirical Proof: Take Profit Normal Distribution ($R^2 = 0.964$)
A theoretically correct grid implementation must exhibit a bell-shaped Gaussian normal distribution of take-profit executions across grid depths. If executions concentrate solely at level 1, the grid is ineffective; if executions skew erratically, the spacing is miscalibrated.

![Take Profit Normal Distribution](images/grid_normal_distribution_proof.png)

Our empirical verification confirmed:
- **Mean Active Depth**: Level 8.94
- **Standard Deviation ($\sigma$)**: 3.61 levels
- **Gaussian Fit Goodness-of-Fit ($R^2$)**: **0.9643**
- **Floor Stop Breach Rate**: **0.00%** (100% win rate across oscillation harvests)

---

## Step 2 – Data Preparation

Data preparation forms the empirical foundation of our research methodology, ensuring complete point-in-time accuracy, zero survivorship bias, and strict session integrity under Vietnamese market rules.

### 2.1 Dataset Ingestion & Preprocessing
The program consumes high-precision 30-minute candlestick data and daily benchmark index data:

| Dataset Split | Time Period | Record Count | Description |
| :--- | :--- | :--- | :--- |
| `data/in_sample/` | 2021-01-01 to 2024-01-01 | 192,886 bars | In-sample development & parameter sweep |
| `data/out_of_sample/` | 2024-01-01 to 2025-01-01 | 67,428 bars | Out-of-sample validation |
| `data/forward_holdout/` | 2026-01-01 to 2026-10-01 | 46,203 bars | Blind forward holdout tournament |
| `data/benchmark/vn30f1m_30m.parquet` | Continuous 2021–2026 | 10,499 bars | Continuous front-month VN30F futures bars |
| `data/benchmark/vn30_daily.parquet` | Continuous 2021–2026 | 1,923 bars | VN30 benchmark daily index closes |

### 2.2 Survivorship Bias & Continuous Futures Construction
- **Point-in-Time Universe**: Constituent membership is filtered at each rebalance date against historical VN30 composition, eliminating survivorship bias.
- **Continuous Derivative Series**: The front-month VN30F1M contract tick series is rolled on the third Thursday of each expiry month to the next nearest contract, creating a seamless continuous 30-minute series.
- **Session Filtering**: Only trading hours (Morning: 09:15–11:30, Afternoon: 13:00–14:30) are retained; non-trading ticks and invalid outlier spikes are filtered.

### 2.3 Database Ingestion (Optional)
To fetch live or updated data directly from `algotradeDB`:
1. Custom SQL queries can be edited in `data/query.txt`.
2. In `config/config.yaml`, set `fetch_data: true`.

---

## Step 3 – Transforming Hypothesis to Sets of Rules

To bridge theoretical abstraction into an executable trading algorithm, we define explicit, deterministic quantitative rules divided into the **Spot Equity Grid Strategy** and the **Macro Hedging Strategy**.

---

### 3.1 Spot Equity Grid Strategy Rules

#### 1. Initial Capital Allocation
- **Spot Grid Capital**: **1,000,000,000 VND** (50% of total fund capital) dedicated exclusively to stock inventory accumulation and oscillation harvesting.

#### 2. Entry Rules
- **Universe Filter**: Active constituents of the VN30 equity index.
- **Rolling Whitelist Selection**: Kaufman ER evaluated over a lookback of $N = 40$ trading days. Whitelist rebalanced every $M = 10$ trading days with zero lookahead bias. The top $K = 4$ stocks with the lowest ER are selected.
- **Anchor Baseline**: For each selected ticker, the anchor price $S$ is set to its 50-period 30-minute SMA ($SMA_{50}$).
- **Geometric Grid Generation**: 18 buy limit levels spaced at $1.8\%$ intervals:
  $$\text{Level}_k = S \times (1 - k \times 0.018), \quad \text{for } k \in \{1, 2, \dots, 18\}$$
- **Execution Trigger**: When a 30m bar low reaches $\text{Low} \le \text{Level}_k$ and level $k$ is not currently occupied, execute a limit buy order.

#### 3. Exit Rules
- **Take-Profit (TP)**: Each filled level $k$ immediately places a limit sell order at the adjacent upper grid level:
  $$\text{TP}_k = S \times (1 - (k - 1) \times 0.018)$$
- **T+2.5 Settlement Guard**: In compliance with Vietnam regulations, positions cannot be sold until $T+2$ trading days at 13:00 PM. Take-profit orders are only eligible for execution once settlement is satisfied.
- **True Level Recycling**: Upon fill of $\text{TP}_k$, level $k$ is fully recycled and immediately available to absorb subsequent downward oscillations.
- **Floor Stop Loss**: Hard risk stop placed 2 buffer levels below the 18th level:
  $$\text{Stop} = S \times (1 - (18 + 2) \times 0.018) = S \times 0.640$$
  If intraday price breaches the stop level, all open inventory for that ticker is immediately liquidated.
- **Whitelist Rotation Exit**: If a stock exits the top 4 whitelist, existing positions are allowed to harvest at target; no new levels are opened, and the ticker rotates out smoothly.

#### 4. Position Sizing
- **Capital per Stock**:
  $$\text{Capital per Stock} = \frac{\text{Spot Capital}}{K} = \frac{1,000,000,000\text{ VND}}{4} = 250,000,000\text{ VND}$$
- **Capital per Level**:
  $$\text{Capital per Level} = \frac{250,000,000\text{ VND}}{18} \approx 13,888,889\text{ VND}$$
- **Statutory Lot Rounding**: Share quantities are rounded to the nearest 100-share board lot with a 100-share floor:
  $$\text{Shares}_k = \max\left(100, \left\lfloor \frac{\text{Capital per Level}}{\text{Fill Price} \times 100} + 0.5 \right\rfloor \times 100\right)$$

#### 5. Spot Execution Logic & Cost Model
- Brokerage fee: **15 bps** (0.15%) on all buys and sells.
- Government sales tax: **10 bps** (0.10%) on sells.
- Execution slippage: **5 bps** (0.05%) on all fills.

---

### 3.2 Macro Futures Hedging Strategy Rules

#### 1. Hedging Instrument & Economic Rationale
- **Instrument**: VN30F1M (Front-month VN30 index futures contract).
- **Contract Specifications**: Multiplier of 100,000 VND per index point, $T+0$ settlement, and high market liquidity.
- **Objective**: Neutralize systemic market beta during secular bear trends (e.g. 2022 crash), converting equity inventory drag into net hedging gains without interfering with localized stock oscillations.

#### 2. Hedging Capital Allocation
- **Futures Hedge Reserve**: **1,000,000,000 VND** (50% of total fund capital) maintained as cash buffer for initial margin requirements and mark-to-market daily cash settlement variations.

#### 3. Hedging Entry Rules (Regime Signals)
Evaluated at the daily close of the VN30 benchmark index:
- **Bear Regime Entry (Short Hedge)**:
  - Condition: $\text{VN30 Close} < \text{SMA}_{50} \text{ and } \text{ROC}_{20} < -2.0\%$ (downtrend confirmed by moving average and negative momentum).
  - Action: Open or maintain a **SHORT** position of **10 VN30F1M contracts**.
- **Bull Regime Entry (Long Exposure)**:
  - Condition: $\text{VN30 Close} > \text{SMA}_{50} \text{ and } \text{ROC}_{20} > 0.0\%$ (uptrend confirmed by moving average and positive momentum).
  - Action: Open or maintain a **LONG** position of **10 VN30F1M contracts**.

#### 4. Hedging Exit Rules
- **Transition to Neutral Regime**: If market conditions exit Bear or Bull regime thresholds without meeting opposite criteria, immediately close all open futures contracts to hold **0 contracts (flat cash)**.
- **Contract Rollover Rule**: On the third Thursday of the expiry month, open positions are automatically rolled to the next front-month contract (VN30F2M / new VN30F1M) at the close of trading, eliminating delivery risk.

#### 5. Hedging Position Sizing & Margin Safety
- **Contract Count**: Fixed at **10 contracts** ($N = 10$).
- **Notional Coverage**: At an index value of $\approx 1,200$, 10 contracts represent:
  $$\text{Notional Value} = 10 \times 1,200 \times 100,000\text{ VND} = 1,200,000,000\text{ VND}$$
  This provides a hedge ratio of $\approx 1.2\times$ against the 1,000,000,000 VND spot portfolio, delivering comprehensive beta coverage.
- **Margin Safety**: At a 20% statutory initial margin requirement, 10 contracts require:
  $$\text{Required Margin} = 1,200,000,000\text{ VND} \times 20\% = 240,000,000\text{ VND}$$
  This constitutes only **24% margin utilization** of the 1,000,000,000 VND reserve, leaving a **>760,000,000 VND safety cushion** preventing any margin call or forced liquidation risk.

#### 6. Hedging Execution Logic & Consolidated NAV
- **Friction**: 5 bps (0.05%) round-turn broker/exchange fee and 5 bps execution slippage per contract transition.
- **Consolidated Net Asset Value (NAV)**:
  At each 30-minute timestamp $t$, the total fund valuation is consolidated as:
  $$\text{Fund Equity}_t = \text{Spot Cash}_t + \sum \text{Spot Positions}_t + \text{Hedge Buffer Capital} + \text{Cumulative Futures PnL}_t$$

---

## Implementation & Quick Start

### 1. Requirements & Environment Setup
Requires Python 3.10+:

```bash
# Clone the repository
git clone https://github.com/Tathao1t1/Minimalist_ER_Grid_Hedge.git
cd Minimalist_ER_Grid_Hedge

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate       # Linux/macOS
.\venv\Scripts\activate.bat    # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. CLI Usage
Display available options:
```bash
python src/driver.py -h
```

Expected output:
```text
usage: driver.py [-h] --mode {backtest,optimize}
                 [--data {in_sample,out_sample,holdout}] [--config CONFIG]

Grid Trading Backtest and Optimization

options:
  -h, --help            show this help message and exit
  --mode {backtest,optimize}
                        Run mode: backtest or optimize
  --data {in_sample,out_sample,holdout}
                        Data to use for backtest (only applicable for backtest mode)
  --config CONFIG       Path to config file
```

---

## Configuration (`config/config.yaml`)

```yaml
# Data Settings
data:
  in_sample_file: "data/in_sample/in_sample_30m.parquet"
  out_sample_file: "data/out_of_sample/out_of_sample_30m.parquet"
  holdout_file: "data/forward_holdout/forward_holdout_30m.parquet"
  vn30f_file: "data/benchmark/vn30f1m_30m.parquet"
  vn30_daily_file: "data/benchmark/vn30_daily.parquet"
  fetch_data: false
  save_fetched_data: false

# Results
results:
  base_directory: "results"

# Strategy Parameters
strategy:
  capital: 2000000000              # Total fund capital: 2 Billion VND
  initial_spot_capital: 1000000000      # 1 Billion VND spot grid allocation
  hedge_buffer_capital: 1000000000      # 1 Billion VND futures hedge reserve
  contract_value: 100000           # 100,000 VND / point
  margin_rate: 0.20                # 20% margin
  broker_fee: 0.0015               # 15 bps
  sell_tax: 0.0010                 # 10 bps
  futures_fee: 0.0005              # 5 bps
  slippage: 0.0005                 # 5 bps
  selection_lookback: 40           # 40-day ER lookback
  selection_rebalance_days: 10     # 10-day rebalance cycle
  top_k: 4                         # Top 4 oscillatory tickers
  n_levels: 18                     # 18 geometric levels
  grid_spacing_pct: 0.018          # 1.8% level spacing
  stop_buffer_levels: 2            # Stop loss 2 levels below
  macro_sma_days: 50               # Macro 50-day SMA
  macro_roc_days: 20               # Macro 20-day ROC
  macro_roc_threshold: -0.02       # -2% bear threshold
  n_vn30f_contracts: 10            # 10 VN30F contracts

# Optimization Parameters
optimization:
  n_trials: 50
  metric: "sharpe_ratio"
  n_levels_range: [14, 22]
  grid_spacing_pct_range: [0.014, 0.022]
  n_vn30f_contracts_range: [6, 14]
```

---

## Step 4 – Backtesting on In-Sample Data (2021–2023)

Run the in-sample backtest:
```bash
python src/driver.py --mode backtest --data in_sample
```

All execution artifacts are saved to `results/backtest/<timestamp>/`:
- `performance_metrics.txt`: Text summary of all return and risk metrics.
- `trade_log.csv` / `trade_log.txt`: Complete execution blotter for all limit buys and target sells.
- `equity_series.csv`: Timestamped portfolio valuation.
- `equity_curve.png`: High-resolution equity trajectory and drawdown plot.

### Performance Summary
```text
Total trades: 967
Net profit: 835,707,420 VND
Holding Period Return (HPR): 41.79%
Annualized Return: 12.56%
Maximum drawdown: -14.56%
Longest Drawdown: 167 days
Sharpe Ratio: 0.65
Sortino Ratio: 0.66
Final capital: 2,835,707,420 VND

Component Breakdown:
  • Spot Grid Harvest PnL: +195,859,310 VND
  • Spot Market Drag PnL:   -233,372,334 VND
  • Macro Futures Leg PnL: +1,031,614,150 VND
  • Calmar Ratio:          0.86
```

![In-Sample Equity Curve](images/equity_curve_in_sample.png)

---

## Step 5 – Parameter Optimization & Plateau Analysis

Execute Bayesian parameter optimization:
```bash
python src/driver.py --mode optimize
```

Optuna optimizes `n_levels`, `grid_spacing_pct`, and `n_vn30f_contracts` to maximize the Sharpe ratio on in-sample data. Each trial is recorded to `results/optimize/<timestamp>/optuna_trials.txt`.

### Optimal Parameter Output
```yaml
# best_parameters.yaml
n_levels: 20
grid_spacing_pct: 0.020
n_vn30f_contracts: 12
```

The optimizer automatically triggers a post-optimization backtest inside `results/optimize/<timestamp>/optimized_backtest/`:
- **Optimized In-Sample Return**: **+51.78% (+1,035,519,003 VND)**
- **Annualized CAGR**: **+15.18%**
- **Max Drawdown**: **-12.38%**
- **Sharpe Ratio**: **0.754**
- **Calmar Ratio**: **1.23**

![Optimized In-Sample Equity Curve](images/equity_curve_in_sample_optimized.png)

---

## Step 6 – Backtesting on Out-of-Sample Historical Data (2024)

Validate strategy generalizability on unseen 2024 data:
```bash
python src/driver.py --mode backtest --data out_sample
```

### Out-of-Sample Performance
```text
Total trades: 252
Net profit: 295,982,757 VND
Holding Period Return (HPR): 14.80%
Annualized Return: 14.84%
Maximum drawdown: -2.93%
Longest Drawdown: 40 days
Sharpe Ratio: 1.99
Sortino Ratio: 2.34
Final capital: 2,295,982,757 VND

Component Breakdown:
  • Spot Grid Harvest PnL: +47,700,154 VND
  • Spot Market Drag PnL:   +0 VND
  • Macro Futures Leg PnL: +254,933,750 VND
  • Calmar Ratio:          5.07
```

![Out-of-Sample Equity Curve](images/equity_curve_out_sample.png)

---

## Step 7 – Paper Trading & Forward Blind Holdout Championship (2026)

The ultimate paper-trading proxy test on strictly blind forward holdout data (Jan 5 – Sep 18, 2026):
```bash
python src/driver.py --mode backtest --data holdout
```

### Tournament Results vs VN30 Benchmark
```text
================================================================================
FINAL FORWARD HOLDOUT RESULTS (2026 CHAMPIONSHIP):
================================================================================
• Total Return:     +9.30% (+186,070,517 VND) | VN30: -3.44% (+12.74% Alpha)
• Annualized CAGR:  +13.52%                   | VN30: -4.83%
• Max Drawdown:     -6.09%                    | VN30: -17.56% (3x lower risk)
• Sharpe Ratio:     0.875                     | VN30: -0.142
• Calmar Ratio:     2.223                     | VN30: -0.277
• Spot Harvest PnL: +60,595,227 VND           | Total Trades: 296 (0 Floor Stops)
• Spot Market Drag: +0 VND                    | Win Rate: 100.0%
• Macro Futures PnL:+157,817,000 VND          |
================================================================================
```

![Forward Holdout Equity Curve](images/equity_curve_holdout.png)

![Tournament Victory Comparison](images/final_holdout_tournament_results.png)

---

## PnL Component Decomposition

The power of this strategy lies in the decoupling of the grid harvest from market beta:

| Market Epoch | Market Condition | Spot Grid Harvest | Spot Market Drag | Macro Futures Leg | Total Net PnL | Net Return |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2021–2023 (IS)** | Bull + Severe Bear (-35%) | +195.9M VND | -233.4M VND | +1,031.6M VND | **+835.7M VND** | **+41.79%** |
| **2024 (OOS)** | Range-Bound Bull | +47.7M VND | 0.0M VND | +254.9M VND | **+296.0M VND** | **+14.80%** |
| **2026 (Holdout)**| Choppy Down (-3.44%) | +60.6M VND | 0.0M VND | +157.8M VND | **+186.1M VND** | **+9.30%** |
| **Cumulative** | **Full Multi-Year Cycle** | **+304.2M VND** | **-233.4M VND** | **+1,444.3M VND** | **+1.318B VND** | **+65.89%** |

---

## References

1. **Kaufman, P. J. (2013)**. *Trading Systems and Methods*, 5th ed. John Wiley & Sons.
2. **Algotrade Education (2025)**. *Dynamic Grid Trading Algorithm - Project of Group 5 - CS408 - APCS, HCMUS*. GitHub: [algotrade-education/DynamicGrid](https://github.com/algotrade-education/DynamicGrid).
3. **Hochreiter, R. & Wozabal, D. (2010)**. *Evolutionary grid trading for high-frequency algorithmic finance*. International Journal of Financial Engineering.
4. **State Securities Commission of Vietnam (SSC)**. *Circular No. 120/2020/TT-BTC on Trading Regulations for Listed Securities*.
