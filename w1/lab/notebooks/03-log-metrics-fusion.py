import json
import os
import sys
import pandas as pd
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

CART_LOG = '../logs/cart-service.log.jsonl'
ORDER_LOG = '../logs/order-service.log.jsonl'
OUTPUT_FILE = '03-log_metrics_fusion.txt'

def mine_log(file_path):
    config = TemplateMinerConfig()
    config.load("") 
    config.profiling_enabled = False
    miner = TemplateMiner(config=config)
    
    error_events = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                msg = data.get('message', '')
                lvl = data.get('level', 'INFO')
                ts = data.get('timestamp', '')
                
                # Drain
                miner.add_log_message(msg)
                
                # Capture errors
                if lvl in ['ERROR', 'FATAL', 'WARN']:
                    error_events.append({
                        'timestamp': ts,
                        'level': lvl,
                        'message': msg
                    })
            except:
                pass
                
    return miner, error_events

def main():
    print("--- Phân tích Logs & Map với Metrics (Fusion) ---")
    
    # 1. Mine Cart Logs
    print(f"Mining {CART_LOG}...")
    cart_miner, cart_errors = mine_log(CART_LOG)
    
    # 2. Mine Order Logs
    print(f"Mining {ORDER_LOG}...")
    order_miner, order_errors = mine_log(ORDER_LOG)
    
    # Lấy các Error đáng chú ý
    # Dùng list comprehension để tìm log đầu tiên xuất hiện của mỗi loại pattern
    def find_first_occurrence(errors, keyword):
        for e in errors:
            if keyword.lower() in e['message'].lower():
                return e
        return None
        
    cart_oom = find_first_occurrence(cart_errors, 'OutOfMemoryError')
    cart_gc = find_first_occurrence(cart_errors, 'GC overhead')
    cart_cache = find_first_occurrence(cart_errors, 'ProductCatalogCache eviction failed')
    order_timeout = find_first_occurrence(order_errors, 'timeout')
    order_retry = find_first_occurrence(order_errors, 'retry')
    
    # In ra báo cáo Fusion
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("=== LOG & METRIC EVENT FUSION TIMELINE ===\n\n")
        f.write("| Service | Log Event (First Seen) | Timestamp | Description |\n")
        f.write("|---------|-----------------------|-----------|-------------|\n")
        
        if cart_cache:
            f.write(f"| cart | Cache Eviction Failed | {cart_cache['timestamp']} | {cart_cache['message']} |\n")
        if cart_gc:
            f.write(f"| cart | GC Overhead Limit | {cart_gc['timestamp']} | {cart_gc['message']} |\n")
        if cart_oom:
            f.write(f"| cart | OutOfMemoryError | {cart_oom['timestamp']} | {cart_oom['message']} |\n")
        if order_timeout:
            f.write(f"| order | Upstream Timeout | {order_timeout['timestamp']} | {order_timeout['message']} |\n")
        if order_retry:
            f.write(f"| order | Retry Storm | {order_retry['timestamp']} | {order_retry['message']} |\n")
            
        f.write("\n\n=== TOP 5 CART TEMPLATES ===\n")
        for c in sorted(cart_miner.drain.clusters, key=lambda it: it.size, reverse=True)[:5]:
            f.write(f"Size: {c.size} | {c.get_template()}\n")
            
        f.write("\n=== TOP 5 ORDER TEMPLATES ===\n")
        for c in sorted(order_miner.drain.clusters, key=lambda it: it.size, reverse=True)[:5]:
            f.write(f"Size: {c.size} | {c.get_template()}\n")

    print(f"Hoàn tất! Đã lưu kết quả tại {OUTPUT_FILE}")

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    main()
