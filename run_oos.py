import sys, os
import pandas as pd
import json

sys.path.insert(0, "/Users/ttt/Final_Projects_v1")
from framework.data_loader import load_data
from strategies.minimalist_er_grid_hedge.backtester import run_combined_fund

def main():
    print("=" * 70)
    print("CANDIDATE 1: MINIMALIST ER GRID + MACRO HEDGE — OUT-OF-SAMPLE (2024)")
    print("=" * 70)
    
    bars = load_data('out_of_sample')
    vn30f = pd.read_parquet("data/benchmark/vn30f1m_30m.parquet")
    vn30d = pd.read_parquet("data/benchmark/vn30_daily.parquet")
    
    with open("strategies/minimalist_er_grid_hedge/config.json") as f:
        cfg = json.load(f)
    p = {
        'n_levels': cfg['parameters']['n_levels'],
        'grid_spacing_pct': cfg['parameters']['grid_spacing_pct'],
        'n_vn30f_contracts': cfg['parameters']['n_vn30f_contracts']
    }
    
    res = run_combined_fund(bars, vn30f, vn30d, "2024-01-01", "2025-01-01", p)
    print(f"Total Return:   {res['total_return']*100:+.2f}% ({res['final_val'] - 2e9:+,.0f} VND)")
    print(f"CAGR:           {res['cagr']:+.2f}%")
    print(f"Max Drawdown:   {res['max_drawdown']:.2f}%")
    print(f"Sharpe Ratio:   {res['sharpe_ratio']:.3f}")
    print(f"Calmar Ratio:   {res['calmar_ratio']:.3f}")
    print(f"Spot Harvest:   {res['spot_harvest_pnl']:+,.0f} VND")
    print(f"Spot Drag:      {res['spot_drag_pnl']:+,.0f} VND")
    print(f"Futures Leg:    {res['hedge_pnl']:+,.0f} VND")

if __name__ == '__main__':
    main()
