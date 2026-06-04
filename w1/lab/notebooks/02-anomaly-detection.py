import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from sklearn.ensemble import IsolationForest
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

METRICS_PATH = '../metrics/cart-service.csv'
OUTPUT_PLOT = '02-multi_metric_anomaly.png'

def rolling_z_score(series, window=60): # 60 * 30s = 30 minutes
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()
    z_scores = (series - rolling_mean) / (rolling_std + 1e-9)
    return np.abs(z_scores) > 3

def isolation_forest_1d(series):
    X = series.fillna(0).values.reshape(-1, 1)
    clf = IsolationForest(contamination=0.05, random_state=42)
    clf.fit(X)
    preds = clf.predict(X)
    return preds == -1

def main():
    print(f"--- Đang phân tích Đa Độ Đo (Multi-metric Anomaly Detection) ---")
    df = pd.read_csv(METRICS_PATH)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    metrics_to_check = [
        'memory_usage_bytes', 
        'jvm_gc_pause_ms_avg', 
        'http_5xx_rate', 
        'cpu_usage_percent'
    ]
    
    results = []
    
    # Analyze each metric
    for col in metrics_to_check:
        df[f'{col}_z_anomaly'] = rolling_z_score(df[col])
        df[f'{col}_if_anomaly'] = isolation_forest_1d(df[col])
        
        # Get first alert time
        z_first = df[df[f'{col}_z_anomaly']]['timestamp'].min()
        if_first = df[df[f'{col}_if_anomaly']]['timestamp'].min()
        
        results.append({
            'Metric': col,
            'Z-Score First Alert': str(z_first) if not pd.isna(z_first) else "None",
            'IsolationForest First Alert': str(if_first) if not pd.isna(if_first) else "None"
        })
        
    # Tạo Dataframe hiển thị kết quả
    res_df = pd.DataFrame(results)
    print("\n--- ANOMALY FIRST DETECTION TIME ---")
    print(res_df.to_markdown(index=False))
    print("------------------------------------\n")
    
    # Trực quan hóa tiến trình (Anomaly Progression) cho Memory và GC
    fig, axes = plt.subplots(4, 1, figsize=(15, 12), sharex=True)
    
    for i, col in enumerate(metrics_to_check):
        ax = axes[i]
        ax.plot(df['timestamp'], df[col], label=f'Raw {col}', color='gray', alpha=0.7)
        
        # Plot Z-score anomalies
        anom_z = df[df[f'{col}_z_anomaly']]
        if not anom_z.empty:
            ax.scatter(anom_z['timestamp'], anom_z[col], color='red', s=20, label='Z-Score Alert', zorder=5)
            
        # Plot iForest anomalies
        anom_if = df[df[f'{col}_if_anomaly']]
        if not anom_if.empty:
            ax.scatter(anom_if['timestamp'], anom_if[col], color='blue', s=20, marker='x', label='iForest Alert', zorder=4)
            
        ax.set_title(f'Anomaly Progression: {col}')
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        
        # Highlight alert time
        alert_time = pd.to_datetime('2026-06-01 23:04:00+00:00')
        ax.axvline(x=alert_time, color='red', linestyle=':', linewidth=2)
        
        # Highlight Silent Period if memory
        if col == 'memory_usage_bytes':
            first_signal = pd.to_datetime(res_df.iloc[0]['Z-Score First Alert'])
            if not pd.isna(first_signal):
                ax.axvspan(first_signal, alert_time, color='yellow', alpha=0.2, label='Silent Period')
                ax.legend(loc='upper left')

    plt.xlabel('Time')
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    plt.tight_layout()
    plt.savefig(OUTPUT_PLOT)
    print(f"Đã lưu biểu đồ: {OUTPUT_PLOT}")

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    main()
