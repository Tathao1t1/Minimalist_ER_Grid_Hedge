import sys, os
import pandas as pd
import json

sys.path.insert(0, "/Users/ttt/Final_Projects_v1")
from framework.data_loader import load_data
from strategies.minimalist_er_grid_hedge.backtester import run_combined_fund
from framework.benchmark import get_benchmark_metrics

def main():
    print("=" * 80)
    print("CANDIDATE 1: MINIMALIST ER GRID + MACRO HEDGE — FORWARD BLIND HOLDOUT (2026)")
    print("=" * 80)
    
    bars = load_data('forward_holdout')
    vn30f = pd.read_parquet("data/benchmark/vn30f1m_30m.parquet")
    vn30d = pd.read_parquet("data/benchmark/vn30_daily.parquet")
    
    start_dt = str(bars['bar_close'].min())
    end_dt   = str(bars['bar_close'].max())
    print(f"Executing over holdout window: {start_dt} to {end_dt}")
    
    with open("strategies/minimalist_er_grid_hedge/config.json") as f:
        cfg = json.load(f)
    p = {
        'n_levels': cfg['parameters']['n_levels'],
        'grid_spacing_pct': cfg['parameters']['grid_spacing_pct'],
        'n_vn30f_contracts': cfg['parameters']['n_vn30f_contracts']
    }
    
    res = run_combined_fund(bars, vn30f, vn30d, "2026-01-01", "2026-10-01", p)
    bench = get_benchmark_metrics("forward_holdout", 2_000_000_000.0)
    
    print("\n" + "=" * 80)
    print("FINAL FORWARD HOLDOUT RESULTS:")
    print("=" * 80)
    print(f"• Total Return:     {res['total_return']*100:+.2f}% ({res['final_val'] - 2e9:+,.0f} VND) | VN30: {bench.get('total_return', 0)*100:+.2f}%")
    print(f"• Annualized CAGR:  {res['cagr']:+.2f}%")
    print(f"• Max Drawdown:     {res['max_drawdown']:.2f}% | VN30: {bench.get('max_drawdown', 0)*100:.2f}%")
    print(f"• Sharpe Ratio:     {res['sharpe_ratio']:.3f} | VN30: {bench.get('sharpe_ratio', 0):.3f}")
    print(f"• Calmar Ratio:     {res['calmar_ratio']:.3f} | VN30: {bench.get('calmar_ratio', 0):.3f}")
    print(f"• Spot Harvest PnL: {res['spot_harvest_pnl']:+,.0f} VND (Trades: {res['total_trades']})")
    print(f"• Spot Drag Loss:   {res['spot_drag_pnl']:+,.0f} VND")
    print(f"• Futures Leg PnL:  {res['hedge_pnl']:+,.0f} VND")
    print("=" * 80)

if __name__ == '__main__':
    main()
