# Group Submission - Group 2 (AIOps W1 Lab)

## 1. Group Reflection (Phản hồi & Trải nghiệm của Nhóm)

Qua bài lab tuần này về chủ đề **Detect & Triage - Cứu hệ thống đang cháy**, nhóm 2 đã có cơ hội thực chiến sâu sắc với các khái niệm và công cụ quản trị telemetry thực tế của hệ thống microservices chạy trên Kubernetes. Ban đầu, khi nhận được chuỗi cảnh báo dồn dập vào lúc 23:04, chúng tôi đã gặp không ít khó khăn trong việc khoanh vùng nguyên nhân vì các lỗi có xu hướng lan truyền chéo (cascade failures) giữa API Gateway, Order-service, Payment-service và Cart-service. Tuy nhiên, bằng cách tiếp cận khoa học và phân tách vấn đề theo 3 khía cạnh: Thời gian (WHEN), Vị trí (WHERE) và Bản chất sự cố (WHAT), chúng tôi đã nhanh chóng tìm thấy bức tranh toàn cảnh.

Đặc biệt, trong quá trình làm việc, chúng tôi nhận ra rằng việc chỉ tập trung vào một dịch vụ đơn lẻ (`cart-service`) sẽ không phản ánh đúng tư duy hệ thống phân tán của AIOps. Do đó, nhóm đã quyết định mở rộng quy trình phân tích và phát hiện bất thường ra **tất cả 5 tệp dữ liệu CSV đo lường đo lường hiệu năng** của toàn bộ hệ thống (gồm API Gateway, Cart, Order, Payment và Product). Phân tích thống kê chi tiết đã chứng minh 100% các metrics hiệu năng này đều có phân bố **Non-Gaussian** (lệch phải nặng và đuôi nhọn). Phát hiện này đã giúp chúng tôi loại bỏ quy tắc Z-score (3-Sigma) truyền thống vì nó luôn cảnh báo trễ từ 2 đến 5 tiếng, và thay thế bằng thuật toán **Robust IQR** cùng **Isolation Forest** trên các đặc trưng được kỹ nghệ hóa (feature engineering). 

Để minh chứng rõ ràng trực quan cho quá trình phát hiện lỗi này, nhóm đã xây dựng **hơn 15 biểu đồ phân tích chuyên sâu** tích hợp trực tiếp trong tập tin [assignment.ipynb](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/assignment.ipynb) và nhúng trực tiếp vào báo cáo postmortem [FINDINGS.md](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/FINDINGS.md). Bộ biểu đồ này bao gồm Grid biểu đồ Normality (4 ảnh), Grid đối chiếu phát hiện bất thường IQR vs. Z-score trên cả 5 dịch vụ (8 ảnh), Không gian bất thường Isolation Forest (1 ảnh), biểu đồ Telemetry Fusion tích hợp số liệu GC pause và log warning (1 ảnh), cùng biểu đồ bậc thang thể hiện chuỗi domino cascade (1 ảnh).

Bài học lớn nhất của nhóm là việc tương quan chéo dữ liệu chéo dịch vụ (cross-service correlation) giúp phát hiện sớm các "tín hiệu im lặng" (như GC pause bất thường của Cart lúc 16:28:30 gây trễ lan truyền sang Order lúc 16:49:30) từ rất nhiều giờ trước khi hệ thống sập hoàn toàn lúc 19:59. Điều này khẳng định tầm quan trọng của việc giám sát hệ thống dưới góc nhìn hội tụ telemetry (Telemetry Fusion) thay vì các silo giám sát rời rạc.

---

## 2. Member Contributions (Phân chia công việc & Đóng góp)

* **Thành viên 1 (Trưởng nhóm):** Điều phối chung, xây dựng kế hoạch phân tích hệ thống phân tán đa dịch vụ và hoàn thiện báo cáo kỹ thuật [FINDINGS.md](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/FINDINGS.md).
* **Thành viên 2:** Viết mã nguồn tải và làm sạch dữ liệu cho cả 5 file CSV metrics, chạy kiểm định normality (Shapiro-Wilk) trên tất cả các cột dữ liệu.
* **Thành viên 3:** Cài đặt thuật toán Isolation Forest trên các chỉ số tài nguyên của Cart Service, thiết lập các features `gc_per_req` và `mem_growth_rate_30s`.
* **Thành viên 4:** Thực hiện phân tích log JSONL của `cart-service`, trích xuất tần suất các cảnh báo GC Overhead và lỗi eviction.
* **Thành viên 5:** Nghiên cứu log của `order-service`, chỉ ra tác động lan truyền ngược dòng từ lỗi của Cart Service lên Order và Payment.
* **Thành viên 6:** Trực quan hóa toàn bộ 5 metrics CSV và 2 log files trong Notebook [assignment.ipynb](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/assignment.ipynb), đối chiếu thời gian restarts và viết nội dung phản hồi [SUBMIT.md](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase2/W1/D4/SUBMIT.md).
