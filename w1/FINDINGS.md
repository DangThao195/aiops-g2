# INCIDENT POSTMORTEM: CASCADING FAILURE TRIGGERED BY CART-SERVICE OUT-OF-MEMORY

| Thuộc tính | Thông tin chi tiết |
| :--- | :--- |
| **Ngày xảy ra sự cố** | 2026-06-01 |
| **Dịch vụ chịu ảnh hưởng** | `cart-service`, `api-gateway`, `order-service`, `payment-service` |
| **Mức độ nghiêm trọng** | CRITICAL (Sập diện rộng luồng nghiệp vụ Core) |
| **Trạng thái xử lý** | Đã định vị nguyên nhân gốc rễ (Root Cause Identified) |

---

## 1. WHEN — Dòng thời gian diễn biến sự cố (Timeline)

Sự cố bùng phát theo chuỗi phản ứng dây chuyền (Domino Effect) từ tầng hạ tầng tài nguyên ứng dụng lên luồng trải nghiệm người dùng, kéo dài từ chiều đến đêm muộn ngày 01/06/2026:

* **03:08:00 UTC:** `product-service` ghi nhận cảnh báo bất thường đa biến độc lập. Hệ thống tự phục hồi, không lan truyền sang các service khác (Nhóm đối chứng cô lập).
* **17:46:30 UTC:** **[THỜI ĐIỂM KÍCH HOẠT SỰ CỐ GỐC]** `cart-service` nổ cảnh báo đa biến phối hợp đầu tiên giữa RAM, Latency và nhịp Pause của JVM.
* **20:19:30 UTC:** Sự cố bắt đầu lan sang tầng biên của hệ thống. `api-gateway` nổ cảnh báo do tỷ lệ lỗi kết nối ngược dòng (`cart_upstream_error_rate`) tăng vọt.
* **20:39:30 UTC:** Lỗi tràn sang dịch vụ phụ thuộc cốt lõi. `order-service` mất khả năng giao tiếp với Giỏ hàng, dính timeout diện rộng và gãy luồng đặt hàng.
* **20:48:00 UTC:** Điểm cuối luồng nghiệp vụ bị chặn đứng. `payment-service` sụt giảm tải lượng và biến động Latency nghiêm trọng do không có request thanh toán hợp lệ đổ về từ tầng Order.

---

## 2. WHERE — Định vị cấu trúc khu vực ảnh hưởng

Sự cố bắt nguồn cục bộ tại cụm Pod của một dịch vụ đơn lẻ, sau đó quét qua trục giao tiếp Microservices theo mô hình thác nước (Waterfall):

```text
[Bệnh nhân số 0: cart-service] 
       │ (Treo cứng RAM/GC lúc 17:46)
       ▼
[api-gateway] (Báo lỗi 5xx kết nối ngược dòng lúc 20:19)
       │
       ▼
[order-service] (Nghẽn hàng đợi kết nối, dính Timeout lúc 20:39)
       │
       ▼
[payment-service] (Mất traffic, biến động chỉ số lúc 20:48)
```

> **Ghi chú:** `product-service` hoàn toàn im lặng trong suốt chuỗi thảm họa ban đêm, chứng tỏ lỗi cô lập hoàn toàn trong call-chain liên quan đến Giỏ hàng (`Cart`).

---

## 3. WHAT — Bằng chứng chi tiết (Evidence từ Metrics & Logs)

### 3.1. Phân tích nguyên nhân gốc rễ tại `cart-service`
Isolation Forest đa biến đã khoanh vùng hẹp cửa sổ lỗi trong khoảng từ **17:41:30** đến **17:51:30**. Drain3 tiến hành trích xuất 111 dòng log lỗi cấu trúc và bóc tách thành 3 mẫu template mang tính nhân quả:

#### Cụm số #2 (Nguyên nhân cốt lõi - Xuất hiện: 40 lần)
* **Mẫu cấu trúc Drain3:** `ProductCatalogCache eviction failed: heap pressure too high`
* **Phân tích kỹ thuật:** Ứng dụng duy trì bộ đệm `ProductCatalogCache` nằm trong bộ nhớ RAM. Khi lượng dữ liệu phình to vượt ngưỡng, cơ chế dọn dẹp giải phóng phần tử cũ khỏi cache (`eviction failed`) bị tê liệt hoàn toàn do áp lực bộ nhớ Heap của máy ảo Java tăng quá cao (`heap pressure too high`). Đây là dấu hiệu kinh điển của **Memory Leak (Rò rỉ bộ nhớ ngầm)**.

#### Cụm số #1 (Hệ quả hạ tầng JVM - Xuất hiện: 31 lần)
* **Mẫu cấu trúc Drain3:** `GC overhead limit warning: pause=<*> heap=<*>`
* **Log thực tế đại diện:** `GC overhead limit warning: pause=703ms heap=90%`
* **Phân tích kỹ thuật:** Do RAM bị chiếm giữ đến **90%** mà không thể giải phóng từ Cache, bộ dọn rác tự động của Java (Garbage Collection) phải kích hoạt liên tục. Hiện tượng "Stop the World" xảy ra khiến toàn bộ ứng dụng bị đóng băng ứng cứu lên tới **703ms** mỗi chu kỳ, tiêu tốn hơn 98% thời gian chạy của CPU chỉ để dọn rác vô ích.

#### Cụm số #3 (Tác động dịch vụ - Xuất hiện: 29 lần)
* **Mẫu cấu trúc Drain3:** `Slow response detected endpoint=/api/cart <*>`
* **Log thực tế đại diện:** `Slow response detected endpoint=/api/cart latency=1141ms`
* **Phân tích kỹ thuật:** Khi JVM bị đóng băng luân phiên do GC, các request của khách hàng đổ vào giỏ hàng `/api/cart` bị kéo giãn thời gian phản hồi, trễ trung bình vượt qua ngưỡng **1141ms đến 1837ms**, tạo vết dầu loang làm nghẽn cổ chai luồng vào.

---

### 3.2. Hiệu ứng sụp đổ dây chuyền tại `order-service`
Khi `cart-service` mất hoàn toàn khả năng phản hồi nhanh, tác động lan sang `order-service` tại khung thời gian cô lập của Drain3 từ **20:34:30** đến **20:44:30**:

#### Cụm số #1 (Xuất hiện: 61 lần)
* **Mẫu cấu trúc Drain3:** `Cart service <*> <*> <*>`
* **Log thực tế đại diện:** `Cart service timeout after 2374ms`
* **Phân tích kỹ thuật:** Để xử lý một đơn đặt hàng, `order-service` bắt buộc phải gọi HTTP/gRPC sang `cart-service`. Do phía Giỏ hàng đã bị treo cứng, luồng xử lý của Order bị giam lại cho đến khi cạn kiệt thời gian chờ cấu hình mạng (`timeout after 2374ms`). Hiện tượng này lặp lại liên tiếp **61 lần** trong 10 phút, chiếm dụng sạch sẽ tài nguyên Connection Pool của hệ thống Đặt hàng và trả về mã lỗi `502/503` cho khách hàng.

---

## 4. ĐỀ XUẤT BIỆN PHÁP KHẮC PHỤC (RECOMMENDATIONS)

* **Sửa lỗi Code (Hotfix ứng dụng):** Kiểm tra và cấu hình lại thư viện cache sử dụng trong `ProductCatalogCache`. Bắt buộc phải đặt giới hạn kích thước cứng (Max Size) và cấu hình chính sách giải phóng bộ nhớ tự động (ví dụ: *Least Recently Used - LRU*), nghiêm cấm việc để cache phình to vô hạn theo tải lượng.
* **Cấu hình Hạ tầng (Chống sụp đổ dây chuyền):**
    * Triển khai cơ chế **Circuit Breaker (Ngắt mạch tự động)** tại `api-gateway` và `order-service` khi gọi sang `cart-service`. Nếu tỷ lệ timeout vượt quá 10%, ngắt mạch ngay lập tức và trả về fallback page để bảo vệ tài nguyên luồng Đặt hàng.
    * Tối ưu hóa tham số cấu hình JVM: Bổ sung cờ kích hoạt tự động dump bộ nhớ khi tràn RAM (`-XX:+HeapDumpOnOutOfMemoryError`) để lấy dữ liệu phân tích sâu, đồng thời chuyển đổi sang bộ dọn rác thế hệ mới **G1GC** hoặc **ZGC** để giảm thời gian ứng dụng bị đóng băng (*GC pause time*).