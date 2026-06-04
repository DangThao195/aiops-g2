import json
import os
import sys
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

LOG_FILE = '../logs/cart-service.log.jsonl'
OUTPUT_FILE = '03-log_clusters.txt'

def main():
    print(f"Bắt đầu phân tích log từ {LOG_FILE} bằng Drain3...")
    
    # Cấu hình Drain3
    config = TemplateMinerConfig()
    config.load("") # Load default
    config.profiling_enabled = False
    
    template_miner = TemplateMiner(config=config)
    
    total_lines = 0
    error_lines = 0
    
    # 1. Khai phá Log Templates
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            total_lines += 1
            try:
                log_data = json.loads(line)
                message = log_data.get('message', '')
                level = log_data.get('level', 'INFO')
                
                # Trích xuất template cho tất cả các dòng
                template_miner.add_log_message(message)
                
                if level in ['ERROR', 'FATAL']:
                    error_lines += 1
            except Exception as e:
                pass
                
    print(f"Đã duyệt qua {total_lines} dòng log. Có {error_lines} dòng lỗi.")
    
    # 2. Thống kê kết quả
    sorted_clusters = sorted(template_miner.drain.clusters, key=lambda it: it.size, reverse=True)
    
    print("\n--- TOP 10 LOG TEMPLATES XUẤT HIỆN NHIỀU NHẤT ---")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out_f:
        out_f.write(f"Total lines: {total_lines}\n")
        out_f.write(f"Total error lines: {error_lines}\n\n")
        out_f.write("--- TOP LOG TEMPLATES ---\n")
        
        for cluster in sorted_clusters[:10]:
            info = f"Cluster ID {cluster.cluster_id} | Size: {cluster.size} | Template: {cluster.get_template()}"
            print(info)
            out_f.write(info + "\n")
            
    print(f"\nĐã lưu chi tiết vào file: {OUTPUT_FILE}")

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    main()
