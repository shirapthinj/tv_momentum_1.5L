import io
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime

# BACKTEST CONFIGURATION ALIGNED WITH LIVE ENGINE
BACKTEST_START = "2024-01-01"
BACKTEST_END = datetime.now().strftime("%Y-%m-%d")
DATA_START = "2023-01-01"      # 1-year buffer for 200 SMA & 52W High
INITIAL_CAPITAL = 150000.0     # ₹1.5 Lakhs
TARGET_POSITIONS = 10          # 10 slots
MAX_HOLD_RANK = 25             # Rank Decay Cutoff
ATR_MULTIPLIER = 3.5           # 3.5x ATR Dynamic Trailing Stop
MIN_TURNOVER = 50000000        # ₹5 Crore Daily Turnover Floor
MIN_STOCK_PRICE = 20.0         # ₹20 Minimum Price Floor

SLIPPAGE_BUY = 1.0015          # 0.15% Buy Friction
SLIPPAGE_SELL = 0.9985         # 0.15% Sell Friction

BENCHMARKS = {
    'Nifty 50': '^NSEI',
    'Nifty 500': '^CRSLDX',
    'Nifty Midcap 100': 'NIFTY_MIDCAP_100.NS',
    'Nifty Next 50': 'NIFTYJR.NS',
    'Nifty Smallcap 100': 'NIFTY_SMLCAP_100.NS'
}

def fetch_universe():
    print("Fetching Nifty 500 universe and filtering out non-EQ series...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    n500_url = "https://niftyindices.com/IndexConstituent/ind_nifty500list.csv"
    nse_master_url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    
    try:
        res_n500 = requests.get(n500_url, headers=headers, timeout=15)
        df_n500 = pd.read_csv(io.StringIO(res_n500.text))
        n500_symbols = set(df_n500['Symbol'].str.strip())

        res_master = requests.get(nse_master_url, headers=headers, timeout=15)
        df_master = pd.read_csv(io.StringIO(res_master.text))
        df_master.columns = df_master.columns.str.strip()
        
        eq_only = df_master[df_master['SERIES'].str.strip() == 'EQ']
        eq_symbols = set(eq_only['SYMBOL'].str.strip())

        valid_symbols = list(n500_symbols.intersection(eq_symbols))
        return [f"{sym}.NS" for sym in valid_symbols]
    except Exception as e:
        print(f"Error fetching master list: {e}")
        return ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'BHARTIARTL.NS', 'ICICIBANK.NS']

def run_backtest():
    tickers = fetch_universe()
    bench_symbols = list(BENCHMARKS.values())
    all_symbols = list(set(tickers + bench_symbols))
    
    print(f"Downloading OHLCV data for {len(all_symbols)} tickers...")
    raw_data = yf.download(all_symbols, start=DATA_START, end=BACKTEST_END, progress=True)
    
    close_df = raw_data['Close'].ffill()
    high_df = raw_data['High'].ffill()
    low_df = raw_data['Low'].ffill()
    volume_df = raw_data['Volume'].fillna(0)

    sma200_df = close_df.rolling(window=200).mean()
    high52w_df = high_df.rolling(window=252).max()
    
    ret6m_df = close_df.pct_change(126) * 100
    ret12m_df = close_df.pct_change(252) * 100
    ret3m_df = close_df.pct_change(63) * 100
    turnover_df = close_df * volume_df

    # Calculate 14-Day ATR
    prev_close = close_df.shift(1)
    tr1 = high_df - low_df
    tr2 = (high_df - prev_close).abs()
    tr3 = (low_df - prev_close).abs()
    tr_df = np.maximum(tr1, np.maximum(tr2, tr3))
    atr14_df = tr_df.rolling(window=14).mean()
    atr_pct_df = (atr14_df / close_df) * 100

    # Shift by 1 day to remove look-ahead bias
    sig_close = close_df.shift(1)
    sig_high = high_df.shift(1)
    sig_low = low_df.shift(1)
    sig_sma200 = sma200_df.shift(1)
    sig_high52w = high52w_df.shift(1)
    sig_atr14 = atr14_df.shift(1)
    sig_atr_pct = atr_pct_df.shift(1)
    sig_ret3m = ret3m_df.shift(1)
    sig_ret6m = ret6m_df.shift(1)
    sig_ret12m = ret12m_df.shift(1)
    sig_turnover = turnover_df.shift(1)

    trading_days = close_df.loc[BACKTEST_START:BACKTEST_END].index
    cash = INITIAL_CAPITAL
    holdings = {}
    history, trade_log = [], []
    last_week = None

    for dt in trading_days:
        dt_str = dt.strftime('%Y-%m-%d')
        current_week = dt.isocalendar()[1]
        is_rebalance_day = (last_week is None) or (current_week != last_week)
        
        # 1. DAILY EXIT EVALUATION (3.5x ATR Trailing Stop)
        sold_tickers = []
        for ticker, pos in list(holdings.items()):
            cur_p = close_df.loc[dt, ticker] if ticker in close_df.columns else np.nan
            if pd.isna(cur_p) or cur_p <= 0:
                continue
                
            s_atr = sig_atr14.loc[dt, ticker] if ticker in sig_atr14.columns else np.nan
            pos['peak_price'] = max(pos['peak_price'], cur_p)
            
            stop_price = pos['peak_price'] - (ATR_MULTIPLIER * s_atr) if (not pd.isna(s_atr) and s_atr > 0) else pos['peak_price'] * 0.85
            
            if cur_p < stop_price:
                exit_price = cur_p * SLIPPAGE_SELL
                cash += pos['shares'] * exit_price
                ret_pct = ((exit_price - pos['entry_price']) / pos['entry_price']) * 100
                days_held = (dt - pd.to_datetime(pos['entry_date'])).days
                
                trade_log.append({
                    'Ticker': ticker.replace('.NS', ''),
                    'Entry Date': pos['entry_date'],
                    'Entry Price': round(pos['entry_price'], 2),
                    'Exit Date': dt_str,
                    'Exit Price': round(exit_price, 2),
                    'Return (%)': round(ret_pct, 2),
                    'Holding Days': days_held,
                    'Exit Reason': f"{ATR_MULTIPLIER}x ATR Trailing Stop"
                })
                sold_tickers.append(ticker)
                
        for t in sold_tickers:
            del holdings[t]

        # 2. WEEKLY REBALANCING WITH CIRCUIT & ATR FLOOR FILTERS
        if is_rebalance_day:
            last_week = current_week
            n500_sym = BENCHMARKS['Nifty 500']
            n500_3m = sig_ret3m.loc[dt, n500_sym] if n500_sym in sig_ret3m.columns else 0.0
            if pd.isna(n500_3m):
                n500_3m = 0.0
            
            all_candidates = []
            for ticker in tickers:
                if ticker not in close_df.columns:
                    continue
                
                p_exec = close_df.loc[dt, ticker]
                p_sig = sig_close.loc[dt, ticker]
                h_sig = sig_high.loc[dt, ticker]
                l_sig = sig_low.loc[dt, ticker]
                sma200 = sig_sma200.loc[dt, ticker]
                h52w = sig_high52w.loc[dt, ticker]
                r3m = sig_ret3m.loc[dt, ticker]
                r6m = sig_ret6m.loc[dt, ticker]
                r12m = sig_ret12m.loc[dt, ticker]
                atr_pct = sig_atr_pct.loc[dt, ticker]
                to = sig_turnover.loc[dt, ticker]
                
                if pd.isna(p_exec) or pd.isna(p_sig) or pd.isna(sma200) or pd.isna(h52w) or pd.isna(r3m) or pd.isna(r6m) or pd.isna(r12m) or pd.isna(atr_pct) or pd.isna(to) or h52w <= 0:
                    continue
                
                # GUARD 1: Upper Circuit Lock Filter (High == Low means no volume sell liquidity)
                if not pd.isna(h_sig) and not pd.isna(l_sig) and h_sig == l_sig:
                    continue

                # GUARD 2: Volatility Floor (Filters out unfillable flat-line circuit stocks)
                if atr_pct < 0.8:
                    continue

                alpha_3m = r3m - n500_3m
                if p_sig >= MIN_STOCK_PRICE and to >= MIN_TURNOVER and p_sig > sma200 and alpha_3m > 0:
                    smooth_momentum = (0.6 * r6m) + (0.4 * r12m)
                    vol_adj_momentum = smooth_momentum / max(atr_pct, 0.5)
                    high_proximity_power4 = (p_sig / h52w) ** 4
                    score = vol_adj_momentum * high_proximity_power4
                    all_candidates.append({'ticker': ticker, 'price': p_exec, 'score': score})
            
            if all_candidates:
                cand_df = pd.DataFrame(all_candidates).sort_values(by='score', ascending=False).reset_index(drop=True)
                cand_df['rank'] = cand_df.index + 1
                rank_lookup = dict(zip(cand_df['ticker'], cand_df['rank']))
                
                # Rank Decay Exit (> Rank 25)
                rank_decay_sells = []
                for ticker, pos in list(holdings.items()):
                    current_rank = rank_lookup.get(ticker, 999)
                    if current_rank > MAX_HOLD_RANK:
                        cur_p = close_df.loc[dt, ticker] if ticker in close_df.columns else pos['entry_price']
                        exit_price = cur_p * SLIPPAGE_SELL
                        cash += pos['shares'] * exit_price
                        ret_pct = ((exit_price - pos['entry_price']) / pos['entry_price']) * 100
                        days_held = (dt - pd.to_datetime(pos['entry_date'])).days
                        
                        trade_log.append({
                            'Ticker': ticker.replace('.NS', ''),
                            'Entry Date': pos['entry_date'],
                            'Entry Price': round(pos['entry_price'], 2),
                            'Exit Date': dt_str,
                            'Exit Price': round(exit_price, 2),
                            'Return (%)': round(ret_pct, 2),
                            'Holding Days': days_held,
                            'Exit Reason': f"Rank Decay Exit (Rank #{current_rank})"
                        })
                        rank_decay_sells.append(ticker)
                        
                for t in rank_decay_sells:
                    del holdings[t]

                # Entry Execution
                current_portfolio_val = cash + sum(
                    pos['shares'] * close_df.loc[dt, t]
                    for t, pos in holdings.items() 
                    if t in close_df.columns and not pd.isna(close_df.loc[dt, t])
                )
                
                open_slots = TARGET_POSITIONS - len(holdings)
                if open_slots > 0 and cash > 2000:
                    buy_candidates = cand_df[~cand_df['ticker'].isin(holdings.keys())].head(open_slots)
                    target_alloc_per_stock = current_portfolio_val / TARGET_POSITIONS
                    
                    for _, row in buy_candidates.iterrows():
                        stk, p = row['ticker'], row['price']
                        effective_buy_price = p * SLIPPAGE_BUY
                        alloc_capital = min(cash, target_alloc_per_stock)
                        shares = int(np.floor(alloc_capital / effective_buy_price))
                        
                        if shares > 0 and cash >= (shares * effective_buy_price):
                            holdings[stk] = {
                                'shares': shares,
                                'entry_price': effective_buy_price,
                                'peak_price': p,
                                'entry_date': dt_str
                            }
                            cash -= (shares * effective_buy_price)

        # 3. RECORD DAILY SNAPSHOT
        portfolio_val = cash + sum(
            pos['shares'] * close_df.loc[dt, t] 
            for t, pos in holdings.items() 
            if t in close_df.columns and not pd.isna(close_df.loc[dt, t])
        )
        
        row_dict = {'Date': dt_str, 'Portfolio_Value': portfolio_val, 'Cash': cash, 'Holdings_Count': len(holdings)}
        for b_name, b_sym in BENCHMARKS.items():
            row_dict[b_name] = close_df.loc[dt, b_sym] if b_sym in close_df.columns else np.nan
        history.append(row_dict)

    df_perf = pd.DataFrame(history)
    base_port = df_perf['Portfolio_Value'].iloc[0]
    df_perf['Portfolio Return (%)'] = ((df_perf['Portfolio_Value'] - base_port) / base_port) * 100
    
    final_port_ret = df_perf['Portfolio Return (%)'].iloc[-1]
    df_perf['Peak'] = df_perf['Portfolio_Value'].cummax()
    df_perf['Drawdown'] = ((df_perf['Portfolio_Value'] - df_perf['Peak']) / df_perf['Peak']) * 100
    max_dd = df_perf['Drawdown'].min()
    
    df_trades = pd.DataFrame(trade_log)
    win_trades = df_trades[df_trades['Return (%)'] > 0] if not df_trades.empty else pd.DataFrame()
    win_rate = (len(win_trades) / len(df_trades) * 100) if not df_trades.empty else 0.0

    print("\n" + "="*58)
    print(" 📊 REALISTIC MOMENTUM BACKTEST SUMMARY (CIRCUIT FILTERED)")
    print("="*58)
    print(f" Initial Capital      : ₹{INITIAL_CAPITAL:,.2f}")
    print(f" Final Portfolio Value: ₹{df_perf['Portfolio_Value'].iloc[-1]:,.2f}")
    print(f" Strategy Total Return: {final_port_ret:+.2f}%")
    print(f" Max Drawdown         : {max_dd:.2f}%")
    print(f" Total Closed Trades  : {len(df_trades)}")
    print(f" Win Rate             : {win_rate:.1f}%")
    print("="*58)

if __name__ == "__main__":
    run_backtest()
