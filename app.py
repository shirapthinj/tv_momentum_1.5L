import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Quantitative Momentum Engine",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="collapsed"
)

# Custom CSS: Executive Styling, Bolder Headers, Center Alignment
st.markdown("""
<style>
    .stApp { background-color: #0B0E14; font-family: 'Inter', sans-serif; }
    
    /* KPI Card Styling - Center Aligned & Bolder Headings */
    div[data-testid="stMetric"] {
        background-color: #161B22; border: 1px solid #262C36;
        padding: 14px 10px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        text-align: center !important;
        display: flex; flex-direction: column; align-items: center; justify-content: center;
    }
    div[data-testid="stMetricLabel"] { 
        font-size: 1.05rem !important; 
        font-weight: 800 !important; 
        color: #FFFFFF !important; 
        text-align: center !important;
        width: 100%; justify-content: center !important;
    }
    div[data-testid="stMetricLabel"] > div { justify-content: center !important; text-align: center !important; }
    div[data-testid="stMetricValue"] { 
        font-size: 1.25rem !important; 
        font-weight: 500 !important; 
        color: #C9D1D9 !important; 
        text-align: center !important; width: 100%;
    }
    div[data-testid="stMetricDelta"] { 
        font-size: 0.78rem !important; 
        justify-content: center !important; text-align: center !important; width: 100%;
    }
    div[data-testid="stMetricDelta"] > div { justify-content: center !important; text-align: center !important; }

    /* Center-Align All Table Headers & Cells */
    [data-testid="stDataFrame"] { text-align: center !important; }
    [data-testid="stDataFrame"] div[role="grid"] { text-align: center !important; }
    [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th { text-align: center !important; }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] { background-color: #161B22; padding: 6px; border-radius: 10px; border: 1px solid #262C36; }
    .stTabs [aria-selected="true"] { background-color: #21262D !important; color: #58A6FF !important; font-weight: 600; }
    div[data-testid="stDataFrame"] { background-color: #161B22; border-radius: 10px; border: 1px solid #262C36; }
    h2, h3 { color: #F0F6FC !important; font-weight: 700 !important; letter-spacing: -0.5px; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h2>⚡ Quantitative Momentum Engine</h2>", unsafe_allow_html=True)
st.markdown("<p style='color: #8B949E; margin-bottom: 20px;'>TradingView-Powered Executive Analytics & Friction Cost Engine</p>", unsafe_allow_html=True)

@st.cache_data(ttl=60)
def load_data():
    holdings = pd.read_csv("current_holdings.csv") if os.path.exists("current_holdings.csv") else pd.DataFrame()
    perf = pd.read_csv("performance_history.csv") if os.path.exists("performance_history.csv") else pd.DataFrame()
    trades = pd.read_csv("trade_log.csv") if os.path.exists("trade_log.csv") else pd.DataFrame()
    return holdings, perf, trades

holdings_df, perf_df, trades_df = load_data()

# Helper: Max Drawdown Calculation
def calc_max_drawdown(series):
    if series.empty or series.dropna().empty:
        return 0.0
    s = series.dropna()
    peak = s.cummax()
    dd = ((s - peak) / peak) * 100
    return dd.min()

# Calculate Portfolio Drawdown Curve
if not perf_df.empty and 'Portfolio_Value' in perf_df.columns:
    perf_df['Peak_Val'] = perf_df['Portfolio_Value'].cummax()
    perf_df['Drawdown (%)'] = ((perf_df['Portfolio_Value'] - perf_df['Peak_Val']) / perf_df['Peak_Val']) * 100

# TOP EXECUTIVE KPI CARDS
if not perf_df.empty:
    latest = perf_df.iloc[-1]
    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
    
    col1.metric("Portfolio Value", f"₹{latest['Portfolio_Value']:,.2f}", f"{latest['Portfolio_Return (%)']:+.2f}%")
    col2.metric("Available Cash", f"₹{latest['Cash']:,.2f}")
    
    n50_p = latest.get('Nifty_50', 0.0)
    col3.metric("Nifty 50", f"{n50_p:,.2f}" if n50_p > 0 else "—", f"{latest.get('Nifty_50_Return (%)', 0.0):+.2f}%")

    n500_p = latest.get('Nifty_500', 0.0)
    col4.metric("Nifty 500", f"{n500_p:,.2f}" if n500_p > 0 else "—", f"{latest.get('Nifty_500_Return (%)', 0.0):+.2f}%")

    mid100_p = latest.get('Nifty_Midcap_100', 0.0)
    col5.metric("Nifty Midcap 100", f"{mid100_p:,.2f}" if mid100_p > 0 else "—", f"{latest.get('Nifty_Midcap_100_Return (%)', 0.0):+.2f}%")

    njr_p = latest.get('Nifty_Next_50', 0.0)
    col6.metric("Nifty Next 50", f"{njr_p:,.2f}" if njr_p > 0 else "—", f"{latest.get('Nifty_Next_50_Return (%)', 0.0):+.2f}%")

    sml100_p = latest.get('Nifty_Smallcap_100', 0.0)
    col7.metric("Nifty Smallcap 100", f"{sml100_p:,.2f}" if sml100_p > 0 else "—", f"{latest.get('Nifty_Smallcap_100_Return (%)', 0.0):+.2f}%")
    
    st.markdown("<br>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs([
    "📈 Returns & Risk Benchmarks", 
    "📋 Active Positions & Risk Exposure", 
    "💸 Zerodha Friction & Cost Drag", 
    "📜 Executed Trade History"
])

# TAB 1: RETURNS & MAX DRAWDOWN RISK COMPARISON
with tab1:
    col_chart, col_dd = st.columns([2, 1])
    
    with col_chart:
        st.markdown("### 📈 Cumulative Strategy vs Benchmarks")
        if not perf_df.empty and 'Portfolio_Return (%)' in perf_df.columns:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=perf_df['Date'], y=perf_df['Portfolio_Return (%)'], mode='lines+markers', name='Strategy Portfolio', line=dict(color='#00E676', width=3)))
            
            benchmarks = [
                ('Nifty_Midcap_100_Return (%)', 'Nifty Midcap 100', '#FFB74D', 'dot'),
                ('Nifty_500_Return (%)', 'Nifty 500', '#4FC3F7', 'dash'),
                ('Nifty_50_Return (%)', 'Nifty 50', '#B0BEC5', 'dashdot'),
                ('Nifty_Next_50_Return (%)', 'Nifty Next 50', '#AB47BC', 'dot'),
                ('Nifty_Smallcap_100_Return (%)', 'Nifty Smallcap 100', '#FF7043', 'dot')
            ]
            
            for col, name, color, style in benchmarks:
                if col in perf_df.columns:
                    fig.add_trace(go.Scatter(x=perf_df['Date'], y=perf_df[col], mode='lines', name=name, line=dict(color=color, width=1.5, dash=style)))

            fig.update_layout(
                template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                height=400, margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(showgrid=True, gridcolor='#1F242D'), yaxis=dict(showgrid=True, gridcolor='#1F242D', ticksuffix="%")
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_dd:
        st.markdown("### 📉 Underwater Drawdown Curve")
        if not perf_df.empty and 'Drawdown (%)' in perf_df.columns:
            dd_fig = go.Figure()
            dd_fig.add_trace(go.Scatter(
                x=perf_df['Date'], y=perf_df['Drawdown (%)'],
                fill='tozeroy', mode='lines', line=dict(color='#FF5252', width=1.5),
                fillcolor='rgba(255, 82, 82, 0.2)'
            ))
            dd_fig.update_layout(
                template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                height=400, margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified",
                xaxis=dict(showgrid=True, gridcolor='#1F242D'), yaxis=dict(showgrid=True, gridcolor='#1F242D', ticksuffix="%")
            )
            st.plotly_chart(dd_fig, use_container_width=True)

    st.markdown("### 🎯 Benchmark Risk & Max Drawdown Comparison")
    if not perf_df.empty:
        risk_metrics = []
        
        # Strategy Row
        p_ret = perf_df['Portfolio_Return (%)'].iloc[-1]
        p_mdd = calc_max_drawdown(perf_df['Portfolio_Value'])
        calmar = abs(p_ret / p_mdd) if p_mdd != 0 else 0.0
        risk_metrics.append({
            'Asset / Index': '🚀 Strategy Portfolio',
            'Latest Value / Level': f"₹{perf_df['Portfolio_Value'].iloc[-1]:,.2f}",
            'Total Return (%)': f"{p_ret:+.2f}%",
            'Max Drawdown (%)': f"{p_mdd:.2f}%",
            'Calmar Ratio': f"{calmar:.2f}"
        })

        # Benchmarks
        bench_cols = [
            ('Nifty_50', 'Nifty_50_Return (%)', 'Nifty 50'),
            ('Nifty_500', 'Nifty_500_Return (%)', 'Nifty 500'),
            ('Nifty_Midcap_100', 'Nifty_Midcap_100_Return (%)', 'Nifty Midcap 100'),
            ('Nifty_Next_50', 'Nifty_Next_50_Return (%)', 'Nifty Next 50'),
            ('Nifty_Smallcap_100', 'Nifty_Smallcap_100_Return (%)', 'Nifty Smallcap 100')
        ]

        for val_col, ret_col, label in bench_cols:
            if val_col in perf_df.columns:
                b_val = perf_df[val_col].iloc[-1]
                b_ret = perf_df[ret_col].iloc[-1] if ret_col in perf_df.columns else 0.0
                b_mdd = calc_max_drawdown(perf_df[val_col])
                b_calmar = abs(b_ret / b_mdd) if b_mdd != 0 else 0.0
                risk_metrics.append({
                    'Asset / Index': label,
                    'Latest Value / Level': f"{b_val:,.2f}" if b_val > 0 else "—",
                    'Total Return (%)': f"{b_ret:+.2f}%",
                    'Max Drawdown (%)': f"{b_mdd:.2f}%",
                    'Calmar Ratio': f"{b_calmar:.2f}"
                })

        st.dataframe(pd.DataFrame(risk_metrics), use_container_width=True, hide_index=True)

# TAB 2: ACTIVE HOLDINGS & RISK BUFFERS
with tab2:
    if not holdings_df.empty:
        holdings_df['Stop Price'] = holdings_df['Peak Price'] * 0.88
        holdings_df['Stop Buffer (%)'] = ((holdings_df['Current Price'] - holdings_df['Stop Price']) / holdings_df['Current Price']) * 100
        
        col_bar, col_alloc = st.columns([1.5, 1])
        
        with col_bar:
            st.markdown("### 📊 Unrealized PnL (%) by Position")
            chart_df = holdings_df.sort_values(by='PnL (%)', ascending=False)
            bar_colors = ['#00C853' if pnl >= 0 else '#FF5252' for pnl in chart_df['PnL (%)']]
            
            pnl_fig = go.Figure()
            pnl_fig.add_trace(go.Bar(
                x=chart_df['Ticker'], y=chart_df['PnL (%)'],
                text=chart_df['PnL (%)'].apply(lambda x: f"{x:,.2f}%"),
                textposition='outside', marker=dict(color=bar_colors)
            ))
            pnl_fig.update_layout(
                template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                height=320, margin=dict(l=10, r=10, t=20, b=10),
                yaxis=dict(showgrid=True, gridcolor='#1F242D', ticksuffix="%")
            )
            st.plotly_chart(pnl_fig, use_container_width=True)

        with col_alloc:
            st.markdown("### 🍰 Capital Allocation Breakdown")
            alloc_fig = px.pie(
                holdings_df, names='Ticker', values='Current Value',
                hole=0.4, color_discrete_sequence=px.colors.qualitative.Dark24
            )
            alloc_fig.update_layout(
                template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                height=320, margin=dict(l=10, r=10, t=10, b=10), showlegend=False
            )
            st.plotly_chart(alloc_fig, use_container_width=True)

        st.markdown("### 📋 Position Tracking Table & Stop Loss Buffers")
        st.dataframe(
            holdings_df[['Ticker', 'Entry Date', 'Entry Price', 'Current Price', 'Peak Price', 'Stop Price', 'Stop Buffer (%)', 'Shares', 'Current Value', 'PnL (%)']],
            use_container_width=True, hide_index=True,
            column_config={
                "PnL (%)": st.column_config.NumberColumn("PnL (%)", format="%.2f%%"),
                "Stop Buffer (%)": st.column_config.NumberColumn("Stop Buffer (%)", format="%.2f%%"),
                "Current Value": st.column_config.NumberColumn("Position Value", format="₹%.2f"),
                "Current Price": st.column_config.NumberColumn("Current Price", format="₹%.2f"),
                "Entry Price": st.column_config.NumberColumn("Entry Price", format="₹%.2f"),
                "Peak Price": st.column_config.NumberColumn("Peak Price", format="₹%.2f"),
                "Stop Price": st.column_config.NumberColumn("12% Stop Price", format="₹%.2f"),
            }
        )
    else:
        st.info("No active holdings currently in portfolio.")

# TAB 3: ZERODHA FRICTION & TAX ANALYSIS
with tab3:
    st.markdown("### 💸 Zerodha Delivery Cost Engine (Tax & Fee Breakdown)")
    
    # Estimate Turnover from Current Holdings + Closed Trades
    buy_turnover = holdings_df['Current Value'].sum() if not holdings_df.empty else 0.0
    closed_turnover = 0.0
    closed_trades_count = 0
    
    if not trades_df.empty:
        closed_trades_count = len(trades_df)
        # Assuming average ~₹25k turnover per trade leg
        closed_turnover = closed_trades_count * 25000.0 * 2.0

    total_buy_turnover = buy_turnover + (closed_turnover / 2.0)
    total_sell_turnover = (closed_turnover / 2.0)
    total_turnover = total_buy_turnover + total_sell_turnover

    # Zerodha Fee Engine Calculations
    stt = (total_buy_turnover * 0.001) + (total_sell_turnover * 0.001)
    stamp_duty = total_buy_turnover * 0.00015
    exchange_fee = total_turnover * 0.0000297
    sebi_fee = total_turnover * 0.000001
    gst = (exchange_fee + sebi_fee) * 0.18
    dp_charges = closed_trades_count * 15.34  # ₹13 + 18% GST flat per sell
    
    total_taxes = stt + stamp_duty + exchange_fee + sebi_fee + gst + dp_charges
    initial_cap = 500000.0
    tax_drag_pct = (total_taxes / initial_cap) * 100

    f1, f2, f3, f4, f5 = st.columns(5)
    f1.metric("Total Tax & Fees", f"₹{total_taxes:,.2f}")
    f2.metric("STT (0.1%)", f"₹{stt:,.2f}")
    f3.metric("Stamp Duty (0.015%)", f"₹{stamp_duty:,.2f}")
    f4.metric("DP Charges (₹15.34/sell)", f"₹{dp_charges:,.2f}")
    f5.metric("Friction Drag on Capital", f"{tax_drag_pct:.2f}%")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🧾 Zerodha Delivery Tariff Breakdown")
    fee_structure = [
        {"Fee Type": "Brokerage", "Zerodha Delivery Rate": "₹0.00 (Free)", "Applicability": "Buy & Sell Trades"},
        {"Fee Type": "STT (Securities Transaction Tax)", "Zerodha Delivery Rate": "0.10%", "Applicability": "Buy & Sell Turnover"},
        {"Fee Type": "Stamp Duty", "Zerodha Delivery Rate": "0.015%", "Applicability": "Buy Turnover Only"},
        {"Fee Type": "NSE Exchange Transaction Fee", "Zerodha Delivery Rate": "0.00297%", "Applicability": "Total Turnover"},
        {"Fee Type": "SEBI Charges", "Zerodha Delivery Rate": "₹10 / Crore (0.0001%)", "Applicability": "Total Turnover"},
        {"Fee Type": "GST", "Zerodha Delivery Rate": "18%", "Applicability": "On Exchange & SEBI Fees"},
        {"Fee Type": "DP (Depository Participant) Fee", "Zerodha Delivery Rate": "₹15.34 / scrip", "Applicability": "Sell Executions Only"}
    ]
    st.dataframe(pd.DataFrame(fee_structure), use_container_width=True, hide_index=True)

# TAB 4: EXECUTED TRADE LOGS & PERFORMANCE STATS
with tab4:
    if not trades_df.empty and len(trades_df) > 0:
        win_trades = trades_df[trades_df['Return (%)'] > 0]
        loss_trades = trades_df[trades_df['Return (%)'] <= 0]
        
        total_trades = len(trades_df)
        win_rate = (len(win_trades) / total_trades) * 100
        avg_win = win_trades['Return (%)'].mean() if not win_trades.empty else 0.0
        avg_loss = loss_trades['Return (%)'].mean() if not loss_trades.empty else 0.0
        
        gross_profit = win_trades['Return (%)'].sum() if not win_trades.empty else 0.0
        gross_loss = abs(loss_trades['Return (%)'].sum()) if not loss_trades.empty else 1.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Closed Trades", total_trades)
        m2.metric("Win Rate", f"{win_rate:.1f}%")
        m3.metric("Avg Winning Trade", f"{avg_win:+.2f}%")
        m4.metric("Avg Losing Trade", f"{avg_loss:+.2f}%")
        m5.metric("Profit Factor", f"{profit_factor:.2f}")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 📜 Executed Trade History")
        st.dataframe(trades_df, use_container_width=True, hide_index=True)
    else:
        st.info("No closed trades recorded yet.")
