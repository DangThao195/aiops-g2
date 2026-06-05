# Technical Postmortem: ShopX Cart Service Incident (W1 Lab)

> [!NOTE]
> Mã nguồn phân tích chi tiết và các biểu đồ trực quan hóa dữ liệu được lưu tại:
> * Phân tích Metrics và Anomaly Detection đa dịch vụ: **[assignment.ipynb](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/assignment.ipynb)**
> * Báo cáo trực quan hóa tự động: **[metrics_analysis.ipynb](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/metrics_analysis.ipynb)** và **[logs_analysis.ipynb](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/logs_analysis.ipynb)**

---

## 1. WHEN — Mốc thời gian & Tín hiệu cảnh báo sớm (Silent Signals)

Qua phân tích tương quan chuỗi thời gian (temporal correlation) và log của toàn bộ 5 microservices, chúng tôi xác định được quá trình tích tụ lỗi và lan truyền bất thường như sau:

| Thời gian (UTC) | Dịch vụ (Service) | Loại sự kiện | Chi tiết kỹ thuật & Dữ liệu thực tế |
| :--- | :--- | :--- | :--- |
| **00:46:13** | `cart-service` | Log Warning | DB Connection pool cảnh báo sắp cạn kiệt: `connections=50/50`. |
| **06:30:19** | `cart-service` | Log Warning | JVM GC Overhead cảnh báo lần đầu: `pause=384ms heap=88%`. |
| **06:32:33** | `cart-service` | Log Error | **Lỗi Cache Eviction đầu tiên (Silent Signal)**: `ProductCatalogCache eviction failed: heap pressure too high`. Xuất hiện trước alert chính thức **16.5 tiếng**. |
| **16:28:30** | `cart-service` | Metric Anomaly (IQR) | Bất thường đầu tiên của JVM GC pause (`jvm_gc_pause_ms_avg`). JVM liên tục dọn rác do áp lực bộ nhớ. |
| **16:37:00** | `cart-service` | Metric Anomaly (IF) | **Isolation Forest (kỹ nghệ đặc trưng)** phát hiện bất thường bộ nhớ ở mức `720.57 MB` (độ tăng trưởng đạt `45.4 MB/s`). |
| **16:43:30** | `cart-service` | Metric Anomaly (IQR) | **Robust IQR** phát hiện bộ nhớ `cart-service` vượt ngưỡng chặn trên (`774.74 MB`). |
| **16:49:30** | `order-service` | Metric Anomaly (IQR) | **Độ trễ p99 của Order Service bắt đầu bất thường** (IQR), chỉ **6 phút** sau khi bộ nhớ Cart Service vượt ngưỡng. |
| **17:49:00** | `cart-service` | Metric | RSS Memory vượt ngưỡng `1.0 GB` và tăng tuyến tính liên tục. |
| **18:53:00** | `cart-service` | Metric Anomaly (Z-score) | **Z-score (3-Sigma)** phát hiện bộ nhớ bất thường khi đạt `1,411.21 MB` (Z-score = 3.03) -- trễ 2.1 tiếng so với IQR. |
| **19:59:02** | `cart-service` | Log Fatal / Crash | **Pod đầu tiên bị OOMKilled** (`cart-service-7d9f8b-hsahx`). Cả 4 pods sập trong vòng 50 giây tiếp theo. |
| **20:00:30** | `api-gateway` | Metric Anomaly (IQR) | Tỷ lệ lỗi kết nối tới Cart Service (`cart_upstream_error_rate`) bất thường trên API Gateway ngay sau loạt crash đầu tiên. |
| **20:11:00** | `api-gateway` | Metric Anomaly (IQR) | HTTP 5xx rate tổng của API Gateway bắt đầu bất thường. |
| **20:45:00** | `payment-service` | Metric Anomaly (IQR) | Lỗi timeout kết nối ngược dòng (`upstream_timeout_rate`) của Payment Service bắt đầu bất thường do nghẽn luồng xử lý Order. |
| **23:04:00** | On-call Alert | Alertmanager | Kỹ sư trực ca nhận một loạt cảnh báo critical (Cart 5xx = 34%, restarts = 7, Order timeout = 28%, Payment timeout = 12%). |
| **23:43:00** | `cart-service` | Metric | Lần restart thứ 7 (cuối cùng) của pod trước khi kỹ sư trực ca can thiệp dập tắt sự cố. |

### Biểu đồ phân tích phát hiện bất thường trên Cart Service Memory:

![Memory Outlier Detection (Z-Score vs. Robust IQR)](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/plot/metrics_anomaly_thresholds.png)

![Isolation Forest Anomaly Detection (Feature Engineered)](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/plot/isolation_forest_anomalies.png)

---

## 2. Kiểm định phân phối (Normality) & Đối chiếu thuật toán phát hiện bất thường

### A. Phân tích đặc trưng phân phối dữ liệu (Normality Test)
Chúng tôi chạy kiểm định thống kê trên các chỉ số chính của toàn bộ 5 CSV metrics. Kết quả cho thấy **100% các metric đo hiệu năng (độ trễ, tỷ lệ lỗi, tài nguyên hệ thống) đều không tuân theo phân phối chuẩn (Non-Gaussian)**:

* **Cart Service Memory**: Skewness = `2.30` $\gg 0$ (lệch phải nặng), Kurtosis = `4.66` (đỉnh nhọn, đuôi dày). Kiểm định Shapiro-Wilk trả về p-value = $7.29957 \times 10^{-59} \ll 0.05$.
* **API Gateway 5xx & Timeout Rates**: Skewness dao động từ `2.5` đến `4.9`, bác bỏ hoàn toàn giả thuyết chuẩn.
* Do phân phối lệch phải nghiêm trọng (dưới tác động của rò rỉ bộ nhớ và tích tụ lỗi), quy tắc Z-score (3-Sigma) bị sai lệch toán học (do mean và std dev bị kéo lệch theo các outliers), dẫn tới việc phát hiện bất thường rất trễ hoặc bỏ sót các tín hiệu sớm.

![Normality Testing Grid](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/plot/metrics_normality_grid.png)

### B. Bảng đối chiếu so sánh thuật toán trên 5 file metrics

Dưới đây là bảng tổng hợp kết quả chạy đối chiếu Z-score (3-Sigma) vs. Robust IQR trên toàn bộ hệ thống ShopX:

| Dịch vụ (Service) | Chỉ số phân tích (Metric) | Skewness | Shapiro p-value | Z-Score Earliest | IQR Earliest | Trễ của Z-score so với IQR |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **cart-service** | `memory_usage_bytes` | 2.30 | $7.30 \times 10^{-59}$ | 18:53:00 | **16:43:30** | **2.16 giờ** (130 phút) |
| **cart-service** | `jvm_gc_pause_ms_avg` | 1.11 | $3.21 \times 10^{-34}$ | 18:04:30 | **16:28:30** | **1.6 giờ** (96 phút) |
| **order-service** | `http_p99_latency_ms` | 2.36 | $4.78 \times 10^{-58}$ | 21:49:30 | **16:49:30** | **5.0 giờ** (300 phút) |
| **order-service** | `upstream_timeout_rate`| 3.08 | $1.72 \times 10^{-69}$ | 22:31:30 | **20:32:00** | **1.99 giờ** (119 phút) |
| **payment-service**| `upstream_timeout_rate`| 3.19 | $3.76 \times 10^{-70}$ | 22:29:00 | **20:45:00** | **1.73 giờ** (104 phút) |
| **api-gateway** | `cart_upstream_error_rate`| 2.83 | $3.11 \times 10^{-68}$ | 22:21:30 | **20:00:30** | **2.35 giờ** (141 phút) |
| **api-gateway** | `http_5xx_rate` | 2.52 | $5.57 \times 10^{-64}$ | 22:12:30 | **20:11:00** | **2.02 giờ** (121 phút) |

> [!TIP]
> **Nhận xét AIOps**: Thuật toán Robust IQR dựa trên phân vị ($Q1, Q3$) hoàn toàn không bị ảnh hưởng bởi các giá trị cực biên (outliers), giúp phát hiện bất thường sớm hơn Z-score từ **2 đến 5 tiếng** trên toàn bộ các microservices. Điều này cho phép on-call engineer có đủ thời gian ứng phó trước khi hệ thống sập hoàn toàn.

![Multi-Service Anomaly Grid (IQR vs Z-score)](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/plot/metrics_multi_service_anomalies.png)

### C. Không gian phát hiện bất thường Isolation Forest (Cart Service)

![Isolation Forest Anomaly Space Scatter Plot](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/plot/isolation_forest_space.png)

---

## 3. WHERE — Vị trí lan truyền & Phân tích chéo (Cascade Correlation)

### A. Kiểm tra tính toàn vẹn của Distributed Tracing
Chúng tôi thực hiện phép toán giao (intersection) tập hợp Trace ID của hai dịch vụ liên đới trực tiếp:
* **Trace ID độc nhất trong `order-service`:** 7,857
* **Trace ID độc nhất trong `cart-service`:** 24,275
* **Trace ID chung (Overlap):** **0**
* **Kết luận**: distributed tracing bị **lỗi lan truyền header (header propagation)** của OpenTelemetry/APM. `cart-service` không kế thừa `trace_id` từ `order-service` mà tự tạo Trace ID mới cho mỗi request nhận được.

### B. Tương quan thời gian (Temporal Correlation) và Tiến trình đổ vỡ cascade
Vì tracing hỏng, chúng tôi dùng phương pháp **Temporal Correlation** (ghép nối log theo mili-giây) để chứng minh luồng cascade lỗi trong cửa sổ OOM sập pod đầu tiên (`23:42:00Z` - `23:44:30Z`):

```
[23:42:02.139] [cart-service ] | INFO  | Application starting up version=2.4.1
[23:42:02.746] [cart-service ] | FATAL | Container OOMKilled: memory limit exceeded  <-- (1) Cart pod 1 bị OOM sập lập tức
[23:42:03.271] [order-service] | WARN  | Cart service timeout after 2782ms           <-- (2) Upstream (Order) bị timeout kết nối
[23:42:03.299] [cart-service ] | INFO  | Application starting up version=2.4.1
[23:42:03.416] [cart-service ] | ERROR | OutOfMemoryError imminent: available heap < 5%
[23:42:08.655] [cart-service ] | ERROR | Upstream connection refused host=product-service
[23:42:11.437] [cart-service ] | FATAL | Container OOMKilled: memory limit exceeded  <-- (3) Pod khởi động lại bị OOM tiếp
[23:42:16.000] [cart-service ] | FATAL | Container OOMKilled: memory limit exceeded
[23:42:31.496] [order-service] | ERROR | Cart service returned 5xx status=500        <-- (4) Gateway nhận lỗi 500 từ Order
[23:42:33.705] [cart-service ] | FATAL | Container OOMKilled: memory limit exceeded
```

**Mô tả tiến trình cascade:**
1. **Giai đoạn 1 (Memory Leak & Latency Degradation)**: Lúc **16:28:30**, JVM GC của Cart Service bị quá tải, gây trễ. Đến **16:49:30**, latency của `order-service` bị kéo tăng đột biến do phải đợi `cart-service`.
2. **Giai đoạn 2 (Crash & Client Timeout)**: Lúc **19:59:02**, bộ nhớ RSS của Cart Service vượt quá giới hạn 2GB của K8s, container bị `OOMKilled`. Ngay lập tức, `order-service` phát sinh hàng loạt lỗi `connection timeout`.
3. **Giai đoạn 3 (Restart Loop & Gateway 5xx)**: Pod Cart Service khởi động lại, thực hiện cache warm-up kết hợp với tải người dùng dồn dập (thundering herd) khiến RSS tăng vọt và tiếp tục bị `OOMKilled` trước khi kịp ready. API Gateway ghi nhận tỷ lệ lỗi upstream tăng vọt lên 34%.

![Cascade Domino Sequence](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/plot/cascade_domino_sequence.png)

### Biểu đồ thống kê số lượng Logs (Log volume spikes) của Cart và Order Services:

![Cart Service Log Spikes](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/plot/logs_cart-service.png)

![Order Service Log Spikes](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/plot/logs_order-service.png)

---

## 4. WHAT — Cơ chế lỗi & Giải pháp khắc phục triệt để

### Cơ chế lỗi (Feedback Loop & Thundering Herd)
1. **Lỗi logic cache eviction**: Khi áp lực heap tăng cao, thay vì giải phóng cache tích cực hơn, `ProductCatalogCache` lại bỏ qua eviction do kiểm tra thấy `heap pressure too high`. Điều này tạo ra một vòng lặp tự hủy hoại (Vicious Cycle): Heap cao $\rightarrow$ Không eviction cache $\rightarrow$ Heap tiếp tục tăng trong lần nạp sau.
2. **JVM Heap vs RSS Limit**: K8s container limit là 2GB. Vì JVM Heap tối đa (`-Xmx`) không được cấu hình chặt chẽ để chừa khoảng trống cho off-heap và stack memory, nên RSS thực tế của container vượt 2GB và bị kubelet kết liễu.
3. **Restart Loop**: Khi khởi động lại, tiến trình nạp cache (warm-up) chạy song song với traffic dồn từ các pod đã chết gây tràn bộ nhớ RSS lập tức, khiến container chết trước khi kịp chuyển sang trạng thái `Ready`.

### Xu hướng xuất hiện lỗi cache eviction so với cảnh báo GC trên Cart Service:

![Cart Service Hourly Eviction Failures vs GC Warnings](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/plot/hourly_log_warnings.png)

### Telemetry Fusion: GC Pause Metrics tương quan chéo với GC Warning Logs

![Telemetry Fusion: Metric JVM GC Pauses vs Log GC Overhead warnings](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/plot/telemetry_fusion_gc.png)

### Giải pháp khắc phục đề xuất
1. **Cấu hình lại JVM Heap**: Set `-Xmx1400m` để đảm bảo heap luôn nằm trong ngưỡng an toàn, chừa 600MB cho off-heap, JVM overhead và thread stacks của container 2GB.
2. **Tối ưu hóa Eviction Logic**: Thay đổi logic cache eviction, bắt buộc thực hiện dọn dẹp cache quyết liệt hơn khi heap pressure tăng cao thay vì bỏ qua.
3. **Warm-up throttling**: Thực hiện tải nạp cache theo lô (chunking) và giới hạn request rate trong giai đoạn khởi chạy. Chỉ cho phép định tuyến traffic sau khi Readiness probe trả về Success.
4. **Sửa cấu hình OpenTelemetry**: Cấu hình đúng W3C tracecontext header propagation trên các HTTP clients của `order-service` để khôi phục tính năng distributed tracing chéo dịch vụ.
