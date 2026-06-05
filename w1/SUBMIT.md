# BÁO CÁO TỔNG KẾT VÀ ĐÓNG GÓP THÀNH VIÊN 

## 1. Group Reflection 

Qua quá trình nghiên cứu và triển khai thực tế hệ thống giám sát anomaly detection cho kiến trúc Microservices, nhóm đã rút ra được nhiều bài học kinh nghiệm sâu sắc về cả mặt lý thuyết lẫn kỹ thuật vận hành SRE (Site Reliability Engineering). 

Thách thức lớn nhất ban đầu của nhóm là giải quyết bài toán "Alert Fatigue" (Nhiễu cảnh báo). Khi sử dụng các thuật toán đơn biến độc lập (IQR, Z-Score, Bollinger Bands, Isolation Forest 1D) tại thời điểm rạng sáng, hệ thống liên tục nổ ra các cảnh báo thô (Spikes) do xung nhiễu mạng hoặc tiến trình dọn rác định kỳ của JVM, trong khi bản chất hệ thống vẫn tự phục hồi ổn định. Bài học bước ngoặt xuất hiện khi nhóm quyết định cải tiến sang tư duy **Đa biến (Multivariate Isolation Forest)**. Sự kết hợp này giúp hệ thống loại bỏ hoàn toàn các báo động giả lắt nhắt, chỉ chốt hạ cảnh báo thực tế khi các chỉ số tài nguyên (RAM, GC Pause) và chỉ số hiệu năng (p99 Latency) bắt đầu cộng hưởng, suy sụp đồng loạt (Crisis Point lúc 17:46:30).

Bên cạnh đó, việc tích hợp tầng xử lý ngôn ngữ tự nhiên thông minh (TF-IDF + K-Means hoặc Drain3) để quét hẹp dữ liệu log `.jsonl` trong phạm vi $\pm$5 phút quanh mốc trigger point đã giúp nhóm tối ưu hóa triệt để quy trình Root Cause Analysis (RCA). Thay vì phải trace qua hàng triệu dòng log của cả ngày một cách mù mờ, thuật toán phân cụm văn bản đã ngay lập tức bóc tách và phơi bày chính xác "bệnh nhân số 0" (Lỗi Memory Leak tại bộ đệm `ProductCatalogCache`), từ đó chứng minh rõ ràng hiệu ứng Domino lan truyền sang `api-gateway` và `order-service` (Timeout diện rộng). Dự án này không chỉ nâng cao tư duy phân tích dữ liệu chuỗi thời gian của nhóm mà còn mở ra góc nhìn thực chiến sắc bén trong việc thiết kế các hệ thống tự động cảnh báo tự phục hồi (Auto-scaling & Circuit Breaker) trên môi trường Production hiện đại.

---

## 2. Member Contributions

## 2. Member Contributions (Bảng đóng góp thành viên)

Dưới đây là chi tiết phân chia công việc và tỷ lệ đóng góp của từng thành viên trong dự án xây dựng Pipeline giám sát đa biến và phân tích chuỗi sự cố hệ thống:

| STT | Thành viên | Vai trò chính | Chi tiết đóng góp cụ thể (Contribution Statement) | Tỷ lệ |
| :---: | :--- | :--- | :--- | :---: |
| 1 | **Trần Quốc Kiệt** | Pipeline Architect | Khảo sát cấu trúc hệ thống, chịu trách nhiệm thiết kế và vẽ sơ đồ Pipeline tự động hóa toàn bộ quy trình từ thu thập metrics/logs đến kích hoạt cảnh báo. | 11.1% |
| 2 | **Phạm Vũ Khánh Trường** | Pipeline Engineer | Hiện thực hóa sơ đồ kiến trúc, biên soạn tài liệu kỹ thuật chi tiết (`.md`) hướng dẫn cài đặt, cấu hình và vận hành Pipeline tự động hóa. | 11.1% |
| 3 | **Nguyễn Đức Hảo** | ML Engineer | Nghiên cứu sâu toán học và cài đặt lõi thuật toán **Multivariate Isolation Forest**; thực hiện Feature Engineering sinh các đặc trưng động để phát hiện điểm bất thường đa biến. | 11.1% |
| 4 | **Đặng Thị Ngọc Thảo** | Log Analytics Specialist | Chịu trách nhiệm xử lý cấu trúc file log `.jsonl`, tích hợp và cấu hình bộ phân tách mẫu cấu trúc cây **Drain3** và TF-IDF để bóc tách log lỗi xung quanh cửa sổ sự cố. | 11.1% |
| 5 | **Bùi Lê Anh Tuấn** | Technical Consultant | Nghiên cứu lý thuyết, chủ trì các buổi phản biện và bàn luận chuyên sâu nhằm so sánh, lựa chọn phương pháp tối ưu nhất (giữa đơn biến và đa biến, Drain3 và TF-IDF). | 11.1% |
| 6 | **Ngô Thanh Kiên** | Technical Consultant | Phối hợp nghiên cứu các mô hình lọc nhiễu, tham gia bàn luận phản biện để tối ưu hóa tham số thuật toán và đề xuất phương án xử lý sự cố tốt nhất cho hệ thống. | 11.1% |
| 7 | **Nguyễn Tiến Hoàng Thịnh** | Technical Writer | Tổng hợp toàn bộ minh chứng từ số liệu mô hình (Metrics) và cấu trúc mẫu log, chịu trách nhiệm chính biên soạn báo cáo phân tích sự cố chuyên sâu **`FINDINGS.md`**. | 11.1% |
| 8 | **Lê Hải Khoa** | Technical Writer | Đúc kết quá trình nghiên cứu, tổng hợp phần Group Reflection và biên soạn hoàn chỉnh tài liệu tổng kết đóng góp **`SUBMIT.md`** cho nhóm. | 11.1% |
| 9 | **Nguyễn Phan Anh Bảo** | Presentation Designer | Tổng hợp toàn bộ mã nguồn, biểu đồ trực quan và kết quả phân tích sự cố để thiết kế slide báo cáo chuyên nghiệp, phục vụ công tác thuyết trình dự án. | 11.1% |

---


