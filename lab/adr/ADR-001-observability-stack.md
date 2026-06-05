# ADR-001: Chọn Observability Stack Cho AIOps

## Trạng thái

Đề xuất

## Bối cảnh

ShopX chạy nhiều microservice trên Kubernetes. Để phát hiện và triage incident theo hướng AIOps, chỉ dùng một loại alert hoặc một nguồn dữ liệu là chưa đủ.

Pipeline cần thu thập nhiều loại telemetry:

- Metrics của service và Kubernetes.
- Logs của ứng dụng.
- Kubernetes events như OOMKilled, CrashLoopBackOff, pod restart.
- Distributed traces để hiểu quan hệ gọi nhau giữa các service.

Dataset của bài lab hiện chỉ có metrics và logs. Tuy nhiên, trong kiến trúc production, Kubernetes events và traces là cần thiết để xác nhận OOM/restart và chứng minh quan hệ upstream/downstream.

## Quyết định

Chọn một observability stack cố định cho bản cost-optimized:

| Loại telemetry | Công cụ | Vai trò |
|---|---|---|
| Metrics | Prometheus | Thu thập metrics của service và Kubernetes |
| Logs | Promtail + Loki | Thu thập, lưu và query application logs |
| Traces | OpenTelemetry Collector + Tempo | Thu thập distributed traces |
| Kubernetes events | Kubernetes Event Exporter + kube-state-metrics | Thu thập OOMKilled, restart, CrashLoopBackOff |
| Incident store | Postgres | Lưu incident candidates và evidence timeline |
| Dashboard/alert | Grafana + Alertmanager + Slack webhook | Hiển thị telemetry và gửi alert |

## Lý do

Prometheus được chọn vì đây là chuẩn phổ biến trong Kubernetes metrics. Prometheus tích hợp tốt với Grafana, Alertmanager, kube-state-metrics và hỗ trợ PromQL để tính các tín hiệu như error rate, latency, restart delta, memory pressure.

Loki được chọn thay vì Elasticsearch để tối ưu chi phí. Use case chính là query logs theo service, pod và time range, sau đó đưa logs vào Drain3 log template mining. Với kiểu truy vấn này, Loki nhẹ hơn và tích hợp trực tiếp với Grafana.

Tempo được chọn thay vì Jaeger để đồng bộ với Grafana stack và tối ưu chi phí vận hành. OpenTelemetry cần thiết vì metrics và logs không phải lúc nào cũng chứng minh được quan hệ nhân quả giữa các service. Trong incident hiện tại, `product-service` có anomaly sớm, nhưng thiếu trace nên chưa thể kết luận chắc chắn product gây lỗi cart.

Kubernetes Event Exporter cần thiết vì OOMKilled, CrashLoopBackOff và pod restart là evidence trực tiếp từ platform.

Postgres được chọn làm incident store vì đơn giản, rẻ, dễ query, đủ cho MVP. Không dùng Kafka/Redpanda ở bản đầu vì pipeline chạy theo batch window bằng Kubernetes CronJob; streaming chỉ cần khi yêu cầu realtime/scale tăng.

## Hệ quả

Ưu điểm:

- Stack phù hợp với Kubernetes-native observability.
- Cost thấp hơn Elastic/Kafka-based architecture.
- Traces giúp triage theo dependency graph.
- Kubernetes events cung cấp bằng chứng trực tiếp cho incident OOM/restart.

Đánh đổi:

- Nhiều component hơn so với chỉ dùng Prometheus alerts.
- Logs và traces cần retention policy để kiểm soát chi phí.
- Trace instrumentation có thể cần chỉnh code hoặc dùng service mesh.
- Batch CronJob không realtime bằng streaming Kafka, nhưng đủ cho MVP và rẻ hơn.

## Tối Ưu Chi Phí

Stack được chọn cho MVP:

```text
Prometheus + Promtail + Loki + OpenTelemetry Collector + Tempo
+ Kubernetes Event Exporter + Postgres + Grafana + Alertmanager
```

Không triển khai ở giai đoạn đầu:

```text
Kafka/Redpanda
Elasticsearch
Thanos/Mimir
```

Các công cụ này chỉ cân nhắc khi có nhu cầu scale/retention/search lớn hơn.

Retention đề xuất:

| Dữ liệu | Hot retention | Long-term option |
|---|---:|---|
| Metrics raw 30s | 7-15 ngày | Downsample 5m/1h |
| Logs | 7 ngày | Archive sang object storage |
| Traces | 1-3 ngày | Giữ slow/error traces lâu hơn |
| Incident signals | 30-90 ngày | Lưu Postgres/object storage |
