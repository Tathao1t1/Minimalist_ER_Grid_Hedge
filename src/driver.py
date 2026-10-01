"""
Main Driver for Minimalist ER Grid Strategy with Macro Futures Overlay
Emulating algotrade-education/DynamicGrid repository architecture.

Usage:
  python src/driver.py -h
  python src/driver.py --mode backtest --data in_sample
  python src/driver.py --mode backtest --data out_sample
  python src/driver.py --mode backtest --data holdout
  python src/driver.py --mode optimize
"""

import argparse
import yaml
import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import optuna

# Modern, clean sans-serif typography configuration for publication-grade charts
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica', 'Liberation Sans', 'sans-serif']
plt.rcParams['axes.edgecolor'] = '#cbd5e1'
plt.rcParams['axes.linewidth'] = 0.8
plt.rcParams['grid.color'] = '#e2e8f0'

# Ensure current directory is in sys.path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_fetcher import prepare_data, resolve_path
from logic import MinimalistERGridBacktest


def setup_results_dir(config, run_mode):
    """
    Setup the results directory structure matching DynamicGrid convention:
    results/<run_mode>/<YYYYMMDD_HHMMSS>/
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = config.get('results', {}).get('base_directory', 'results')
    
    # Resolve relative to strategy root if needed
    if not os.path.isabs(base_dir):
        strat_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        base_dir = os.path.join(strat_root, base_dir)
        
    output_dir = os.path.join(base_dir, run_mode, timestamp)
    os.makedirs(output_dir, exist_ok=True)
    
    # Save a reproducible snapshot of the config
    with open(os.path.join(output_dir, 'config.yaml'), 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
        
    return output_dir


def run_backtest(config, data_mode, output_dir):
    """
    Run backtest using the specified configuration and data split.
    """
    print(f"\n=======================================================")
    print(f"RUNNING BACKTEST [{data_mode.upper()}]")
    print(f"=======================================================")
    
    # Prepare data bundle
    data_bundle = prepare_data(config, data_mode)
    if data_bundle is None:
        print(f"Error: Failed to load {data_mode} data.")
        return None
        
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
        n_bull_contracts=strat_cfg.get('n_bull_contracts', None),
        hedging_mode=strat_cfg.get('hedging_mode', 'dynamic_delta_hedge'),
        hedging_direction=strat_cfg.get('hedging_direction', 'both'),
        trend_filter=strat_cfg.get('trend_filter', 'none')
    )
    
    backtest.log_file = os.path.join(output_dir, "trade_log.txt")
    metrics = backtest.backtest(data_bundle)
    
    # Print and save results
    print(f"\nBacktest results ({data_mode}):")
    backtest.print_results(output_dir)
    return metrics


def objective(trial, config, data_bundle):
    """
    Objective function for Optuna optimization
    """
    opt_cfg = config.get('optimization', {})
    
    n_levels_range = opt_cfg.get('n_levels_range', [14, 22])
    grid_spacing_range = opt_cfg.get('grid_spacing_pct_range', [0.014, 0.022])
    n_contracts_range = opt_cfg.get('n_vn30f_contracts_range', [6, 14])
    
    # Sample trial parameters
    n_levels = trial.suggest_int("n_levels", n_levels_range[0], n_levels_range[1], step=2)
    grid_spacing_pct = trial.suggest_float("grid_spacing_pct", grid_spacing_range[0], grid_spacing_range[1], step=0.002)
    n_contracts = trial.suggest_int("n_vn30f_contracts", n_contracts_range[0], n_contracts_range[1], step=2)
    
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
        n_levels=n_levels,
        grid_spacing_pct=grid_spacing_pct,
        stop_buffer_levels=strat_cfg.get('stop_buffer_levels', 2),
        macro_sma_days=strat_cfg.get('macro_sma_days', 50),
        macro_roc_days=strat_cfg.get('macro_roc_days', 20),
        macro_roc_threshold=strat_cfg.get('macro_roc_threshold', -0.02),
        n_vn30f_contracts=n_contracts,
        n_bull_contracts=strat_cfg.get('n_bull_contracts', None),
        hedging_mode=strat_cfg.get('hedging_mode', 'dynamic_delta_hedge'),
        hedging_direction=strat_cfg.get('hedging_direction', 'both'),
        trend_filter=strat_cfg.get('trend_filter', 'none')
    )
    
    metrics = backtest.backtest(data_bundle)
    if metrics is None or 'sharpe_ratio' not in metrics or 'final_capital' not in metrics:
        return -float('inf')
        
    final_capital = metrics['final_capital']
    sharpe = metrics['sharpe_ratio']
    
    if final_capital < strat_cfg.get('capital', 2_000_000_000) * 0.8:
        return -float('inf')
        
    trial.set_user_attr('final_capital', final_capital)
    trial.set_user_attr('cagr', metrics['annual_return'])
    trial.set_user_attr('max_dd', metrics['max_drawdown'])
    trial.set_user_attr('calmar', metrics['calmar_ratio'])
    trial.set_user_attr('metrics', metrics)
    
    return sharpe


def log_trial_callback(study, trial, output_dir):
    """
    Callback function for logging trial results matching DynamicGrid
    """
    final_capital = trial.user_attrs.get('final_capital', 0)
    cagr = trial.user_attrs.get('cagr', 0.0)
    max_dd = trial.user_attrs.get('max_dd', 0.0)
    
    log_file = os.path.join(output_dir, "optuna_trials.txt")
    with open(log_file, "a") as f:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        trial_info = (
            f"[{timestamp}] Trial {trial.number:02d} | Sharpe: {trial.value:6.3f} | "
            f"CAGR: {cagr:6.2f}% | MaxDD: {max_dd:6.2f}% | "
            f"Final Cap: {final_capital:,.0f} VND | "
            f"Params: {trial.params} | Best Trial {study.best_trial.number} (Sharpe: {study.best_value:.3f})"
        )
        f.write(trial_info + "\n")
    print(trial_info)


def run_optimization(config, output_dir):
    """
    Run parameter optimization using Optuna on in-sample data
    """
    print("\n=======================================================")
    print("RUNNING OPTUNA OPTIMIZATION ON IN-SAMPLE DATA")
    print("=======================================================")
    
    data_bundle = prepare_data(config, "in_sample")
    if data_bundle is None:
        print("Error: Failed to load in-sample data for optimization.")
        return None
        
    opt_cfg = config.get('optimization', {})
    n_trials = opt_cfg.get('n_trials', 50)
    
    print(f"Optimizing {n_trials} trials to maximize Sharpe Ratio...")
    
    callback = lambda study, trial: log_trial_callback(study, trial, output_dir)
    study = optuna.create_study(direction="maximize")
    
    study.optimize(
        lambda trial: objective(trial, config, data_bundle),
        n_trials=n_trials,
        callbacks=[callback]
    )
    
    best_trial = study.best_trial
    best_params = best_trial.params
    print("\n" + "=" * 55)
    print("OPTIMIZATION RESULTS")
    print("=" * 55)
    print(f"Best Sharpe Ratio: {best_trial.value:.3f}")
    print(f"Best Parameters:   {best_params}")
    print(f"Final Capital:     {best_trial.user_attrs.get('final_capital', 0):,.0f} VND")
    
    # Save best parameters to YAML
    with open(os.path.join(output_dir, "best_parameters.yaml"), "w") as f:
        yaml.dump(best_params, f, default_flow_style=False)
        
    # Re-run backtest with best parameters in optimized_backtest/
    print("\nRunning backtest with optimized parameters...")
    optimized_dir = os.path.join(output_dir, "optimized_backtest")
    os.makedirs(optimized_dir, exist_ok=True)
    
    opt_config = yaml.safe_load(yaml.dump(config))
    for k, v in best_params.items():
        opt_config['strategy'][k] = v
        
    strat_cfg = opt_config['strategy']
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
        n_levels=best_params['n_levels'],
        grid_spacing_pct=best_params['grid_spacing_pct'],
        stop_buffer_levels=strat_cfg.get('stop_buffer_levels', 2),
        macro_sma_days=strat_cfg.get('macro_sma_days', 50),
        macro_roc_days=strat_cfg.get('macro_roc_days', 20),
        macro_roc_threshold=strat_cfg.get('macro_roc_threshold', -0.02),
        n_vn30f_contracts=best_params['n_vn30f_contracts']
    )
    
    backtest.log_file = os.path.join(optimized_dir, "trade_log.txt")
    backtest.backtest(data_bundle)
    backtest.print_results(optimized_dir)
    return best_params


def main():
    """
    Main driver entry point with CLI matching DynamicGrid
    """
    parser = argparse.ArgumentParser(description='Grid Trading Backtest and Optimization')
    parser.add_argument('--mode', type=str, choices=['backtest', 'optimize'], required=True,
                        help='Run mode: backtest or optimize')
    parser.add_argument('--data', type=str, choices=['in_sample', 'out_sample', 'holdout'], default='in_sample',
                        help='Data to use for backtest (only applicable for backtest mode)')
    parser.add_argument('--config', type=str, default=None,
                        help='Path to config file')

    args = parser.parse_args()
    
    # Resolve config path
    if args.config is None:
        cfg_path = resolve_path("config/config.yaml")
        if not os.path.exists(cfg_path):
            cfg_path = resolve_path("strategies/minimalist_er_grid_hedge/config/config.yaml")
    else:
        cfg_path = resolve_path(args.config)
        
    try:
        with open(cfg_path, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config file from {cfg_path}: {e}")
        return

    # Setup results directory
    output_dir = setup_results_dir(config, args.mode)
    print(f"Results will be saved to: {output_dir}")

    if args.mode == 'backtest':
        run_backtest(config, args.data, output_dir)
    elif args.mode == 'optimize':
        if args.data != 'in_sample':
            print("Warning: Optimization must be run on in-sample data. Using in_sample split.")
        run_optimization(config, output_dir)

    print(f"\nAll results saved to: {output_dir}")


if __name__ == "__main__":
    main()
