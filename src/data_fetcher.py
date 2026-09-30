"""
Data Fetcher Module for Minimalist ER Grid Strategy
Emulating algotrade-education/DynamicGrid repository architecture.

Supports loading pre-extracted split Parquet/CSV files and live database fetching
via PostgreSQL from algotradeDB.
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

# Try importing psycopg for database functionality
try:
    import psycopg
except ImportError:
    psycopg = None

# Load environment variables if available
load_dotenv()


def resolve_path(path_str):
    """
    Resolve a file path intelligently whether executed from:
    1. strategies/minimalist_er_grid_hedge/
    2. Project root (/Users/ttt/Final_Projects_v1/)
    3. Direct absolute path
    """
    if not path_str:
        return path_str
    if os.path.isabs(path_str) and os.path.exists(path_str):
        return path_str
    
    # Check current working directory
    if os.path.exists(path_str):
        return os.path.abspath(path_str)
        
    # Check relative to strategy root
    strat_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    p_strat = os.path.join(strat_root, path_str)
    if os.path.exists(p_strat):
        return p_strat
        
    # Check relative to workspace root (two levels up from src)
    ws_root = os.path.abspath(os.path.join(strat_root, "../.."))
    p_ws = os.path.join(ws_root, path_str)
    if os.path.exists(p_ws):
        return p_ws
        
    # Default to resolved absolute path under workspace root if possible
    return p_ws


def load_query_from_file(filepath="data/query.txt"):
    """
    Load SQL query from text file
    """
    resolved_path = resolve_path(filepath)
    try:
        with open(resolved_path, 'r') as file:
            return file.read()
    except Exception as e:
        print(f"Error loading query from {resolved_path}: {e}")
        return None


def fetch_vn30_data(query=None):
    """
    Fetch VN30 data from PostgreSQL database (algotradeDB)
    """
    if psycopg is None:
        print("psycopg is not installed. Database fetching unavailable.")
        return None
        
    print("Fetching data from database...")
    try:
        if query is None:
            query = load_query_from_file()
            if query is None:
                print("Failed to load query from file.")
                return None
                
        # Resolve database credentials from environment or database.json
        db_host = os.getenv('DB_HOST')
        db_port = os.getenv('DB_PORT', 5432)
        db_name = os.getenv('DB_NAME')
        db_user = os.getenv('DB_USER')
        db_pass = os.getenv('DB_PASSWORD')
        
        if not (db_host and db_name and db_user and db_pass):
            # Fallback to database.json in workspace
            db_json_path = resolve_path("database.json")
            if os.path.exists(db_json_path):
                with open(db_json_path, 'r') as f:
                    db_cfg = json.load(f)
                    db_host = db_cfg.get('host', db_host)
                    db_port = db_cfg.get('port', db_port)
                    db_name = db_cfg.get('database', db_name)
                    db_user = db_cfg.get('user', db_user)
                    db_pass = db_cfg.get('password', db_pass)

        with psycopg.connect(
            host=db_host,
            port=int(db_port),
            dbname=db_name,
            user=db_user,
            password=db_pass
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                cols = [desc[0] for desc in cur.description]
                result = cur.fetchall()
                if not result:
                    print("Query returned no results.")
                    return None
                df = pd.DataFrame(result, columns=cols)
                print(f"Successfully fetched {len(df)} records from database.")
                return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None


def save_data_to_file(data, filename="data/vn30_data.csv"):
    """
    Save time series data to CSV or Parquet
    """
    try:
        resolved = resolve_path(filename)
        os.makedirs(os.path.dirname(resolved) or '.', exist_ok=True)
        if filename.endswith('.parquet'):
            data.to_parquet(resolved, index=False)
        else:
            data.to_csv(resolved, index=True)
        print(f"Data saved to {resolved}")
        return True
    except Exception as e:
        print(f"Error saving data to {filename}: {e}")
        return False


def load_data_from_file(filename):
    """
    Load data file supporting both Parquet and CSV formats
    """
    resolved = resolve_path(filename)
    if not os.path.exists(resolved):
        print(f"Warning: File {resolved} does not exist.")
        return None
        
    try:
        if resolved.endswith('.parquet'):
            df = pd.read_parquet(resolved)
        else:
            df = pd.read_csv(resolved)
            
        col_names = [c.lower() for c in df.columns]
        # Normalize date column
        for cand in ['bar_close', 'datetime', 'date', 'tradingdate']:
            if cand in col_names:
                actual = df.columns[col_names.index(cand)]
                df['bar_close'] = pd.to_datetime(df[actual])
                break
                
        print(f"Loaded {resolved}: {len(df):,} records.")
        return df
    except Exception as e:
        print(f"Error loading {resolved}: {e}")
        return None


def prepare_data(config, mode="in_sample"):
    """
    Prepare data bundle for in_sample, out_sample, or holdout mode.
    
    Returns:
        dict with:
            - 'bars': pd.DataFrame of spot equity bars
            - 'vn30f': pd.DataFrame of 30m VN30F1M futures bars
            - 'vn30d': pd.DataFrame of VN30 daily benchmark bars
            - 'start_date': str YYYY-MM-DD
            - 'end_date': str YYYY-MM-DD
    """
    data_cfg = config.get('data', {})
    
    # 1. Determine date ranges and file paths
    if mode == "in_sample":
        file_path = data_cfg.get('in_sample_file', "data/in_sample/in_sample_30m.parquet")
        start_date = data_cfg.get('in_sample', {}).get('start_date', "2021-01-01")
        end_date = data_cfg.get('in_sample', {}).get('end_date', "2024-01-01")
    elif mode == "out_sample":
        file_path = data_cfg.get('out_sample_file', "data/out_of_sample/out_of_sample_30m.parquet")
        start_date = data_cfg.get('out_sample', {}).get('start_date', "2024-01-01")
        end_date = data_cfg.get('out_sample', {}).get('end_date', "2025-01-01")
    elif mode in ["holdout", "forward_holdout"]:
        file_path = data_cfg.get('holdout_file', "data/forward_holdout/forward_holdout_30m.parquet")
        start_date = data_cfg.get('holdout', {}).get('start_date', "2026-01-01")
        end_date = data_cfg.get('holdout', {}).get('end_date', "2026-10-01")
    else:
        raise ValueError(f"Unknown data mode '{mode}'. Choose in_sample, out_sample, or holdout.")

    bars_df = None
    
    # 2. Live database fetching if configured
    if data_cfg.get('fetch_data', False):
        bars_df = fetch_vn30_data()
        if bars_df is not None and data_cfg.get('save_fetched_data', False):
            save_data_to_file(bars_df, "data/vn30_data.csv")
            
    # 3. Load from disk file
    if bars_df is None:
        bars_df = load_data_from_file(file_path)
        
    if bars_df is None or bars_df.empty:
        print(f"Error: Could not load spot data for {mode} from {file_path}")
        return None
        
    # 4. Load benchmark futures & daily index data
    vn30f_path = data_cfg.get('vn30f_file', "data/benchmark/vn30f1m_30m.parquet")
    vn30d_path = data_cfg.get('vn30_daily_file', "data/benchmark/vn30_daily.parquet")
    
    vn30f_df = load_data_from_file(vn30f_path)
    vn30d_df = load_data_from_file(vn30d_path)
    
    if vn30f_df is None or vn30d_df is None:
        print("Error: Could not load VN30F or VN30 daily benchmark datasets.")
        return None
        
    # Standardize column types
    bars_df['bar_close'] = pd.to_datetime(bars_df['bar_close'])
    vn30f_df['bar_close'] = pd.to_datetime(vn30f_df['bar_close'])
    
    date_col = 'bar_close' if 'bar_close' in vn30d_df.columns else ('datetime' if 'datetime' in vn30d_df.columns else 'date')
    vn30d_df['bar_close'] = pd.to_datetime(vn30d_df[date_col])

    # Filter date range
    dt_start = pd.to_datetime(start_date)
    dt_end = pd.to_datetime(end_date)
    
    bars_filtered = bars_df[(bars_df['bar_close'] >= dt_start) & (bars_df['bar_close'] < dt_end)].copy()
    vn30f_filtered = vn30f_df[(vn30f_df['bar_close'] >= dt_start) & (vn30f_df['bar_close'] < dt_end)].copy()
    vn30d_filtered = vn30d_df[(vn30d_df['bar_close'] >= dt_start) & (vn30d_df['bar_close'] < dt_end)].copy()

    print(f"Prepared {mode} data: {len(bars_filtered):,} spot bars ({bars_filtered['tickersymbol'].nunique() if 'tickersymbol' in bars_filtered else 0} tickers), "
          f"{len(vn30f_filtered):,} futures bars across [{start_date} to {end_date}].")

    return {
        'bars': bars_filtered,
        'vn30f': vn30f_filtered,
        'vn30d': vn30d_filtered,
        'start_date': start_date,
        'end_date': end_date
    }
