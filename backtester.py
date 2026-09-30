import sys, os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def kaufman_er(prices):
    direction = abs(prices[-1] - prices[0])
    volatility = np.sum(np.abs(np.diff(prices)))
    return direction / volatility if volatility > 0 else 1.0

def get_settlement_dt(trade_dt: datetime) -> datetime:
    d = trade_dt.date()
    added = 0
    while added < 2:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return datetime.combine(d, datetime.strptime("13:00", "%H:%M").time())

def build_zero_overlap_whitelist(bars_df, lookback_days=40, rebalance_days=10, top_k=4):
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
        candidates.sort(key=lambda x: x[1])
        whitelist[rebal_date] = [c[0] for c in candidates[:top_k]]
    return whitelist

def run_pure_grid_sim(bars_df, whitelist_by_date, n_levels=18, spacing_pct=0.018, max_stocks=4, initial_capital=1e9, stop_buffer=2):
    bars_df = bars_df.copy()
    if bars_df["close"].max() < 1000:
        for c in ["open", "high", "low", "close"]:
            bars_df[c] *= 1000.0
    bars_df = bars_df.sort_values(["bar_close", "tickersymbol"]).reset_index(drop=True)
    
    anchors = {}
    for ticker, df in bars_df.groupby("tickersymbol"):
        df = df.sort_values("bar_close")
        anchors[ticker] = df.set_index("bar_close")["close"].rolling(50).mean()
        
    capital_per_stock = initial_capital / max_stocks
    capital_per_level = capital_per_stock / n_levels
    broker_fee = 0.0015
    sell_tax = 0.0010
    slippage = 0.0005
    
    cash = float(initial_capital)
    grids = {}
    positions = {}
    completed_trades = []
    equity_curve = []
    
    wl_dates = sorted(whitelist_by_date.keys())
    cur_wl = []
    next_wl_idx = 0
    
    for ts, bar_group in bars_df.groupby("bar_close", sort=True):
        bar_group = bar_group.set_index("tickersymbol")
        cur_date = ts.date()
        
        if next_wl_idx < len(wl_dates) and cur_date >= wl_dates[next_wl_idx]:
            cur_wl = whitelist_by_date[wl_dates[next_wl_idx]]
            next_wl_idx += 1
            
        # 1. SELL / EXIT PASS
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
                actual_fill = fill_px * (1.0 - slippage)
                exit_cost = actual_fill * pos['shares'] * (broker_fee + sell_tax)
                proceeds = actual_fill * pos['shares'] - exit_cost
                cash += proceeds
                pnl = proceeds - (pos['entry_price'] * pos['shares'] + pos['entry_cost'])
                completed_trades.append({
                    'ticker': ticker, 'level_idx': lvl, 'reason': reason,
                    'pnl': pnl, 'shares': pos['shares'], 'exit_ts': ts
                })
                
            if is_floor_hit:
                positions.pop(ticker, None)
                if ticker in grids: del grids[ticker]
            elif len(lvl_dict) == 0 and ticker not in cur_wl:
                positions.pop(ticker, None)
                if ticker in grids: del grids[ticker]

        # 2. GRID ACTIVATION
        for ticker in list(grids.keys()):
            if ticker not in cur_wl and (ticker not in positions or len(positions[ticker]) == 0):
                del grids[ticker]
                
        avail_slots = max_stocks - len(grids)
        if avail_slots > 0 and len(cur_wl) > 0:
            for ticker in cur_wl:
                if ticker in grids or ticker not in bar_group.index:
                    continue
                bar = bar_group.loc[ticker]
                sma_val = anchors[ticker].get(ts, np.nan)
                if np.isnan(sma_val) or abs(float(bar['close']) - sma_val) / sma_val > 0.03:
                    continue
                spacing = sma_val * spacing_pct
                levels = [round(sma_val - k * spacing, 2) for k in range(1, n_levels + 1)]
                tps = [round(sma_val - (k - 1) * spacing, 2) for k in range(1, n_levels + 1)]
                stop_px = sma_val - (n_levels + stop_buffer) * spacing
                grids[ticker] = {'anchor': sma_val, 'levels': levels, 'tps': tps, 'stop': stop_px}
                positions.setdefault(ticker, {})
                avail_slots -= 1
                if avail_slots <= 0: break
                
        # 3. BUY PASS
        for ticker, g in grids.items():
            if ticker not in bar_group.index: continue
            bar_l = float(bar_group.loc[ticker, 'low'])
            lvl_dict = positions.setdefault(ticker, {})
            for lvl_idx in range(1, n_levels + 1):
                if lvl_idx in lvl_dict: continue
                buy_px = g['levels'][lvl_idx - 1]
                if bar_l > buy_px: continue
                actual_fill = buy_px * (1.0 + slippage)
                order_shares = max(100, int(round(capital_per_level / actual_fill / 100.0)) * 100)
                entry_cost = actual_fill * order_shares * broker_fee
                total_cost = actual_fill * order_shares + entry_cost
                if cash < total_cost: continue
                cash -= total_cost
                lvl_dict[lvl_idx] = {
                    'shares': order_shares, 'entry_price': actual_fill,
                    'tp_price': g['tps'][lvl_idx - 1], 'entry_cost': entry_cost,
                    'settlement': get_settlement_dt(ts)
                }
                
        pos_val = sum(
            sum(p['shares'] * float(bar_group.loc[t]['close']) for p in lvl_dict.values())
            for t, lvl_dict in positions.items() if t in bar_group.index
        )
        equity_curve.append({'bar_close': ts, 'portfolio_value': cash + pos_val})
        
    return pd.DataFrame(completed_trades), pd.DataFrame(equity_curve)

def run_combined_fund(bars_df, vn30f_bars, vn30_daily, start_dt, end_dt, params=None):
    if params is None:
        params = {'n_levels': 18, 'grid_spacing_pct': 0.018, 'n_vn30f_contracts': 10}
        
    whitelist = build_zero_overlap_whitelist(bars_df, lookback_days=40, rebalance_days=10, top_k=4)
    trades_df, eq_df = run_pure_grid_sim(bars_df, whitelist, n_levels=params['n_levels'], spacing_pct=params['grid_spacing_pct'])
    eq_series = eq_df.set_index(pd.to_datetime(eq_df['bar_close']))['portfolio_value']
    
    # Futures Overlay
    col = "datetime" if "datetime" in vn30_daily.columns else "bar_close"
    f_df = vn30f_bars[(vn30f_bars['bar_close'] >= start_dt) & (vn30f_bars['bar_close'] < end_dt)].sort_values('bar_close').reset_index(drop=True)
    vd = vn30_daily[(pd.to_datetime(vn30_daily[col]) >= start_dt) & (pd.to_datetime(vn30_daily[col]) < end_dt)].copy()
    vd['date'] = pd.to_datetime(vd[col]).dt.date
    vd['sma50'] = vd['close'].rolling(50).mean()
    vd['roc20'] = vd['close'].pct_change(20)
    vd['is_bear'] = (vd['close'] < vd['sma50']) & (vd['roc20'] < -0.02)
    vd['is_bull'] = (vd['close'] > vd['sma50']) & (vd['roc20'] > 0)
    reg_map = vd.set_index('date')[['is_bear', 'is_bull']].to_dict('index')
    
    f_df['date'] = pd.to_datetime(f_df['bar_close']).dt.date
    point_val = 100_000
    fee_per_contract = 5.0 / 10000.0
    cur_pos = 0; cum_pnl = 0.0; f_hist = []
    closes_f = f_df['close'].values; dates_f = f_df['date'].values; ts_f = pd.to_datetime(f_df['bar_close']).values
    n_contracts = params['n_vn30f_contracts']
    
    for i in range(len(f_df)):
        d = dates_f[i]
        reg = reg_map.get(d, {'is_bear': False, 'is_bull': False})
        t_pos = -1 if reg['is_bear'] else (+1 if reg['is_bull'] else 0)
        if i > 0 and cur_pos != 0:
            cum_pnl += cur_pos * n_contracts * (closes_f[i] - closes_f[i-1]) * point_val
        if t_pos != cur_pos:
            cum_pnl -= abs(t_pos - cur_pos) * n_contracts * closes_f[i] * point_val * fee_per_contract
            cur_pos = t_pos
        f_hist.append({'bar_close': ts_f[i], 'hedge_pnl': cum_pnl})
        
    f_series = pd.DataFrame(f_hist).set_index('bar_close')['hedge_pnl']
    f_aligned = f_series.reindex(eq_series.index, method='ffill').fillna(0)
    comb_eq = eq_series + 1_000_000_000.0 + f_aligned
    
    final_val = float(comb_eq.iloc[-1])
    tot_ret = (final_val / 2e9) - 1.0
    dd = (comb_eq - comb_eq.cummax()) / comb_eq.cummax()
    max_dd = float(dd.min()) * 100.0
    years = (comb_eq.index[-1] - comb_eq.index[0]).days / 365.25
    cagr = (((final_val / 2e9) ** (1 / years)) - 1.0) * 100.0
    rets = comb_eq.pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * np.sqrt(2016)) if rets.std() > 0 else 0.0
    calmar = (cagr / abs(max_dd)) if max_dd != 0 else 0.0
    
    tp_pnl = trades_df[trades_df['reason'] == 'target']['pnl'].sum() if len(trades_df) > 0 else 0
    drag_pnl = trades_df[trades_df['reason'] != 'target']['pnl'].sum() if len(trades_df) > 0 else 0
    
    return {
        'total_return': tot_ret,
        'cagr': cagr,
        'max_drawdown': max_dd,
        'sharpe_ratio': sharpe,
        'calmar_ratio': calmar,
        'final_val': final_val,
        'spot_harvest_pnl': tp_pnl,
        'spot_drag_pnl': drag_pnl,
        'hedge_pnl': float(f_aligned.iloc[-1]),
        'total_trades': len(trades_df),
        'equity_series': comb_eq
    }
