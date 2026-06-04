import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import os
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

METRICS_DIR = '../metrics/'
OUTPUT_TIMELINE = '01-multi_service_timeline.png'
OUTPUT_HEATMAP = '01-correlation_heatmap.png'

def main():
    print("--- Đang load metrics của cả 4 services ---")
    
    # Đọc dữ liệu
    cart_df = pd.read_csv(os.path.join(METRICS_DIR, 'cart-service.csv'))
    order_df = pd.read_csv(os.path.join(METRICS_DIR, 'order-service.csv'))
    payment_df = pd.read_csv(os.path.join(METRICS_DIR, 'payment-service.csv'))
    api_df = pd.read_csv(os.path.join(METRICS_DIR, 'api-gateway.csv'))
    
    # Convert timestamp
    for df in [cart_df, order_df, payment_df, api_df]:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
    
    # Ghép các cột lỗi quan trọng vào 1 DataFrame để phân tích tương quan
    merged_df = pd.DataFrame(index=cart_df.index)
    merged_df['cart_5xx'] = cart_df['http_5xx_rate']
    merged_df['cart_restart'] = cart_df['container_restart_count']
    merged_df['cart_memory_gb'] = cart_df['memory_usage_bytes'] / (1024**3)
    merged_df['cart_gc_pause'] = cart_df['jvm_gc_pause_ms_avg']
    merged_df['order_timeout'] = order_df['upstream_timeout_rate']
    merged_df['payment_timeout'] = payment_df['upstream_timeout_rate']
    merged_df['api_gw_cart_error'] = api_df['cart_upstream_error_rate']
    
    # 1. Vẽ Multi-service Timeline Comparison
    fig, axes = plt.subplots(4, 1, figsize=(15, 12), sharex=True)
    
    # Trục 1: Cart Service - Nơi bắt nguồn
    axes[0].plot(merged_df.index, merged_df['cart_memory_gb'], label='Memory (GB)', color='blue')
    ax0_twin = axes[0].twinx()
    ax0_twin.plot(merged_df.index, merged_df['cart_gc_pause'], label='GC Pause (ms)', color='orange', alpha=0.6)
    axes[0].set_title('[Root] Cart Service: Memory & GC Over Time')
    axes[0].legend(loc='upper left')
    ax0_twin.legend(loc='upper right')
    
    # Trục 2: Lỗi bắt đầu bùng nổ ở Cart
    axes[1].plot(merged_df.index, merged_df['cart_5xx'], label='HTTP 5xx (%)', color='red')
    ax1_twin = axes[1].twinx()
    ax1_twin.plot(merged_df.index, merged_df['cart_restart'], label='Restarts', color='purple', linestyle='--')
    axes[1].set_title('[Trigger] Cart Service: 5xx Errors & Pod Restarts')
    axes[1].legend(loc='upper left')
    ax1_twin.legend(loc='upper right')
    
    # Trục 3: Cascade lên Order & Payment
    axes[2].plot(merged_df.index, merged_df['order_timeout'], label='Order Timeout (%)', color='darkorange')
    axes[2].plot(merged_df.index, merged_df['payment_timeout'], label='Payment Timeout (%)', color='brown')
    axes[2].set_title('[Cascade] Order & Payment Services: Upstream Timeouts')
    axes[2].legend(loc='upper left')
    
    # Trục 4: Cascade lên API Gateway
    axes[3].plot(merged_df.index, merged_df['api_gw_cart_error'], label='API Gateway Cart Error (%)', color='black')
    axes[3].set_title('[Impact] API Gateway: User-facing Errors')
    axes[3].set_xlabel('Time')
    axes[3].legend(loc='upper left')
    
    for ax in axes:
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        
        # Highlight mốc 23:04 (thời điểm alert nổ)
        alert_time = pd.to_datetime('2026-06-01 23:04:00+00:00')
        ax.axvline(x=alert_time, color='red', linestyle=':', linewidth=2, label='Alert Triggered (23:04)')
    
    plt.tight_layout()
    plt.savefig(OUTPUT_TIMELINE)
    print(f"Đã lưu biểu đồ Multi-service Timeline: {OUTPUT_TIMELINE}")
    
    # 2. Vẽ Heatmap Correlation Matrix
    plt.figure(figsize=(10, 8))
    # Tính ma trận tương quan Pearson
    corr = merged_df.corr()
    sns.heatmap(corr, annot=True, cmap='coolwarm', fmt=".2f", vmin=-1, vmax=1)
    plt.title('Correlation Matrix Between Services')
    plt.tight_layout()
    plt.savefig(OUTPUT_HEATMAP)
    print(f"Đã lưu biểu đồ Heatmap: {OUTPUT_HEATMAP}")
    
    print("EDA Nâng cấp Hoàn tất!")

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    main()
