import os
import json
import urllib.request
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import warnings

# Suppress yfinance warnings
warnings.filterwarnings('ignore', category=FutureWarning)

DATA_URL = "https://raw.githubusercontent.com/kadoa-org/congress-trading-monitor/main/public/data/trades.json"
CACHE_DIR = ".cache"
CACHE_FILE = os.path.join(CACHE_DIR, "congress_trades.json")

def download_data():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    if not os.path.exists(CACHE_FILE):
        print(f"Downloading data from {DATA_URL}...")
        urllib.request.urlretrieve(DATA_URL, CACHE_FILE)
        print("Download complete.")

def get_multiplier(t):
    if not isinstance(t, str): return 0
    t = t.lower()
    if 'purchase' in t: return 1
    if 'sale' in t: return -1
    return 0

def calculate_drawdown(returns):
    cum_ret = (1 + returns).cumprod()
    running_max = cum_ret.cummax()
    drawdown = (cum_ret - running_max) / running_max
    return drawdown.min()

def run_backtest():
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    df = pd.DataFrame(data)
    # Basic filtering
    df = df[df['ticker'].notna() & (df['ticker'] != '--') & (df['ticker'] != '')]
    if 'transaction_type' not in df.columns:
        print("Error: no transaction_type")
        return
        
    df['multiplier'] = df['transaction_type'].apply(get_multiplier)
    df['amount_proxy'] = pd.to_numeric(df['amount_range_low'], errors='coerce').fillna(0)
    df['net_purchase'] = df['amount_proxy'] * df['multiplier']
    df['filing_date'] = pd.to_datetime(df['filing_date'], errors='coerce')
    df = df.dropna(subset=['filing_date'])
    df = df.sort_values('filing_date')
    
    # Define backtest period
    min_date = df['filing_date'].min()
    max_date = df['filing_date'].max()
    
    # We will rebalance monthly (end of month)
    rebalance_dates = pd.date_range(start=min_date, end=max_date, freq='ME')
    
    portfolio_history = {}
    all_selected_tickers = set()
    
    print(f"Generating monthly portfolios from {min_date.date()} to {max_date.date()}...")
    
    # Rolling window of 90 days for disclosures
    lookback_days = 90
    top_n = 5
    
    for date in rebalance_dates:
        start_lookback = date - pd.Timedelta(days=lookback_days)
        window_df = df[(df['filing_date'] > start_lookback) & (df['filing_date'] <= date)]
        
        # Aggregate net purchases
        agg = window_df.groupby('ticker')['net_purchase'].sum().sort_values(ascending=False)
        
        # Keep only positive net purchases
        agg = agg[agg > 0]
        
        # Select top N
        top_tickers = agg.head(top_n).index.tolist()
        
        # Remove weird tickers (e.g., CUSIPs which usually have numbers)
        top_tickers = [t for t in top_tickers if t.isalpha()]
        
        portfolio_history[date] = top_tickers
        all_selected_tickers.update(top_tickers)
        
    all_selected_tickers.add("QQQ") # Benchmark
    tickers_str = " ".join(all_selected_tickers)
    
    print(f"Downloading yfinance data for {len(all_selected_tickers)} unique tickers...")
    prices = yf.download(tickers_str, start=min_date, end=max_date + pd.Timedelta(days=31), progress=False)['Close']
    
    # Calculate daily returns
    returns = prices.pct_change().shift(-1) # Shift -1 so that returns on day t reflect t to t+1
    
    # Run simulation
    strategy_returns = pd.Series(0.0, index=prices.index)
    
    for i in range(len(rebalance_dates) - 1):
        start_d = rebalance_dates[i]
        end_d = rebalance_dates[i+1]
        
        current_tickers = portfolio_history[start_d]
        
        # Get period mask
        mask = (returns.index >= start_d) & (returns.index < end_d)
        
        if len(current_tickers) > 0:
            # Average return of selected tickers for the period
            period_returns = returns.loc[mask, current_tickers].mean(axis=1)
            strategy_returns.loc[mask] = period_returns
        else:
            # Cash return (0)
            strategy_returns.loc[mask] = 0.0
            
    # Calculate Benchmark (QQQ) returns
    bm_returns = returns['QQQ']
    
    # Align dates
    strategy_returns = strategy_returns.dropna()
    bm_returns = bm_returns.loc[strategy_returns.index].dropna()
    strategy_returns = strategy_returns.loc[bm_returns.index]
    
    # Cumulative returns
    strat_cum = (1 + strategy_returns).cumprod()
    bm_cum = (1 + bm_returns).cumprod()
    
    # Stats
    years = (bm_returns.index[-1] - bm_returns.index[0]).days / 365.25
    if years > 0:
        strat_cagr = strat_cum.iloc[-1] ** (1 / years) - 1
        bm_cagr = bm_cum.iloc[-1] ** (1 / years) - 1
        strat_mdd = calculate_drawdown(strategy_returns)
        bm_mdd = calculate_drawdown(bm_returns)
        
        print("\n=== Backtest Results (PTR Top 5 vs QQQ) ===")
        print(f"Period: {bm_returns.index[0].date()} to {bm_returns.index[-1].date()} ({years:.2f} years)")
        print(f"PTR Strategy CAGR: {strat_cagr*100:.2f}%")
        print(f"PTR Strategy MDD:  {strat_mdd*100:.2f}%")
        print(f"QQQ Benchmark CAGR: {bm_cagr*100:.2f}%")
        print(f"QQQ Benchmark MDD:  {bm_mdd*100:.2f}%")
    else:
        print("Not enough data for yearly stats.")

if __name__ == "__main__":
    download_data()
    run_backtest()
