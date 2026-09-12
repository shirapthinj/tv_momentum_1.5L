import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from tradingview_ta import TA_Handler, Interval

# SYSTEM CONFIGURATION ALIGNED STRICTLY WITH backtest_mom3v1.py
INITIAL_CAPITAL = 150000.0     # ₹1.5 Lakhs Initial Capital
TARGET_POSITIONS = 10          # 10 slots (10% capital per position)
MAX_HOLD_RANK = 25             # Rank Decay Cutoff (Top 25)
ATR_MULTIPLIER = 3.5           # 3.5x ATR Dynamic Trailing Stop
MIN_TURNOVER = 50000000        # ₹5 Crore Daily Turnover Floor
MIN_STOCK_PRICE = 20.0         # ₹20 Minimum Stock Price Floor

SLIPPAGE_BUY = 1.0015          # 0.15% Buy Slippage
SLIPPAGE_SELL = 0.9985         # 0.15% Sell Slippage

PORTFOLIO_FILE = "portfolio.json"
TRADE_LOG_FILE = "trade_log.csv"
PERFORMANCE_FILE = "performance_history.csv"
CURRENT_HOLDINGS_FILE = "current_holdings.csv"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def init_csv_files():
    if not os.path.exists(TRADE_LOG_FILE):
        pd.DataFrame(columns=[
            'Ticker', 'Entry Date', 'Entry Price', 'Exit Date', 'Exit Price', 'Return (%)', 'Holding Days', 'Exit Reason'
        ]).to_csv(TRADE_LOG_FILE, index=False)

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram send error: {e}")

def get_latest_market_date():
    now = datetime.now()
    if now.weekday() == 5:
        market_dt = now - timedelta(days=1)
    elif now.weekday() == 6:
        market_dt = now - timedelta(days=2)
    else:
        market_dt = now
    return market_dt.strftime('%Y-%m-%d')

def get_tv_single_data(symbol_candidates):
    if isinstance(symbol_candidates, str):
        symbol_candidates = [symbol_candidates]

    configs = [
        {"screener": "india", "exchange": "NSE"},
        {"screener": "india", "exchange": "INDEX"},
        {"screener": "cfd", "exchange": "INDEX"}
    ]

    for sym in symbol_candidates:
        for cfg in configs:
            try:
                handler = TA_Handler(
                    symbol=sym,
                    screener=cfg["screener"],
                    exchange=cfg["exchange"],
                    interval=Interval.INTERVAL_1_DAY
                )
                ind = handler.get_analysis().indicators
                close_val = float(ind.get('close', 0.0))
                if close_val > 0:
                    atr = float(ind.get('ATR', 0.0))
                    atr_pct = (atr / close_val * 100) if close_val > 0 else 2.0
                    return {
                        'close': close_val,
                        'sma200': float(ind.get('SMA200', 0.0)),
                        'high52w': float(ind.get('price_52_week_high', close_val)),
                        'atr14': atr,
                        'atr_pct': atr_pct,
                        'perf_3m': float(ind.get('Perf.3M', 0.0)),
                        'perf_6m': float(ind.get('Perf.6M', 0.0)),
                        'perf_12m': float(ind.get('Perf.Y', 0.0))
                    }
            except Exception:
                continue
    return None

def scan_tv_universe():
    url = "https://scanner.tradingview.com/india/scan"
    payload = {
        "filter": [
            {"left": "exchange", "operation": "equal", "right": "NSE"},
            {"left": "type", "operation": "in_range", "right": ["stock", "dr"]}
        ],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": [
            "name", "close", "SMA200", "price_52_week_high",
            "Perf.3M", "Perf.6M", "Perf.Y", "ATR", "Value.Traded"
        ],
        "sort": {"sortBy": "Perf.3M", "sortOrder": "desc"},
        "range": [0, 500]
    }
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        if res.status_code == 200:
            candidates = []
            for item in res.json().get('data', []):
                cols = item.get('d', [])
                if len(cols) >= 9:
                    name, close, sma200, h52w, r3m, r6m, r12m, atr, turnover = cols[:9]
                    if not close or close < MIN_STOCK_PRICE or not turnover or turnover < MIN_TURNOVER:
                        continue
                    if not sma200 or close <= sma200:
                        continue

                    atr_val = float(atr or 0.0)
                    atr_pct = (atr_val / float(close) * 100) if close > 0 else 2.0
                    candidates.append({
                        'symbol': f"{name}.NS",
                        'close': float(close),
                        'sma200': float(sma200),
                        'high52w': float(h52w or close),
                        'perf_3m': float(r3m or 0.0),
                        'perf_6m': float(r6m or 0.0),
                        'perf_12m': float(r12m or 0.0),
                        'atr14': atr_val,
                        'atr_pct': atr_pct
                    })
            return candidates
    except Exception as e:
        print(f"Scanner fetch error: {e}")
    return []

def run_scanner():
    init_csv_files()
    with open(PORTFOLIO_FILE, "r") as f:
        state = json.load(f)

    cash = state.get("cash", INITIAL_CAPITAL)
    holdings = state.get("holdings", {})
    last_week = state.get("last_week", None)
    
    dt = datetime.now()
    dt_str = get_latest_market_date()
    current_week = dt.isocalendar()[1]
    is_rebalance_day = (last_week is None) or (current_week != last_week)

    sell_signals, buy_signals, closed_trades = [], [], []

    # 1. DAILY EXIT EVALUATION (3.5x ATR Trailing Stop)
    retained_holdings = {}
    for stock, pos in list(holdings.items()):
        clean_sym = stock.replace('.NS', '')
        data = get_tv_single_data(clean_sym)
        if not data or data['close'] <= 0:
            retained_holdings[stock] = pos
            continue

        cur_p = data['close']
        pos['peak_price'] = max(pos.get('peak_price', cur_p), cur_p)
        atr = data['atr14']

        stop_price = pos['peak_price'] - (ATR_MULTIPLIER * atr) if atr > 0 else pos['peak_price'] * 0.85

        if cur_p < stop_price:
            exit_price = cur_p * SLIPPAGE_SELL
            proceeds = pos['shares'] * exit_price
            cash += proceeds
            ret_pct = ((exit_price - pos['entry_price']) / pos['entry_price']) * 100
            days_held = (pd.to_datetime(dt_str) - pd.to_datetime(pos['entry_date'])).days

            sell_signals.append(f"🔴 *SELL (3.5x ATR Stop):* `{clean_sym}` @ ₹{exit_price:,.2f} ({ret_pct:+.2f}%)")
            closed_trades.append({
                'Ticker': clean_sym,
                'Entry Date': pos['entry_date'],
                'Entry Price': round(pos['entry_price'], 2),
                'Exit Date': dt_str,
                'Exit Price': round(exit_price, 2),
                'Return (%)': round(ret_pct, 2),
                'Holding Days': days_held,
                'Exit Reason': f"{ATR_MULTIPLIER}x ATR Trailing Stop"
            })
        else:
            retained_holdings[stock] = pos

    holdings = retained_holdings

    # 2. WEEKLY REBALANCING & RANK DECAY EVALUATION
    tv_n500 = get_tv_single_data(['CNX500', 'NIFTY500'])
    n500_3m = tv_n500['perf_3m'] if tv_n500 else 0.0

    if is_rebalance_day:
        candidates = scan_tv_universe()
        scored_candidates = []

        for item in candidates:
            stk = item['symbol']
            p = item['close']
            h52w = item['high52w']
            alpha_3m = item['perf_3m'] - n500_3m

            if alpha_3m > 0 and h52w > 0:
                smooth_mom = (0.6 * item['perf_6m']) + (0.4 * item['perf_12m'])
                vol_adj_mom = smooth_mom / max(item['atr_pct'], 0.5)
                high_proximity = (p / h52w) ** 4
                score = vol_adj_mom * high_proximity
                scored_candidates.append({'ticker': stk, 'price': p, 'score': score})

        if scored_candidates:
            cand_df = pd.DataFrame(scored_candidates).sort_values(by='score', ascending=False).reset_index(drop=True)
            cand_df['rank'] = cand_df.index + 1
            rank_lookup = dict(zip(cand_df['ticker'], cand_df['rank']))

            # Rank Decay Exit (> Rank 25)
            for stock, pos in list(holdings.items()):
                cur_rank = rank_lookup.get(stock, 999)
                if cur_rank > MAX_HOLD_RANK:
                    clean_sym = stock.replace('.NS', '')
                    cur_p = cand_df.loc[cand_df['ticker'] == stock, 'price'].values[0] if stock in cand_df['ticker'].values else pos['entry_price']
                    exit_price = cur_p * SLIPPAGE_SELL
                    cash += pos['shares'] * exit_price
                    ret_pct = ((exit_price - pos['entry_price']) / pos['entry_price']) * 100
                    days_held = (pd.to_datetime(dt_str) - pd.to_datetime(pos['entry_date'])).days

                    sell_signals.append(f"🔴 *SELL (Rank Decay #{cur_rank}):* `{clean_sym}` @ ₹{exit_price:,.2f}")
                    closed_trades.append({
                        'Ticker': clean_sym,
                        'Entry Date': pos['entry_date'],
                        'Entry Price': round(pos['entry_price'], 2),
                        'Exit Date': dt_str,
                        'Exit Price': round(exit_price, 2),
                        'Return (%)': round(ret_pct, 2),
                        'Holding Days': days_held,
                        'Exit Reason': f"Rank Decay Exit (Rank #{cur_rank})"
                    })
                    del holdings[stock]

            # Entry Execution
            open_slots = TARGET_POSITIONS - len(holdings)
            portfolio_val = cash + sum(pos['shares'] * pos['entry_price'] for pos in holdings.values())

            if open_slots > 0 and cash > 2000:
                buy_candidates = cand_df[~cand_df['ticker'].isin(holdings.keys())].head(open_slots)
                alloc_target = portfolio_val / TARGET_POSITIONS

                for _, row in buy_candidates.iterrows():
                    stk, p = row['ticker'], row['price']
                    effective_buy = p * SLIPPAGE_BUY
                    alloc = min(cash, alloc_target)
                    shares = int(np.floor(alloc / effective_buy))

                    if shares > 0 and cash >= (shares * effective_buy):
                        holdings[stk] = {
                            'shares': shares,
                            'entry_price': effective_buy,
                            'peak_price': p,
                            'entry_date': dt_str
                        }
                        cash -= (shares * effective_buy)
                        buy_signals.append(f"🟢 *BUY:* `{stk.replace('.NS','')}` | {shares} shares @ ₹{effective_buy:,.2f}")

        last_week = current_week

    # 3. SAVE STATE & CURRENT HOLDINGS CSV WITH ATR TRAILING STOPS
    if closed_trades:
        pd.DataFrame(closed_trades).to_csv(TRADE_LOG_FILE, mode='a', header=False, index=False)

    with open(PORTFOLIO_FILE, "w") as f:
        json.dump({"cash": cash, "holdings": holdings, "last_week": last_week}, f, indent=4)

    holdings_rows = []
    for stk, info in holdings.items():
        clean_sym = stk.replace('.NS', '')
        data = get_tv_single_data(clean_sym)
        cur_p = data['close'] if data else info['entry_price']
        peak_p = max(info.get('peak_price', cur_p), cur_p)
        atr_val = data['atr14'] if data else 0.0

        stop_p = peak_p - (ATR_MULTIPLIER * atr_val) if atr_val > 0 else peak_p * 0.85
        stop_buffer = ((cur_p - stop_p) / cur_p) * 100 if cur_p > 0 else 0.0

        holdings_rows.append({
            'Ticker': clean_sym,
            'Entry Date': info['entry_date'],
            'Entry Price': round(info['entry_price'], 2),
            'Current Price': round(cur_p, 2),
            'Shares': info['shares'],
            'Current Value': round(cur_p * info['shares'], 2),
            'PnL (%)': round(((cur_p - info['entry_price']) / info['entry_price']) * 100, 2),
            'Peak Price': round(peak_p, 2),
            'ATR 14': round(atr_val, 2),
            'Stop Price': round(stop_p, 2),
            'Stop Buffer (%)': round(stop_buffer, 2)
        })
    pd.DataFrame(holdings_rows).to_csv(CURRENT_HOLDINGS_FILE, index=False)

    # 4. FETCH BENCHMARKS & APPEND PERFORMANCE HISTORY
    tv_n50 = get_tv_single_data(['NIFTY', 'NIFTY50'])
    tv_mid100 = get_tv_single_data(['CNXMIDCAP', 'NIFTY_MIDCAP_100'])
    tv_nJR = get_tv_single_data(['NIFTYJR', 'NIFTYNXT50'])
    tv_sml100 = get_tv_single_data(['CNXSMALLCAP', 'NIFTYSMLCAP100'])

    n50_val = tv_n50['close'] if tv_n50 else 0.0
    n500_val = tv_n500['close'] if tv_n500 else 0.0
    mid100_val = tv_mid100['close'] if tv_mid100 else 0.0
    nJR_val = tv_nJR['close'] if tv_nJR else 0.0
    sml100_val = tv_sml100['close'] if tv_sml100 else 0.0

    tot_val = cash + sum(r['Current Value'] for r in holdings_rows)
    p_ret = ((tot_val - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100

    base_n50, base_n500, base_mid100 = n50_val, n500_val, mid100_val
    base_nJR, base_sml100 = nJR_val, sml100_val

    if os.path.exists(PERFORMANCE_FILE) and os.path.getsize(PERFORMANCE_FILE) > 0:
        try:
            df_perf_old = pd.read_csv(PERFORMANCE_FILE)
            if not df_perf_old.empty:
                first_row = df_perf_old.iloc[0]
                base_n50 = first_row.get('Nifty_50', n50_val)
                base_n500 = first_row.get('Nifty_500', n500_val)
                base_mid100 = first_row.get('Nifty_Midcap_100', mid100_val)
                base_nJR = first_row.get('Nifty_Next_50', nJR_val)
                base_sml100 = first_row.get('Nifty_Smallcap_100', sml100_val)
        except Exception:
            pass

    n50_ret = ((n50_val - base_n50) / base_n50 * 100) if base_n50 > 0 else 0.0
    n500_ret = ((n500_val - base_n500) / base_n500 * 100) if base_n500 > 0 else 0.0
    mid100_ret = ((mid100_val - base_mid100) / base_mid100 * 100) if base_mid100 > 0 else 0.0
    nJR_ret = ((nJR_val - base_nJR) / base_nJR * 100) if base_nJR > 0 else 0.0
    sml100_ret = ((sml100_val - base_sml100) / base_sml100 * 100) if base_sml100 > 0 else 0.0

    perf_row = pd.DataFrame([{
        'Date': dt_str,
        'Portfolio_Value': round(tot_val, 2),
        'Portfolio_Return (%)': round(p_ret, 2),
        'Cash': round(cash, 2),
        'Holdings_Count': len(holdings),
        'Nifty_50': round(n50_val, 2),
        'Nifty_50_Return (%)': round(n50_ret, 2),
        'Nifty_500': round(n500_val, 2),
        'Nifty_500_Return (%)': round(n500_ret, 2),
        'Nifty_Midcap_100': round(mid100_val, 2),
        'Nifty_Midcap_100_Return (%)': round(mid100_ret, 2),
        'Nifty_Next_50': round(nJR_val, 2),
        'Nifty_Next_50_Return (%)': round(nJR_ret, 2),
        'Nifty_Smallcap_100': round(sml100_val, 2),
        'Nifty_Smallcap_100_Return (%)': round(sml100_ret, 2)
    }])

    if os.path.exists(PERFORMANCE_FILE) and os.path.getsize(PERFORMANCE_FILE) > 0:
        df_existing = pd.read_csv(PERFORMANCE_FILE)
        if 'Portfolio_Return (%)' in df_existing.columns:
            df_existing = df_existing[df_existing['Date'] != dt_str]
            pd.concat([df_existing, perf_row], ignore_index=True).to_csv(PERFORMANCE_FILE, index=False)
        else:
            perf_row.to_csv(PERFORMANCE_FILE, index=False)
    else:
        perf_row.to_csv(PERFORMANCE_FILE, index=False)

    # TELEGRAM NOTIFICATION
    msg = f"📊 *QUANT MOMENTUM SCAN* ({dt_str})\n"
    msg += f"💼 Portfolio Value: ₹{tot_val:,.2f} ({p_ret:+.2f}%)\n"
    msg += f"💵 Available Cash: ₹{cash:,.2f}\n"
    msg += f"📌 Positions: {len(holdings)}/{TARGET_POSITIONS}\n\n"

    if sell_signals:
        msg += "*EXITS TRIGGERED:*\n" + "\n".join(sell_signals) + "\n\n"
    if buy_signals:
        msg += "*NEW REBALANCING ENTRIES:*\n" + "\n".join(buy_signals) + "\n\n"
    if not sell_signals and not buy_signals:
        msg += "✅ No active trade execution needed today."

    send_telegram(msg)

if __name__ == "__main__":
    run_scanner()
