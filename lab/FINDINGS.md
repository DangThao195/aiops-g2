# AIOps W1 Findings - Group 2

## 1. Ghi chú chất lượng dữ liệu

Bộ dữ liệu gồm 5 file metrics CSV và 2 file logs JSONL:

- Metrics: `api-gateway.csv`, `cart-service.csv`, `order-service.csv`, `payment-service.csv`, `product-service.csv`
- Logs: `cart-service.log.jsonl`, `order-service.log.jsonl`

Các file metrics không có giá trị null và timestamp là duy nhất. Tuy nhiên, mỗi file metrics chỉ có `2,820` dòng thay vì `2,880` dòng như kỳ vọng nếu đủ 24 giờ với interval 30 giây. Tất cả các file metrics đều thiếu cùng một đoạn 30 phút:

| Service | Timestamp trước gap | Timestamp sau gap | Số điểm thiếu |
|---|---:|---:|---:|
| cart-service | `2026-06-01T11:29:30Z` | `2026-06-01T12:00:00Z` | 60 |
| order-service | `2026-06-01T11:29:30Z` | `2026-06-01T12:00:00Z` | 60 |
| payment-service | `2026-06-01T11:29:30Z` | `2026-06-01T12:00:00Z` | 60 |
| api-gateway | `2026-06-01T11:29:30Z` | `2026-06-01T12:00:00Z` | 60 |
| product-service | `2026-06-01T11:29:30Z` | `2026-06-01T12:00:00Z` | 60 |

Gap này không che mất giai đoạn chính của incident, vì chuỗi bất thường quan trọng của `cart-service` bắt đầu rõ từ sau `14:00Z`.

## 2. Phân tích metrics

Metrics được phân tích trước để xác định **WHEN** và **WHERE**. Metrics là tín hiệu định lượng theo thời gian, phù hợp để dựng timeline, so sánh service nào bất thường trước, và khoanh vùng blast radius.

Hướng phân tích:

- Dùng Rolling Z-score để phát hiện điểm lệch khỏi baseline gần.
- Dùng Isolation Forest để phát hiện bất thường đa biến trên `cart-service`.
- Dùng sustained threshold để xác nhận các tín hiệu có ý nghĩa vận hành, tránh kết luận từ outlier đơn lẻ.

Các mốc metrics quan trọng:

| Service | Metric | Mốc bất thường đầu tiên | Điều kiện |
|---|---|---:|---:|
| product-service | `http_p99_latency_ms` | `2026-06-01T03:03:00Z` | >100 ms sustained |
| product-service | `http_5xx_rate` | `2026-06-01T03:17:00Z` | >5% sustained |
| product-service | `cpu_usage_percent` | `2026-06-01T03:41:00Z` | >60% sustained |
| cart-service | `jvm_gc_pause_ms_avg` | `2026-06-01T18:06:00Z` | >100 ms sustained |
| cart-service | `memory_pct` | `2026-06-01T19:37:00Z` | >70% memory limit sustained |
| cart-service | `http_5xx_rate` | `2026-06-01T21:26:30Z` | >5% sustained |
| api-gateway | `cart_upstream_error_rate` | `2026-06-01T21:02:00Z` | >5% sustained |
| order-service | `upstream_timeout_rate` | `2026-06-01T21:52:00Z` | >10% sustained |
| payment-service | `upstream_timeout_rate` | `2026-06-01T22:37:30Z` | >10% sustained |

Kết quả Isolation Forest trên `cart-service`:

| Detector | Feature set | First anomaly | Evidence |
|---|---|---:|---|
| Isolation Forest | `memory_pct`, `jvm_gc_pause_ms_avg`, `http_p99_latency_ms`, `http_5xx_rate`, `restart_delta` | `2026-06-01T18:04:30Z` | memory `49.17%`, GC pause `161.1 ms`, p99 latency `361.1 ms` |

Điều này cho thấy `cart-service` đã bất thường rõ trước khi có OOM và trước khi lỗi lan mạnh sang các service khác.

### Kết luận từ metrics

Nếu chỉ nhìn metrics, `product-service` là early suspicious signal sớm nhất lúc `03:03Z`. Tuy nhiên, service có chuỗi metric dẫn trực tiếp tới restart loop là `cart-service`.

`api-gateway`, `order-service`, và `payment-service` bất thường muộn hơn, nên nhiều khả năng là service bị ảnh hưởng downstream, không phải nguồn gốc chính.

## 3. Phân tích logs

Sau khi metrics khoanh vùng vấn đề vào `cart-service`, Drain3 được dùng để parse log thành template. Mục tiêu là giải thích **WHAT**: cơ chế nào đứng sau các anomaly trong metrics.

Cách làm:

- Đọc `cart-service.log.jsonl` và `order-service.log.jsonl`.
- Dùng Drain3 gom message thành log template.
- Đếm số lần xuất hiện template theo bucket 30 phút.
- Tìm template xuất hiện sớm và template có spike bất thường.

Các template quan trọng:

| Template | First seen | First spike | Tổng count | Ý nghĩa |
|---|---:|---:|---:|---|
| `ProductCatalogCache eviction failed: heap pressure too high` | `2026-06-01T06:32:33Z` | `2026-06-01T14:00:00Z` | 2,655 | Cache eviction thất bại do heap pressure |
| `GC overhead limit warning: <*> <*>` | `2026-06-01T06:31:11Z` | `2026-06-01T14:00:00Z` | 1,326 | JVM bắt đầu có dấu hiệu GC pressure |
| `Slow response detected endpoint=/api/cart <*>` | `2026-06-01T06:41:41Z` | `2026-06-01T14:00:00Z` | 1,227 | Cart latency tăng theo memory/GC pressure |
| `OutOfMemoryError imminent: available heap < 5%` | `2026-06-01T19:59:00Z` | n/a | 944 | JVM gần hết heap |
| `Container OOMKilled: memory limit exceeded` | `2026-06-01T19:59:02Z` | n/a | 819 | Container bị kill do vượt memory limit |
| `Cart service timeout after <*>` | `2026-06-01T00:04:18Z` | `2026-06-01T20:30:00Z` | 1,018 | `order-service` bắt đầu timeout mạnh khi gọi cart |

Log analysis cho thấy vấn đề không chỉ là lỗi 5xx cuối ngày. Từ rất sớm, `cart-service` đã có dấu hiệu liên quan tới `ProductCatalogCache`, heap pressure, GC warning, và slow response. Những template này spike từ `14:00Z`, trước OOM gần 6 tiếng.

### 3.1 Field phụ trong cart logs: cache size và heap used

Ngoài message text, `cart-service.log.jsonl` còn có các field số giúp củng cố root cause:

| Field | Ý nghĩa | Evidence |
|---|---|---|
| `cache_size_mb` | Kích thước `ProductCatalogCache` trong cart-service | Max khoảng `1799.9 MB`, tức gần `1.8 GB` |
| `heap_used_mb` | Heap đã dùng khi JVM báo sắp hết bộ nhớ | Dao động khoảng `1909-1980 MB` trong giai đoạn OOM |
| `memory_limit_bytes` | Memory limit của container | `2147483648 bytes`, xấp xỉ `2 GB` |

Điểm quan trọng: cache có lúc phình tới gần `1.8 GB`, trong khi container chỉ có memory limit khoảng `2 GB`. Khi `OutOfMemoryError imminent` xuất hiện, `heap_used_mb` đã lên khoảng `1.9-1.98 GB`. Đây là bằng chứng trực tiếp hơn cho chuỗi:

`ProductCatalogCache phình lớn`  
→ `cache eviction thất bại`  
→ `heap/memory pressure tăng`  
→ `OOMKilled`

## 4. Timeline tổng hợp metrics + logs

| Timestamp | Service | Evidence |
|---|---|---|
| `2026-06-01T03:03:00Z` | product-service | Product p99 latency sustained >100 ms |
| `2026-06-01T03:17:00Z` | product-service | Product 5xx sustained >5% |
| `2026-06-01T06:32:33Z` | cart-service | `ProductCatalogCache eviction failed` xuất hiện lần đầu |
| `2026-06-01T14:00:00Z` | cart-service | Cache eviction, GC warning, slow response templates spike |
| `2026-06-01T18:04:30Z` | cart-service | Isolation Forest phát hiện anomaly đa biến |
| `2026-06-01T18:06:00Z` | cart-service | GC pause sustained >100 ms |
| `2026-06-01T19:37:00Z` | cart-service | Memory sustained >70% limit |
| `2026-06-01T19:59:00Z` | cart-service | `OutOfMemoryError imminent` |
| `2026-06-01T19:59:02Z` | cart-service | `Container OOMKilled` |
| `2026-06-01T20:00:00Z` | cart-service | `container_restart_count` tăng lần đầu |
| `2026-06-01T21:02:00Z` | api-gateway | `cart_upstream_error_rate` sustained >5% |
| `2026-06-01T21:52:00Z` | order-service | `upstream_timeout_rate` sustained >10% |
| `2026-06-01T22:37:30Z` | payment-service | `upstream_timeout_rate` sustained >10% |

Timeline này cho thấy chuỗi lỗi hợp lý:

`ProductCatalogCache eviction failure`  
→ heap pressure  
→ GC pause tăng  
→ memory tăng  
→ OOMKilled  
→ restart loop  
→ lỗi lan sang gateway/order/payment

## 5. Root cause hypothesis

Root failure có khả năng cao nằm ở `cart-service`, liên quan tới memory pressure và `ProductCatalogCache`.

Giả thuyết chính:

`cart-service` gặp vấn đề trong cơ chế cache/eviction của `ProductCatalogCache`. Cache eviction thất bại xuất hiện từ `06:32Z` và spike mạnh từ `14:00Z`. Field `cache_size_mb` trong log cho thấy `ProductCatalogCache` có lúc phình lên gần `1.8 GB`, trong khi container chỉ có memory limit khoảng `2 GB`. Điều này làm heap pressure tăng dần, kéo theo GC pause tăng từ `18:06Z`. Khi `OutOfMemoryError imminent` xuất hiện lúc `19:59Z`, field `heap_used_mb` nằm khoảng `1.9-1.98 GB`, rất sát giới hạn memory. Container sau đó bị `OOMKilled`, Kubernetes bắt đầu restart pod lúc `20:00Z`. Restart loop làm cart không ổn định, gây timeout và 5xx cho các service phụ thuộc.

Về `product-service`:

`product-service` có anomaly rất sớm từ `03:03Z`, gồm latency, 5xx và CPU. Vì log của cart nhắc nhiều tới `ProductCatalogCache`, product degradation có thể là yếu tố kích hoạt: ví dụ cache refresh thất bại, cache phình ra, hoặc eviction hoạt động bất thường. Tuy nhiên, dataset không có product logs hoặc trace join để chứng minh liên kết trực tiếp từ product anomaly sang cart memory leak. Vì vậy, `product-service` nên được ghi là **early suspicious signal / possible trigger**, chưa gọi là root cause.

## 6. Limitations

- Không có `product-service` logs, nên không thể chứng minh trực tiếp product anomaly gây ra cache issue trong cart.
- Không có distributed trace đầy đủ để nối request từ product sang cart hoặc từ cart sang downstream service.
- Rolling Z-score có thể bắt outlier sớm nhưng nhiễu, nên báo cáo dùng sustained threshold và Isolation Forest để xác nhận tín hiệu có ý nghĩa vận hành.
- Metrics thiếu 30 phút từ `11:30Z` đến `11:59:30Z`, dù gap này không nằm trong failure window chính.

## 7. Notebook và cách chạy lại

Bài phân tích chính được trình bày theo 4 notebook trong `lab/notebooks`. Chạy 4 notebook này theo thứ tự là đủ để tái tạo phần phân tích chính từ raw data:

| Notebook | Vai trò |
|---|---|
| `01_eda_metrics.ipynb` | EDA metrics, data quality, schema, request rate, cart core metrics, downstream failures, product early signal |
| `02_metric_anomaly.ipynb` | Rolling Z-score, sustained threshold, Isolation Forest trên `cart-service` |
| `03_log_analysis.ipynb` | Drain3 log template mining, log level theo thời gian, template spike |
| `04_incident_timeline.ipynb` | Cross-signal timeline, xếp hạng first anomaly theo service, kết luận WHEN/WHERE/WHAT |

Pipeline tổng quát:

`Metrics first -> locate WHEN/WHERE -> Logs second -> explain WHAT/root cause`

Các script `.py` là helper tùy chọn để rebuild nhanh kết quả, plots và notebooks:

```powershell
python lab\analyze_incident.py
python lab\build_notebooks.py
```

Các output được sinh ra:

- `lab/results/metric_summary.csv`
- `lab/results/metric_gaps.csv`
- `lab/results/rolling_z_anomalies.csv`
- `lab/results/isolation_forest_cart_anomalies.csv`
- `lab/results/sustained_thresholds.csv`
- `lab/results/drain3_template_spikes.csv`
- `lab/results/log_pattern_summary.csv`
- `lab/results/cart_log_numeric_fields.csv`
- `lab/results/cart_log_numeric_summary.csv`
- `lab/results/incident_timeline.csv`
- `lab/results/drain3_parsed_logs.csv`
- `lab/plots/*.png`
- `lab/notebooks/*.ipynb`
