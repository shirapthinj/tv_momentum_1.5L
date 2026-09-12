import io
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime

# BACKTEST CONFIGURATION
BACKTEST_START = "2024-01-01"  # Window starting Jan 2024
BACKTEST_END = datetime.now().strftime("%Y-%m-%d")
DATA_START = "2023-01-01"      # 1-year buffer for 252-day (52W) High & 200 SMA
INITIAL_CAPITAL = 150000.0     # ₹1.5 Lakhs Initial Capital
TARGET_POSITIONS = 10          # 10 slots (10% capital per position)
MAX_HOLD_RANK = 25             # Rank Decay Cutoff (Top 25)
ATR_MULTIPLIER = 3.5           # 3.5x ATR Dynamic Trailing Stop
MIN_TURNOVER = 50000000        # ₹5 Crore Daily Turnover Floor
MIN_STOCK_PRICE = 20.0         # ₹20 Minimum Stock Price Floor

# REALISTIC TRANSACTION COSTS & SLIPPAGE (0.15% per trade side)
SLIPPAGE_BUY = 1.0015
SLIPPAGE_SELL = 0.9985

BENCHMARKS = {
    'Nifty 50': '^NSEI',
    'Nifty 500': '^CRSLDX',
    'Nifty Midcap 100': 'NIFTY_MIDCAP_100.NS',
    'Nifty Next 50': 'NIFTYJR.NS',
    'Nifty Smallcap 100': 'NIFTY_SMLCAP_100.NS'
}

def fetch_universe():
    print("Fetching Nifty 500 universe and filtering out non-EQ (BE/T2T) series...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    n500_url = "https://niftyindices.com/IndexConstituent/ind_nifty500list.csv"
    nse_master_url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    
    try:
        # 1. Download Nifty 500 Constituent List
        res_n500 = requests.get(n500_url, headers=headers, timeout=15)
        df_n500 = pd.read_csv(io.StringIO(res_n500.text))
        n500_symbols = set(df_n500['Symbol'].str.strip())

        # 2. Download Official NSE Security Master File
        res_master = requests.get(nse_master_url, headers=headers, timeout=15)
        df_master = pd.read_csv(io.StringIO(res_master.text))
        df_master.columns = df_master.columns.str.strip()
        
        # 3. Filter strictly for 'EQ' Series (Excludes BE, BZ, SM, ST series)
        eq_only = df_master[df_master['SERIES'].str.strip() == 'EQ']
        eq_symbols = set(eq_only['SYMBOL'].str.strip())

        # 4. Retain only Nifty 500 stocks currently in the EQ series
        valid_symbols = list(n500_symbols.intersection(eq_symbols))
        print(f"Successfully loaded {len(valid_symbols)} active 'EQ' series tickers.")
        return [f"{sym}.NS" for sym in valid_symbols]
        
    except Exception as e:
        print(f"Error fetching filtered master list: {e}")
        try:
            res = requests.get(n500_url, headers=headers, timeout=15)
            df = pd.read_csv(io.StringIO(res.text))
            return [f"{sym.strip()}.NS" for sym in df['Symbol'].dropna()]
        except Exception:
            return ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'BHARTIARTL.NS', 'ICICIBANK.NS']

def run_backtest():
    tickers = fetch_universe()
    bench_symbols = list(BENCHMARKS.values())
    all_symbols = list(set(tickers + bench_symbols))
    
    print(f"Downloading historical OHLCV data from {DATA_START} to {BACKTEST_END} for {len(all_symbols)} tickers...")
    raw_data = yf.download(all_symbols, start=DATA_START, end=BACKTEST_END, progress=True)
    
    if isinstance(raw_data.columns, pd.MultiIndex):
        close_df = raw_data['Close'].ffill()
        high_df = raw_data['High'].ffill()
        low_df = raw_data['Low'].ffill()
        volume_df = raw_data['Volume'].fillna(0)
    else:
        close_df = raw_data[['Close']].ffill()
        high_df = raw_data[['High']].ffill()
        low_df = raw_data[['Low']].ffill()
        volume_df = raw_data[['Volume']].fillna(0)

    print("Calculating technical indicators & 52W High Breakout metrics...")
    sma200_df = close_df.rolling(window=200).mean()
    high52w_df = high_df.rolling(window=252).max()
    
    # Smooth 6M and 12M Return Horizons
    ret6m_df = close_df.pct_change(126) * 100
    ret12m_df = close_df.pct_change(252) * 100
    ret3m_df = close_df.pct_change(63) * 100
    turnover_df = close_df * volume_df

    # Calculate Average True Range (14-day ATR & ATR%)
    prev_close = close_df.shift(1)
    tr1 = high_df - low_df
    tr2 = (high_df - prev_close).abs()
    tr3 = (low_df - prev_close).abs()
    tr_df = np.maximum(tr1, np.maximum(tr2, tr3))
    atr14_df = tr_df.rolling(window=14).mean()
    atr_pct_df = (atr14_df / close_df) * 100

    # Shift indicator datasets by 1 day to eliminate look-ahead bias
    sig_close = close_df.shift(1)
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
    holdings = {}  # ticker: {'shares', 'entry_price', 'peak_price', 'entry_date'}
    history = []
    trade_log = []
    last_week = None

    print("\nExecuting backtest simulation (2024 - Present)...")
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
                
            s_price = sig_close.loc[dt, ticker] if ticker in sig_close.columns else cur_p
            s_atr = sig_atr14.loc[dt, ticker] if ticker in sig_atr14.columns else np.nan
            
            pos['peak_price'] = max(pos['peak_price'], cur_p)
            
            if not pd.isna(s_atr) and s_atr > 0:
                stop_price = pos['peak_price'] - (ATR_MULTIPLIER * s_atr)
            else:
                stop_price = pos['peak_price'] * 0.85
            
            if cur_p < stop_price or s_price < stop_price:
                exit_price = cur_p * SLIPPAGE_SELL
                proceeds = pos['shares'] * exit_price
                cash += proceeds
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

        # 2. WEEKLY REBALANCING & RANK DECAY EVALUATION
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
                sma200 = sig_sma200.loc[dt, ticker]
                h52w = sig_high52w.loc[dt, ticker]
                r3m = sig_ret3m.loc[dt, ticker]
                r6m = sig_ret6m.loc[dt, ticker]
                r12m = sig_ret12m.loc[dt, ticker]
                atr_pct = sig_atr_pct.loc[dt, ticker]
                to = sig_turnover.loc[dt, ticker]
                
                if pd.isna(p_exec) or pd.isna(p_sig) or pd.isna(sma200) or pd.isna(h52w) or pd.isna(r3m) or pd.isna(r6m) or pd.isna(r12m) or pd.isna(atr_pct) or pd.isna(to) or h52w <= 0:
                    continue
                
                alpha_3m = r3m - n500_3m
                
                # Filters: Price Floor, Liquidity, Price > 200 SMA, Alpha vs Nifty 500
                if p_sig >= MIN_STOCK_PRICE and to >= MIN_TURNOVER and p_sig > sma200 and alpha_3m > 0:
                    smooth_momentum = (0.6 * r6m) + (0.4 * r12m)
                    vol_adj_momentum = smooth_momentum / max(atr_pct, 0.5)
                    
                    # Exponential 52-Week High Breakout Factor
                    high_proximity_power4 = (p_sig / h52w) ** 4
                    
                    score = vol_adj_momentum * high_proximity_power4
                    all_candidates.append({'ticker': ticker, 'price': p_exec, 'score': score})
            
            if all_candidates:
                cand_df = pd.DataFrame(all_candidates).sort_values(by='score', ascending=False).reset_index(drop=True)
                cand_df['rank'] = cand_df.index + 1
                rank_lookup = dict(zip(cand_df['ticker'], cand_df['rank']))
                
                # A. RANK DECAY EXIT: Sell holdings that fall outside Top 25 Rank
                rank_decay_sells = []
                for ticker, pos in list(holdings.items()):
                    current_rank = rank_lookup.get(ticker, 999)
                    if current_rank > MAX_HOLD_RANK:
                        cur_p = close_df.loc[dt, ticker] if ticker in close_df.columns else pos['entry_price']
                        exit_price = cur_p * SLIPPAGE_SELL
                        proceeds = pos['shares'] * exit_price
                        cash += proceeds
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

                # B. ENTRY EXECUTION: Fill open slots with top-ranked candidates
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

        # 3. RECORD DAILY VALUES
        portfolio_val = cash + sum(
            pos['shares'] * close_df.loc[dt, t] 
            for t, pos in holdings.items() 
            if t in close_df.columns and not pd.isna(close_df.loc[dt, t])
        )
        
        row_dict = {
            'Date': dt_str,
            'Portfolio_Value': portfolio_val,
            'Cash': cash,
            'Holdings_Count': len(holdings)
        }
        for b_name, b_sym in BENCHMARKS.items():
            row_dict[b_name] = close_df.loc[dt, b_sym] if b_sym in close_df.columns else np.nan
            
        history.append(row_dict)

    # PROCESS METRICS
    df_perf = pd.DataFrame(history)
    base_port = df_perf['Portfolio_Value'].iloc[0]
    df_perf['Portfolio Return (%)'] = ((df_perf['Portfolio_Value'] - base_port) / base_port) * 100
    
    for b_name in BENCHMARKS.keys():
        valid_b = df_perf[b_name].ffill().dropna()
        base_b = valid_b.iloc[0] if not valid_b.empty else 1.0
        df_perf[f'{b_name} Return (%)'] = ((df_perf[b_name].ffill() - base_b) / base_b) * 100

    # PRINT SUMMARY
    final_port_ret = df_perf['Portfolio Return (%)'].iloc[-1]
    df_perf['Peak'] = df_perf['Portfolio_Value'].cummax()
    df_perf['Drawdown'] = ((df_perf['Portfolio_Value'] - df_perf['Peak']) / df_perf['Peak']) * 100
    max_dd = df_perf['Drawdown'].min()
    
    df_trades = pd.DataFrame(trade_log)
    win_trades = df_trades[df_trades['Return (%)'] > 0] if not df_trades.empty else pd.DataFrame()
    win_rate = (len(win_trades) / len(df_trades) * 100) if not df_trades.empty else 0.0

    print("\n" + "="*58)
    print(" 📊 2024-PRESENT QUANT MOMENTUM BACKTEST SUMMARY")
    print("="*58)
    print(f" Initial Capital      : ₹{INITIAL_CAPITAL:,.2f}")
    print(f" Final Portfolio Value: ₹{df_perf['Portfolio_Value'].iloc[-1]:,.2f}")
    print(f" Strategy Total Return: {final_port_ret:+.2f}%")
    print(f" Max Drawdown         : {max_dd:.2f}%")
    print(f" Total Closed Trades  : {len(df_trades)}")
    print(f" Win Rate             : {win_rate:.1f}%")
    print("-" * 58)
    print(" BENCHMARK COMPARISON (Total Return %):")
    for b_name in BENCHMARKS.keys():
        b_series = df_perf[f'{b_name} Return (%)'].dropna()
        b_ret = b_series.iloc[-1] if not b_series.empty else 0.0
        print(f"  • {b_name:<18}: {b_ret:+.2f}%")
    print("="*58)

    # GENERATE PLOTLY CHART
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_perf['Date'], y=df_perf['Portfolio Return (%)'], mode='lines', name='Strategy Portfolio', line=dict(color='#00E676', width=3)))
    colors = ['#FFB74D', '#4FC3F7', '#B0BEC5', '#AB47BC', '#FF7043']
    for idx, b_name in enumerate(BENCHMARKS.keys()):
        fig.add_trace(go.Scatter(x=df_perf['Date'], y=df_perf[f'{b_name} Return (%)'], mode='lines', name=b_name, line=dict(color=colors[idx % len(colors)], width=1.5, dash='dot')))

    fig.update_layout(
        title="Quant Momentum Strategy vs Benchmarks (2024 - Present)",
        template="plotly_dark",
        xaxis_title="Date",
        yaxis_title="Cumulative Return (%)",
        hovermode="x unified",
        height=600
    )
    
    fig.write_html("backtest_results_2024_present.html")
    df_perf.to_csv("backtest_daily_performance_2024.csv", index=False)
    if not df_trades.empty:
        df_trades.to_csv("backtest_trades_2024.csv", index=False)
    print("\n✅ Multi-year backtest completed successfully!")

if __name__ == "__main__":
    run_backtest()
