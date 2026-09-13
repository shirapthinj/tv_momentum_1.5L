# ⚡ Quantitative Momentum Strategy Documentation

> **Universe:** Nifty 500 (`EQ` Series)  
> **Execution Frequency:** Weekly Rebalance & Daily Exit Evaluation  
> **Target Portfolio:** 10 Equal-Weighted Positions (~10% capital per slot)

---

## 🎯 Universe & Baseline Eligibility Filters

Before ranking, stocks in the Nifty 500 universe must satisfy all baseline technical, liquidity, and execution filters:

* **Security Series**: Strictly `EQ` series equities (excludes illiquid or restricted BE, BZ, SM, and ST series).
* **Price Floor**: Stock price $\ge ₹20.00$.
* **Liquidity Floor**: Daily traded value $\ge ₹5\text{ Crore}$ to prevent illiquidity drag.
* **Structural Uptrend**: Daily close price $> 200\text{-Day Simple Moving Average (SMA)}$.
* **Relative Benchmark Outperformance**: 3-Month return must beat the Nifty 500 Index ($\text{Alpha}_{3M} > 0$).
* **Circuit Lock Guard**: Rejects stocks where $\text{High} == \text{Low}$ (zero price discovery / upper-circuit locks) or $\text{ATR}_{\%} < 0.8\%$ to eliminate unfillable orders.

---

## 📊 Quantitative Ranking & Composite Score Formula

All qualified candidates are scored and ranked using a composite factor formula that balances multi-horizon momentum, volatility adjustment, and proximity to 52-week highs:

$$\text{Score} = \left( \frac{0.6 \cdot R_{6M} + 0.4 \cdot R_{12M}}{\max(\text{ATR}_{\%}, 0.5)} \right) \times \left( \frac{\text{Price}}{\text{52W High}} \right)^4$$

### Scoring Component Breakdown
* **Smooth Momentum Horizon ($0.6 \cdot R_{6M} + 0.4 \cdot R_{12M}$)**: Combines 6-month ($R_{6M}$) and 12-month ($R_{12M}$) returns to reward sustained trend strength over single-month spikes.
* **Volatility Adjustment ($\text{ATR}_{\%}$)**: Normalizes returns by dividing by 14-day Average True Range percentage, penalizing erratic micro-cap volatility.
* **Exponential 52-Week High Factor ($\left(\frac{\text{Price}}{\text{52W High}}\right)^4$)**: Exponentially boosts stocks trading at or near 52-week highs to capture immediate breakout momentum.

---

## 🛡️ Risk Management & Exit Architecture

Positions are managed via two distinct exit triggers to protect capital during market downturns while letting winners run:

### 1. Dynamic Trailing Stop Loss (Daily Check)
* Evaluated every daily close.
* Exit is triggered if current price falls $3.5 \times \text{ATR}_{14}$ below the highest peak price achieved while holding the stock:
$$\text{Stop Price} = \text{Peak Price} - (3.5 \times \text{ATR}_{14})$$

### 2. Rank Decay Exit (Weekly Check)
* Evaluated during weekly rebalancing scans.
* Active holdings are liquidated if their strategy rank drops below **Rank 25** (`Current Rank > 25`).
* Capital freed from decayed positions is recycled into new **Top 10** candidates.

---

## 💸 Transaction Costs & Friction Parameters

To ensure backtested performance matches live market execution, all trade legs factor in realistic friction and slippage:

* **Buy Execution Price**: $\text{Entry Price} \times 1.0015$ (0.15% buy slippage)
* **Sell Execution Price**: $\text{Exit Price} \times 0.9985$ (0.15% sell slippage)
