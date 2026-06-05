# ADR-002: Pipeline Phát Hiện Và Triage Incident Theo Hướng AIOps

## Trạng thái

Đề xuất

## Bối cảnh

Alert truyền thống thường phát hiện từng triệu chứng riêng lẻ, ví dụ 5xx cao, latency cao hoặc restart count tăng. Incident trong bài lab cho thấy tín hiệu hữu ích xuất hiện sớm hơn alert cuối:

- `product-service` có anomaly từ khoảng `03:04Z`.
- `cart-service` có log cache eviction failure từ `06:32Z`.
- Log cache/GC/slow response spike từ `14:00Z`.
- Memory/GC/latency của cart degrade trước khi OOM.
- OOMKilled và restart loop xuất hiện gần `20:00Z`.
- `api-gateway`, `order-service`, `payment-service` bị ảnh hưởng sau đó.

Do đó, pipeline AIOps cần tự động detect và correlate nhiều loại signal thay vì yêu cầu con người đọc notebook thủ công.

## Quyết định

Xây dựng pipeline AIOps cost-optimized theo batch window bằng Kubernetes CronJob:

```text
Prometheus/Loki/Tempo/Kubernetes events
→ Python AIOps CronJob
→ detector registry + Drain3 + event detector + trace correlation
→ correlation engine
→ incident scoring
→ Postgres incident store
→ Grafana/Alertmanager/Slack/report
```

Pipeline tạo ra incident candidate với:

- service chính bị nghi ngờ
- thời điểm bắt đầu
- severity
- confidence
- evidence timeline
- suspected root failure
- possible upstream trigger
- downstream impact

## Thành Phần Detector

| Component | Tool | Input | Phương pháp |
|---|---|---|---|
| Metric anomaly detector | Python CronJob query Prometheus HTTP API | Prometheus metrics | Detector registry: Baseline IQR, EWMA, Rolling IQR, counter delta, optional Isolation Forest |
| Log pattern miner | Python CronJob query Loki API + Drain3 | Loki logs | Drain3 template mining và spike detection |
| Kubernetes event detector | Python CronJob query Kubernetes Event Exporter/kube-state-metrics | Kubernetes events | OOMKilled, restart, CrashLoopBackOff |
| Trace anomaly detector | Python CronJob query Tempo API | Tempo traces | Slow spans, error spans, dependency path failures |
| Incident store | Postgres | Correlated signals | Lưu incident candidate, score, evidence timeline |
| Alert output | Alertmanager + Slack webhook | Incident candidate | Gửi alert/report |

## Metric Detector Registry

Không chạy tất cả detector trên mọi metric. Mỗi nhóm metric dùng detector phù hợp với hành vi của nó:

| Nhóm metric | Ví dụ | Detector |
|---|---|---|
| Resource | `cpu_usage_percent`, `memory_pct`, `jvm_gc_pause_ms_avg` | Baseline IQR, EWMA |
| Availability | `http_5xx_rate`, `upstream_timeout_rate` | Baseline IQR, Rolling IQR |
| Latency | `http_p99_latency_ms` | Baseline IQR, EWMA, Rolling IQR |
| Traffic | `http_requests_per_sec`, `active_connections` | Rolling IQR |
| Counter | `container_restart_count` | Counter delta |

Fixed threshold không dùng làm detector chính vì dễ bị xem là chọn ngưỡng theo incident. Threshold chỉ dùng làm operational severity rule để xác nhận mức độ nghiêm trọng.

Isolation Forest được giữ như detector bổ trợ đa biến ở cấp feature group, không phải detector chính duy nhất.

## Correlation Logic

Python AIOps CronJob chạy mỗi 5 phút. Mỗi lần chạy chỉ query window mới nhất, ví dụ:

```text
current window: last 5 minutes
baseline window: last 6 hours
log spike window: last 30 minutes
```

Signals được gom theo:

- service
- time window
- pod/deployment
- dependency graph
- severity

Dependency graph giúp phân biệt root failure và downstream symptom.

Ví dụ:

```text
cart-service OOM/restart xảy ra trước
api-gateway cart upstream error xảy ra sau
order/payment timeout xảy ra sau nữa
```

Kết luận:

```text
cart-service = primary failure
api-gateway/order/payment = downstream impact
```

## Incident Scoring

Ví dụ scoring:

| Signal | Score |
|---|---:|
| OOMKilled | +50 |
| Restart loop | +40 |
| Memory pressure/drift | +25 |
| GC pause anomaly | +20 |
| Cache eviction log spike | +25 |
| 5xx rate anomaly | +20 |
| Downstream timeout | +15 |
| Trace dependency error | +20 |

Ngưỡng:

```text
score >= 80  => incident candidate
score >= 120 => critical incident
```

## Root Cause Hypothesis Rule

Với incident class memory/cache pressure:

```text
IF cache eviction spike
AND memory pressure/drift
AND GC pause anomaly
AND OOMKilled
AND restart increase
THEN suspected root failure = cache-related memory pressure
```

Output kỳ vọng:

```json
{
  "incident_id": "INC-20260601-cart-memory-pressure",
  "severity": "critical",
  "primary_service": "cart-service",
  "suspected_root_failure": "ProductCatalogCache memory pressure and eviction failure",
  "possible_upstream_trigger": "product-service degradation",
  "downstream_impact": [
    "api-gateway",
    "order-service",
    "payment-service"
  ]
}
```

## Hệ quả

Ưu điểm:

- Detect incident sớm hơn alert cuối.
- Giảm alert noise bằng cách gom signals liên quan thành incident candidate.
- Tự động sinh evidence timeline.
- Hỗ trợ root cause hypothesis thay vì chỉ báo alert rời rạc.
- Phân biệt primary failure và downstream impact.
- Không cần Kafka/Redpanda ở giai đoạn đầu nên giảm chi phí và độ phức tạp.

Đánh đổi:

- Cần tuning detector.
- Cần dependency graph đủ chính xác.
- Rule-based RCA dễ giải thích nhưng có thể bỏ sót failure mode mới.
- Batch CronJob có latency theo chu kỳ chạy, ví dụ 5 phút. Nếu cần near-realtime ở quy mô lớn, có thể nâng cấp sau sang streaming.
