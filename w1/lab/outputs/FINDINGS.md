## WHEN
- **Phát hiện bất thường (Số liệu):** Chỉ báo sớm nhất từ ​​số liệu (được phát hiện bởi mô hình Isolation Forest về mức sử dụng CPU và bộ nhớ) xảy ra lúc **2026-06-01 01:20:00 UTC**. Điều này cho thấy một sự sai lệch nhỏ so với các mô hình bình thường vài giờ trước khi sự cố xảy ra.

- **Tín hiệu nhật ký:** Cảnh báo lỗi rõ ràng đầu tiên trong nhật ký xảy ra lúc **2026-06-01 19:59:00 UTC**, với thông báo: `OutOfMemoryError imminent: available heap < 5%`.

- **Cảnh báo được kích hoạt:** Các cảnh báo hệ thống cuối cùng đã được kích hoạt lúc **23:04 UTC** sau khi vượt quá ngưỡng số lần khởi động lại pod và ngưỡng tỷ lệ HTTP 5xx.

## WHERE
- **Dịch vụ:** `cart-service`
- **Số liệu:** `memory_usage_bytes` và `jvm_gc_pause_ms_avg` (cho thấy áp lực bộ nhớ tăng lên), cùng với `http_5xx_rate` tăng lên.

- **Mẫu nhật ký:** Các chỉ báo chính là nhật ký `ERROR` cho `OutOfMemoryError imminent: available heap < 5%` tiếp theo là nhật ký `FATAL` cho `Container OOMKilled: memory limit exceeded`. Có 819 sự cố FATAL cho thấy lỗi hệ thống.

## WHAT
**Giả thuyết nguyên nhân gốc:**
Một lỗi rò rỉ bộ nhớ nghiêm trọng trong `cart-service` đã khiến mức sử dụng bộ nhớ của container liên tục tiến gần đến giới hạn bộ nhớ của Kubernetes (2 GB). Khi heap JVM đầy, thời gian tạm dừng thu gom rác tăng lên, cuối cùng dẫn đến `OutOfMemoryError`. Khi bộ nhớ vượt quá giới hạn của cgroup, Kubernetes đã khởi tạo sự kiện `Container OOMKilled`.

**Cơ chế của vòng lặp khởi động lại:**
Vì sự cố rò rỉ bộ nhớ tiềm ẩn không được giải quyết, mỗi khi Kubernetes khởi động lại pod, bộ nhớ sẽ lại bị rò rỉ cho đến khi đạt đến giới hạn OOMKilled. Điều này khiến pod bị sập liên tục, dẫn đến vòng lặp khởi động lại. Trong thời gian xảy ra sự cố và khởi động lại, dịch vụ không thể xử lý các yêu cầu đến, dẫn đến sự gia tăng đột biến của `http_5xx_rate` (34%) và lỗi hết thời gian chờ ở các dịch vụ phụ thuộc như `order-service` và `payment-service`. Kỹ sư khởi động lại pod đã cung cấp một thiết lập lại tạm thời, nhưng sự cố rò rỉ có thể sẽ tái diễn trừ khi mã ứng dụng được vá lỗi.