import sys, os
import yaml

curr_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.abspath(os.path.join(curr_dir, "../.."))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

from src.data_fetcher import prepare_data
from src.logic import MinimalistERGridBacktest

def main():
    print("=" * 70)
    print("CANDIDATE 1: MINIMALIST ER GRID + MACRO HEDGE — OUT-OF-SAMPLE (2024)")
    print("=" * 70)
    
    cfg_path = os.path.join(curr_dir, "config/config.yaml")
    with open(cfg_path, 'r') as f:
        config = yaml.safe_load(f)
        
    data_bundle = prepare_data(config, "out_sample")
    strat_cfg = config['strategy']
    
    backtest = MinimalistERGridBacktest(
        capital=strat_cfg.get('capital', 2_000_000_000),
        initial_spot_capital=strat_cfg.get('initial_spot_capital', 1_000_000_000),
        hedge_buffer_capital=strat_cfg.get('hedge_buffer_capital', 1_000_000_000),
        contract_value=strat_cfg.get('contract_value', 100_000),
        margin_rate=strat_cfg.get('margin_rate', 0.20),
        broker_fee=strat_cfg.get('broker_fee', 0.0015),
        sell_tax=strat_cfg.get('sell_tax', 0.0010),
        futures_fee=strat_cfg.get('futures_fee', 0.0005),
        slippage=strat_cfg.get('slippage', 0.0005),
        selection_lookback=strat_cfg.get('selection_lookback', 40),
        selection_rebalance_days=strat_cfg.get('selection_rebalance_days', 10),
        top_k=strat_cfg.get('top_k', 4),
        n_levels=strat_cfg.get('n_levels', 18),
        grid_spacing_pct=strat_cfg.get('grid_spacing_pct', 0.018),
        stop_buffer_levels=strat_cfg.get('stop_buffer_levels', 2),
        macro_sma_days=strat_cfg.get('macro_sma_days', 50),
        macro_roc_days=strat_cfg.get('macro_roc_days', 20),
        macro_roc_threshold=strat_cfg.get('macro_roc_threshold', -0.02),
        n_vn30f_contracts=strat_cfg.get('n_vn30f_contracts', 10),
        n_bull_contracts=strat_cfg.get('n_bull_contracts', 10),
        hedging_mode=strat_cfg.get('hedging_mode', 'dynamic_delta_hedge'),
        hedging_direction=strat_cfg.get('hedging_direction', 'both'),
        trend_filter=strat_cfg.get('trend_filter', 'none')
    )
    
    res = backtest.backtest(data_bundle)
    print(f"Total Return:   {res['hpr']:+.2f}% ({res['net_profit']:+,.0f} VND)")
    print(f"CAGR:           {res['annual_return']:+.2f}%")
    print(f"Max Drawdown:   {res['max_drawdown']:.2f}%")
    print(f"Sharpe Ratio:   {res['sharpe_ratio']:.3f}")
    print(f"Calmar Ratio:   {res['calmar_ratio']:.3f}")
    print(f"Spot Harvest:   {res['spot_harvest_pnl']:+,.0f} VND")
    print(f"Spot Drag:      {res['spot_drag_pnl']:+,.0f} VND")
    print(f"Futures Leg:    {res['hedge_pnl']:+,.0f} VND")

if __name__ == '__main__':
    main()
