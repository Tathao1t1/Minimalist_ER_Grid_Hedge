"""
Logic Module for Minimalist ER Grid Strategy with Macro Futures Overlay
Emulating algotrade-education/DynamicGrid repository architecture.

Implements:
1. Non-parametric Kaufman Efficiency Ratio (ER) stock selection.
2. 18-level geometric dynamic grid with T+2.5 settlement enforcement.
3. Macro trend-following VN30F futures hedge overlay.
4. Comprehensive performance metrics calculation, plotting, and reporting.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta


def kaufman_er(prices):
    """
    Calculate Kaufman Efficiency Ratio (ER):
    ER = |Price(t) - Price(t-n)| / Sum(|Price(i) - Price(i-1)|)
    Values close to 0 denote pure mean-reverting oscillation.
    Values close to 1 denote pure directional momentum.
    """
    if len(prices) < 2:
        return 1.0
    direction = abs(prices[-1] - prices[0])
    volatility = np.sum(np.abs(np.diff(prices)))
    return float(direction / volatility) if volatility > 0 else 1.0


def get_settlement_dt(trade_dt: datetime) -> datetime:
    """
    Calculate T+2.5 settlement datetime under Vietnam HOSE regulations.
    Shares purchased become eligible for sale at 13:00 on T+2 trading days.
    """
    d = trade_dt.date()
    added = 0
    while added < 2:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Monday - Friday
            added += 1
    return datetime.combine(d, datetime.strptime("13:00", "%H:%M").time())


def build_zero_overlap_whitelist(bars_df, lookback_days=40, rebalance_days=10, top_k=4):
    """
    Generate rolling non-overlapping stock selection using Kaufman ER.
    Rebalances strictly every rebalance_days with no lookahead bias.
    """
    daily_records = []
    for ticker, df in bars_df.groupby('tickersymbol'):
        df = df.sort_values('bar_close').copy()
        if df['close'].max() < 1000:
            for c in ['open', 'high', 'low', 'close']:
                df[c] *= 1000.0
        df['date'] = df['bar_close'].dt.date
        daily = df.groupby('date').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).reset_index()
        daily['tickersymbol'] = ticker
        daily_records.append(daily)
        
    if not daily_records:
        return {}
        
    daily_df = pd.concat(daily_records).sort_values(['date', 'tickersymbol']).reset_index(drop=True)
    all_dates = sorted(daily_df['date'].unique())
    piv_close = daily_df.pivot(index='date', columns='tickersymbol', values='close').ffill()
    
    whitelist = {}
    for i in range(lookback_days, len(all_dates), rebalance_days):
        rebal_date = all_dates[i]
        hist_dates = all_dates[i - lookback_days : i]
        candidates = []
        for ticker in piv_close.columns:
            c_hist = piv_close.loc[hist_dates, ticker].dropna()
            if len(c_hist) < lookback_days * 0.8:
                continue
            candidates.append((ticker, kaufman_er(c_hist.values)))
        candidates.sort(key=lambda x: x[1])  # Lowest ER = most oscillatory
        whitelist[rebal_date] = [c[0] for c in candidates[:top_k]]
    return whitelist


class MinimalistERGridBacktest:
    """
    Minimalist Kaufman ER Grid Backtest Engine with Macro Futures Overlay
    """
    def __init__(
        self,
        capital=2_000_000_000,
        initial_spot_capital=1_000_000_000,
        hedge_buffer_capital=1_000_000_000,
        contract_value=100_000,
        margin_rate=0.20,
        broker_fee=0.0015,
        sell_tax=0.0010,
        futures_fee=0.0005,
        slippage=0.0005,
        selection_lookback=40,
        selection_rebalance_days=10,
        top_k=4,
        n_levels=18,
        grid_spacing_pct=0.018,
        stop_buffer_levels=2,
        macro_sma_days=50,
        macro_roc_days=20,
        macro_roc_threshold=-0.02,
        n_vn30f_contracts=10,
        hedging_mode='dynamic_delta_hedge',
        hedging_direction='short_only'
    ):
        self.capital = capital
        self.initial_spot_capital = initial_spot_capital
        self.hedge_buffer_capital = hedge_buffer_capital
        self.contract_value = contract_value
        self.margin_rate = margin_rate
        self.broker_fee = broker_fee
        self.sell_tax = sell_tax
        self.futures_fee = futures_fee
        self.slippage = slippage
        
        self.selection_lookback = selection_lookback
        self.selection_rebalance_days = selection_rebalance_days
        self.top_k = top_k
        self.n_levels = n_levels
        self.grid_spacing_pct = grid_spacing_pct
        self.stop_buffer_levels = stop_buffer_levels
        
        self.macro_sma_days = macro_sma_days
        self.macro_roc_days = macro_roc_days
        self.macro_roc_threshold = macro_roc_threshold
        self.n_vn30f_contracts = n_vn30f_contracts
        self.hedging_mode = hedging_mode
        self.hedging_direction = hedging_direction
        
        self.trades = []
        self.equity_series = None
        self.metrics = None
        self.log_file = "trade_log.txt"

    def backtest(self, data_bundle):
        """
        Execute simulation on data bundle (bars, vn30f, vn30d)
        """
        bars_df = data_bundle['bars'].copy()
        vn30f_bars = data_bundle['vn30f'].copy()
        vn30_daily = data_bundle['vn30d'].copy()
        start_dt = pd.to_datetime(data_bundle['start_date'])
        end_dt = pd.to_datetime(data_bundle['end_date'])
        
        # 1. Normalize prices
        if bars_df['close'].max() < 1000:
            for c in ['open', 'high', 'low', 'close']:
                bars_df[c] *= 1000.0
        bars_df = bars_df.sort_values(['bar_close', 'tickersymbol']).reset_index(drop=True)
        
        # 2. Build selection whitelist
        whitelist_by_date = build_zero_overlap_whitelist(
            bars_df, 
            lookback_days=self.selection_lookback,
            rebalance_days=self.selection_rebalance_days,
            top_k=self.top_k
        )
        
        # 3. Compute anchors (50-period SMA per ticker)
        anchors = {}
        for ticker, df in bars_df.groupby('tickersymbol'):
            df = df.sort_values('bar_close')
            anchors[ticker] = df.set_index('bar_close')['close'].rolling(50).mean()

        capital_per_stock = self.initial_spot_capital / self.top_k
        capital_per_level = capital_per_stock / self.n_levels
        
        cash = float(self.initial_spot_capital)
        grids = {}
        positions = {}
        completed_trades = []
        equity_curve = []
        
        wl_dates = sorted(whitelist_by_date.keys())
        cur_wl = []
        next_wl_idx = 0
        
        # 4. Spot Bar Execution Loop
        for ts, bar_group in bars_df.groupby('bar_close', sort=True):
            bar_group = bar_group.set_index('tickersymbol')
            cur_date = ts.date()
            
            if next_wl_idx < len(wl_dates) and cur_date >= wl_dates[next_wl_idx]:
                cur_wl = whitelist_by_date[wl_dates[next_wl_idx]]
                next_wl_idx += 1
                
            # A. EXIT / SELL PASS
            for ticker in list(positions.keys()):
                if ticker not in bar_group.index:
                    continue
                bar = bar_group.loc[ticker]
                bar_h, bar_l, bar_c = float(bar['high']), float(bar['low']), float(bar['close'])
                grid_info = grids.get(ticker)
                floor_stop = grid_info['stop'] if grid_info else 0.0
                is_floor_hit = (bar_l <= floor_stop) and (floor_stop > 0)
                
                to_remove = []
                lvl_dict = positions[ticker]
                for lvl, pos in lvl_dict.items():
                    can_exit = (ts >= pos['settlement'])
                    if is_floor_hit:
                        fill = max(min(float(bar['open']), floor_stop), floor_stop * 0.93)
                        to_remove.append((lvl, fill, True, 'floor_stop'))
                        continue
                    if bar_h >= pos['tp_price'] and can_exit:
                        to_remove.append((lvl, pos['tp_price'], False, 'target'))
                        continue
                    if ticker not in cur_wl and can_exit and (grid_info is None):
                        to_remove.append((lvl, bar_c, True, 'rotation_exit'))
                        continue
                        
                for (lvl, fill_px, is_stop, reason) in to_remove:
                    pos = lvl_dict.pop(lvl)
                    actual_fill = fill_px * (1.0 - self.slippage)
                    exit_cost = actual_fill * pos['shares'] * (self.broker_fee + self.sell_tax)
                    proceeds = actual_fill * pos['shares'] - exit_cost
                    cash += proceeds
                    pnl = proceeds - (pos['entry_price'] * pos['shares'] + pos['entry_cost'])
                    completed_trades.append({
                        'timestamp': ts,
                        'ticker': ticker,
                        'level_idx': lvl,
                        'action': 'SELL',
                        'price': actual_fill,
                        'shares': pos['shares'],
                        'reason': reason,
                        'pnl': pnl
                    })
                    
                if is_floor_hit:
                    positions.pop(ticker, None)
                    if ticker in grids:
                        del grids[ticker]
                elif len(lvl_dict) == 0 and ticker not in cur_wl:
                    positions.pop(ticker, None)
                    if ticker in grids:
                        del grids[ticker]

            # B. GRID ACTIVATION
            for ticker in list(grids.keys()):
                if ticker not in cur_wl and (ticker not in positions or len(positions[ticker]) == 0):
                    del grids[ticker]
                    
            avail_slots = self.top_k - len(grids)
            if avail_slots > 0 and len(cur_wl) > 0:
                for ticker in cur_wl:
                    if ticker in grids or ticker not in bar_group.index:
                        continue
                    bar = bar_group.loc[ticker]
                    sma_val = anchors[ticker].get(ts, np.nan)
                    if np.isnan(sma_val) or abs(float(bar['close']) - sma_val) / sma_val > 0.03:
                        continue
                    spacing = sma_val * self.grid_spacing_pct
                    levels = [round(sma_val - k * spacing, 2) for k in range(1, self.n_levels + 1)]
                    tps = [round(sma_val - (k - 1) * spacing, 2) for k in range(1, self.n_levels + 1)]
                    stop_px = sma_val - (self.n_levels + self.stop_buffer_levels) * spacing
                    grids[ticker] = {'anchor': sma_val, 'levels': levels, 'tps': tps, 'stop': stop_px}
                    positions.setdefault(ticker, {})
                    avail_slots -= 1
                    if avail_slots <= 0:
                        break
                        
            # C. BUY PASS
            for ticker, g in grids.items():
                if ticker not in bar_group.index:
                    continue
                bar_l = float(bar_group.loc[ticker, 'low'])
                lvl_dict = positions.setdefault(ticker, {})
                for lvl_idx in range(1, self.n_levels + 1):
                    if lvl_idx in lvl_dict:
                        continue
                    buy_px = g['levels'][lvl_idx - 1]
                    if bar_l > buy_px:
                        continue
                    actual_fill = buy_px * (1.0 + self.slippage)
                    order_shares = max(100, int(round(capital_per_level / actual_fill / 100.0)) * 100)
                    entry_cost = actual_fill * order_shares * self.broker_fee
                    total_cost = actual_fill * order_shares + entry_cost
                    if cash < total_cost:
                        continue
                    cash -= total_cost
                    lvl_dict[lvl_idx] = {
                        'shares': order_shares,
                        'entry_price': actual_fill,
                        'tp_price': g['tps'][lvl_idx - 1],
                        'entry_cost': entry_cost,
                        'settlement': get_settlement_dt(ts)
                    }
                    completed_trades.append({
                        'timestamp': ts,
                        'ticker': ticker,
                        'level_idx': lvl_idx,
                        'action': 'BUY',
                        'price': actual_fill,
                        'shares': order_shares,
                        'reason': 'grid_limit',
                        'pnl': 0.0
                    })
                    
            pos_val = sum(
                sum(p['shares'] * float(bar_group.loc[t]['close']) for p in lvl_dict.values())
                for t, lvl_dict in positions.items() if t in bar_group.index
            )
            equity_curve.append({'bar_close': ts, 'spot_equity': cash + pos_val, 'pos_val': pos_val})
            
        trades_df = pd.DataFrame(completed_trades)
        eq_df = pd.DataFrame(equity_curve)
        eq_series = eq_df.set_index(pd.to_datetime(eq_df['bar_close']))['spot_equity']
        pos_val_series = eq_df.set_index(pd.to_datetime(eq_df['bar_close']))['pos_val']
        
        # 5. Macro Futures Hedge Overlay
        date_col = 'datetime' if 'datetime' in vn30_daily.columns else 'bar_close'
        vd = vn30_daily.sort_values(date_col).copy()
        vd['date'] = pd.to_datetime(vd[date_col]).dt.date
        vd['sma50'] = vd['close'].rolling(self.macro_sma_days).mean()
        vd['roc20'] = vd['close'].pct_change(self.macro_roc_days)
        
        # Strictly zero lookahead: lagged by 1 day (shift(1))
        # Yesterday's closing auction determines today's defensive hedge status
        vd['is_bear'] = ((vd['close'] < vd['sma50']) & (vd['roc20'] < self.macro_roc_threshold)).shift(1).fillna(False)
        vd['is_bull'] = ((vd['close'] > vd['sma50']) & (vd['roc20'] > 0)).shift(1).fillna(False)
        reg_map = vd.set_index('date')[['is_bear', 'is_bull']].to_dict('index')
        
        f_df = vn30f_bars[(vn30f_bars['bar_close'] >= start_dt) & (vn30f_bars['bar_close'] < end_dt)].sort_values('bar_close').reset_index(drop=True)
        f_df['date'] = pd.to_datetime(f_df['bar_close']).dt.date
        
        # Align open inventory valuation to futures timestamps
        pos_val_aligned = pos_val_series.reindex(pd.to_datetime(f_df['bar_close']), method='ffill').fillna(0).values
        
        cur_pos = 0
        cum_pnl = 0.0
        f_hist = []
        closes_f = f_df['close'].values
        dates_f = f_df['date'].values
        ts_f = pd.to_datetime(f_df['bar_close']).values
        max_c = self.n_vn30f_contracts
        pv = self.contract_value
        ff = self.futures_fee
        
        for i in range(len(f_df)):
            d = dates_f[i]
            reg = reg_map.get(d, {'is_bear': False, 'is_bull': False})
            open_inv = pos_val_aligned[i]
            
            if self.hedging_mode == 'dynamic_delta_hedge':
                # Approach 1: True Dynamic Delta-Neutral Defensive Hedge
                # Sizing: Short contracts scale dynamically with open inventory at risk
                # Zero naked longs / zero speculative leverage in bull or neutral regimes
                if reg['is_bear'] and open_inv > 0:
                    contract_notional = closes_f[i] * pv
                    target_contracts = -min(max_c, int(round(open_inv / contract_notional)))
                else:
                    target_contracts = 0
            elif self.hedging_mode == 'unhedged':
                target_contracts = 0
            elif self.hedging_mode == 'macro_cta':
                # Approach 2: Bi-Directional CTA Momentum Overlay
                target_contracts = -max_c if reg['is_bear'] else (+max_c if reg['is_bull'] else 0)
            elif self.hedging_mode == 'legacy':
                # Unlagged legacy model for audit comparison
                is_bear_m0 = (vd.set_index('date')['close'] < vd.set_index('date')['sma50']) & (vd.set_index('date')['roc20'] < self.macro_roc_threshold)
                is_bull_m0 = (vd.set_index('date')['close'] > vd.set_index('date')['sma50']) & (vd.set_index('date')['roc20'] > 0)
                reg_m0 = {'is_bear': is_bear_m0.get(d, False), 'is_bull': is_bull_m0.get(d, False)}
                target_contracts = -max_c if reg_m0['is_bear'] else (+max_c if reg_m0['is_bull'] else 0)
            else:
                target_contracts = 0
                
            if i > 0 and cur_pos != 0:
                cum_pnl += cur_pos * (closes_f[i] - closes_f[i-1]) * pv
            if target_contracts != cur_pos:
                cum_pnl -= abs(target_contracts - cur_pos) * closes_f[i] * pv * ff
                cur_pos = target_contracts
            f_hist.append({'bar_close': ts_f[i], 'hedge_pnl': cum_pnl})
            
        f_series = pd.DataFrame(f_hist).set_index('bar_close')['hedge_pnl']
        f_aligned = f_series.reindex(eq_series.index, method='ffill').fillna(0)
        
        # 6. Combined Fund Equity
        comb_eq = eq_series + self.hedge_buffer_capital + f_aligned
        self.equity_series = comb_eq
        self.trades = completed_trades
        
        # 7. Compute Performance Metrics
        self.metrics = self.calculate_performance_metrics(trades_df, f_aligned)
        return self.metrics

    def calculate_performance_metrics(self, trades_df=None, f_aligned=None):
        """
        Calculate standard performance metrics matching DynamicGrid specification
        """
        if self.equity_series is None or len(self.equity_series) == 0:
            return None
            
        comb_eq = self.equity_series
        initial_val = float(self.capital)
        final_val = float(comb_eq.iloc[-1])
        net_profit = final_val - initial_val
        hpr = (final_val / initial_val - 1.0) * 100.0
        
        # Drawdown calculation
        peak = comb_eq.cummax()
        dd = (comb_eq - peak) / peak
        max_dd = float(dd.min()) * 100.0
        
        # Longest drawdown duration (days)
        is_in_dd = dd < 0
        dd_runs = (~is_in_dd).cumsum()[is_in_dd]
        if not dd_runs.empty:
            longest_bars = dd_runs.value_counts().max()
            longest_days = int(round(longest_bars / 8.0))  # 8 thirty-minute bars per day
        else:
            longest_days = 0
            
        # Annualized return and risk ratios
        days_span = (comb_eq.index[-1] - comb_eq.index[0]).total_seconds() / 86400.0
        years = max(days_span / 365.25, 0.05)
        cagr = (((final_val / initial_val) ** (1.0 / years)) - 1.0) * 100.0
        
        rets = comb_eq.pct_change().dropna()
        ann_factor = np.sqrt(2016)  # 252 days * 8 bars
        sharpe = float(rets.mean() / rets.std() * ann_factor) if rets.std() > 0 else 0.0
        
        downside = rets[rets < 0]
        sortino = float(rets.mean() / downside.std() * ann_factor) if len(downside) > 0 and downside.std() > 0 else 0.0
        calmar = (cagr / abs(max_dd)) if max_dd != 0 else 0.0
        
        # Decomposed PnL
        sells = [t for t in self.trades if t.get('action') == 'SELL']
        tp_pnl = sum(t['pnl'] for t in sells if t.get('reason') == 'target')
        drag_pnl = sum(t['pnl'] for t in sells if t.get('reason') != 'target')
        hedge_pnl = float(f_aligned.iloc[-1]) if f_aligned is not None else 0.0
        
        return {
            'total_trades': len(sells),
            'net_profit': net_profit,
            'hpr': hpr,
            'annual_return': cagr,
            'max_drawdown': max_dd,
            'longest_drawdown': longest_days,
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'calmar_ratio': calmar,
            'final_capital': final_val,
            'spot_harvest_pnl': tp_pnl,
            'spot_drag_pnl': drag_pnl,
            'hedge_pnl': hedge_pnl,
            'equity_series': comb_eq
        }

    def print_results(self, output_dir=None):
        """
        Print and save backtest results in exact DynamicGrid layout
        """
        metrics = self.metrics
        if metrics is None:
            print("Cannot calculate performance metrics due to missing data.")
            return

        results = [
            f"Total trades: {metrics['total_trades']}",
            f"Net profit: {metrics['net_profit']:,.0f} VND",
            f"Holding Period Return (HPR): {metrics['hpr']:.2f}%",
            f"Annualized Return: {metrics['annual_return']:.2f}%",
            f"Maximum drawdown: {metrics['max_drawdown']:.2f}%",
            f"Longest Drawdown: {metrics['longest_drawdown']} days",
            f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}",
            f"Sortino Ratio: {metrics['sortino_ratio']:.2f}",
            f"Final capital: {metrics['final_capital']:,.0f} VND",
            f"Trade log saved to: {self.log_file}"
        ]
        
        # Print results to console
        for line in results:
            print(line)
            
        print("\nComponent Breakdown:")
        print(f"  • Spot Grid Harvest PnL: {metrics['spot_harvest_pnl']:+,.0f} VND")
        print(f"  • Spot Market Drag PnL:   {metrics['spot_drag_pnl']:+,.0f} VND")
        print(f"  • Macro Futures Leg PnL: {metrics['hedge_pnl']:+,.0f} VND")
        print(f"  • Calmar Ratio:          {metrics['calmar_ratio']:.2f}")

        # Save artifacts to file if output_dir provided
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            
            # 1. Performance metrics
            with open(os.path.join(output_dir, "performance_metrics.txt"), "w") as f:
                for line in results:
                    f.write(line + "\n")
                f.write(f"\nSpot Grid Harvest PnL: {metrics['spot_harvest_pnl']:+,.0f} VND\n")
                f.write(f"Spot Market Drag PnL: {metrics['spot_drag_pnl']:+,.0f} VND\n")
                f.write(f"Macro Futures Leg PnL: {metrics['hedge_pnl']:+,.0f} VND\n")
                f.write(f"Calmar Ratio: {metrics['calmar_ratio']:.2f}\n")
                    
            # 2. Trade log
            if self.trades:
                trades_df = pd.DataFrame(self.trades)
                trades_df.to_csv(os.path.join(output_dir, "trade_log.txt"), sep="\t", index=False)
                trades_df.to_csv(os.path.join(output_dir, "trade_log.csv"), index=False)
                
            # 3. Equity series
            if metrics['equity_series'] is not None:
                metrics['equity_series'].to_csv(os.path.join(output_dir, "equity_series.csv"))
                
                # 4. Plot equity curve
                fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), gridspec_kw={'height_ratios': [3, 1]})
                
                eq = metrics['equity_series']
                ax1.plot(eq.index, eq.values / 1e9, label='Strategy Portfolio Value (Billion VND)', color='#10b981', lw=1.8)
                ax1.axhline(self.capital / 1e9, color='#64748b', linestyle='--', label=f'Initial Capital ({self.capital/1e9:.1f}B)')
                ax1.set_title("Minimalist ER Grid Strategy with Macro Futures Overlay — Equity Curve", fontsize=13, fontweight='bold', pad=12)
                ax1.set_ylabel("Portfolio Value (Billion VND)", fontsize=11)
                ax1.grid(True, alpha=0.3)
                ax1.legend(loc='upper left')
                
                # Drawdown subplot
                peak = eq.cummax()
                dd = (eq - peak) / peak * 100.0
                ax2.fill_between(dd.index, dd.values, 0, color='#ef4444', alpha=0.35, label='Drawdown (%)')
                ax2.plot(dd.index, dd.values, color='#dc2626', lw=1.0)
                ax2.set_ylabel("Drawdown (%)", fontsize=11)
                ax2.set_xlabel("Time", fontsize=11)
                ax2.grid(True, alpha=0.3)
                ax2.legend(loc='lower left')
                
                plt.tight_layout()
                fig_path = os.path.join(output_dir, "equity_curve.png")
                plt.savefig(fig_path, dpi=200)
                plt.close(fig)
                print(f"Equity curve saved to: {fig_path}")
