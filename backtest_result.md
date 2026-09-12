# 📊 Quant Momentum Strategy — Backtest Results

> **From Date:** January 1, 2024
> **As of Date:** September 12, 2026  
> **Backtest Engine:** `backtest_mom3v1.py`  
> **Universe:** Nifty 500 (`EQ` Series)

---

## 🚀 Performance Overview

| Strategy Metric | Value |
| :--- | :---: |
| **Initial Capital** | **₹1,50,000.00** |
| **Final Portfolio Value** | **₹2,25,836.31** |
| **Strategy Total Return** | **+50.56%** |
| **Max Drawdown (MDD)** | **-25.07%** |
| **Win Rate** | **41.8%** |
| **Total Closed Trades** | **282** |

---

## 🎯 Benchmark Return Comparison

| Index / Asset | Total Return (%) | Excess Alpha vs Benchmark |
| :--- | :---: | :---: |
| 🚀 **Quant Momentum Strategy** | **+50.56%** | **—** |
| 📈 **Nifty Midcap 100** | **+35.18%** | **+15.38%** |
| 📊 **Nifty 500** | **+17.69%** | **+32.87%** |
| 📉 **Nifty 50** | **+7.62%** | **+42.94%** |

---

## ⚙️ Execution Rules & Guardrails

* **Target Allocation**: Concentrated 10-stock portfolio (~10% allocation per slot).
* **Trailing Stop Loss**: Daily dynamic exit at `3.5x ATR` below the highest peak price.
* **Rank Decay Exit**: Weekly liquidation for active holdings dropping below `Rank 25`.
* **Friction & Costs**: Includes `0.15%` buy slippage and `0.15%` sell slippage per trade side.
