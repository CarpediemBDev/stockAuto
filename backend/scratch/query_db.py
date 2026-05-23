import sqlite3

def main():
    conn = sqlite3.connect('stockauto.db')
    c = conn.cursor()
    
    # Get active holdings
    c.execute("SELECT ticker, avg_price, quantity, highest_price FROM holdings")
    holdings = c.fetchall()
    
    exchange_rate = 1350.0
    
    print("=== ACTIVE HOLDINGS DETAILS ===")
    total_cost_usd = 0
    
    for ticker, avg_price, quantity, highest_price in holdings:
        cost = avg_price * quantity
        peak_return = ((highest_price - avg_price) / avg_price) * 100
        print(f"Ticker: {ticker:5} | Qty: {quantity:4} | Buy Price: ${avg_price:7.2f} | Peak Price: ${highest_price:7.2f} | Peak Return: {peak_return:6.2f}%")
        total_cost_usd += cost
        
    print(f"Total Invested: ${total_cost_usd:,.2f} (approx {total_cost_usd*exchange_rate:,.0f} KRW)")
    print()
    
    # Calculate completed trades returns
    c.execute("SELECT ticker, trade_type, price, quantity, executed_at FROM trade_logs ORDER BY ticker, executed_at")
    logs = c.fetchall()
    
    # We will match BUYs and SELLs to calculate actual profit/loss
    buys = {}
    completed_profits = []
    
    for ticker, trade_type, price, quantity, executed_at in logs:
        if trade_type == 'BUY':
            if ticker not in buys:
                buys[ticker] = []
            buys[ticker].append((price, quantity))
        elif trade_type == 'SELL':
            if ticker in buys and buys[ticker]:
                buy_price, buy_qty = buys[ticker].pop(0) # match oldest buy (FIFO)
                profit_usd = (price - buy_price) * min(quantity, buy_qty)
                profit_pct = ((price - buy_price) / buy_price) * 100
                completed_profits.append((ticker, profit_usd, profit_pct))
                
    print("=== COMPLETED TRADES PERFORMANCE ===")
    if completed_profits:
        total_profit = sum(p[1] for p in completed_profits)
        avg_profit_pct = sum(p[2] for p in completed_profits) / len(completed_profits)
        print(f"Total Completed Trades: {len(completed_profits)}")
        print(f"Total Realized Profit: ${total_profit:,.2f}")
        print(f"Average Return per Trade: {avg_profit_pct:.2f}%")
        print("\nIndividual Realized Profits:")
        for ticker, profit_usd, profit_pct in completed_profits:
            print(f"Ticker: {ticker:5} | Profit: ${profit_usd:+.2f} ({profit_pct:+.2f}%)")
    else:
        print("No completed matched trades found in log.")
        
    conn.close()

if __name__ == "__main__":
    main()
