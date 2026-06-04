# SUBMIT - Group 2 Reflection

## Reflection

Bài lab này cho thấy thời điểm alert xuất hiện chưa chắc là thời điểm incident thật sự bắt đầu. Alert cuối ngày cho thấy `cart-service` có 5xx cao và restart nhiều, nhưng khi phân tích telemetry theo timeline, hệ thống đã có dấu hiệu bất thường sớm hơn nhiều. Bài học quan trọng nhất là phải tách biệt giữa root failure và symptom propagation. `api-gateway`, `order-service`, và `payment-service` đều trở nên noisy về sau, nhưng các anomaly của chúng xuất hiện sau khi `cart-service` đã có memory pressure, OOMKilled và restart loop.

Hướng phân tích được triển khai theo thứ tự metrics trước, logs sau. Metrics giúp định lượng mốc thời gian, so sánh service nào bất thường trước, và khoanh vùng blast radius vào `cart-service`. Sau đó, Drain3 được dùng để phân tích log template nhằm giải thích WHAT/root cause. Log cho thấy các pattern như `ProductCatalogCache eviction failed`, GC warning, heap pressure và OOMKilled. Những pattern này giúp giải thích vì sao các metric như GC pause, memory usage, latency và restart count tăng lên.

Phần khó nhất là đánh giá vai trò của `product-service`. Service này có anomaly rất sớm từ khoảng `03:03Z`, và log của cart lại nhắc tới `ProductCatalogCache`, nên product-service có thể là trigger liên quan tới cache behavior. Tuy nhiên, vì dataset không có product logs hoặc distributed traces để chứng minh liên kết trực tiếp, product-service chưa đủ cơ sở để được kết luận là root cause. Kết luận hợp lý hơn là: product-service là early suspicious signal / possible trigger, còn root failure đã chứng minh được là `cart-service` memory pressure dẫn tới OOM và restart loop.

## Contributions

- Member 1: Kiểm tra chất lượng dữ liệu, timestamp gap và thống kê tổng quan metrics.
- Member 2: Xây dựng Rolling Z-score và sustained threshold analysis.
- Member 3: Xây dựng Isolation Forest cho anomaly detection đa biến trên `cart-service`.
- Member 4: Parse logs bằng Drain3 và phân tích template spike theo thời gian.
- Member 5: Điều tra `product-service` anomaly và giả thuyết possible trigger.
- Member 6: Dựng cross-signal timeline và phân tích blast radius.
- Member 7: Viết `FINDINGS.md`, `SUBMIT.md`, kiểm tra reproduction và review kết quả cuối.
