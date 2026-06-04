# SUBMIT: AIOps Lab W1 - Group 2

## Group Reflection
Bài Lab tuần này đã mang lại cho nhóm một bài học cực kỳ sâu sắc về giá trị của AIOps và tư duy giám sát hệ thống phân tán. 
Lúc đầu, khi nhìn vào cảnh báo lúc 23:04, chúng tôi rất dễ bị bối rối bởi "cơn bão cảnh báo" (Alert Storm) đến từ cả 4 services cùng một lúc. Tuy nhiên, bằng cách áp dụng tuần tự các phương pháp EDA, phân tích đa độ đo (multi-metric correlation) và Machine Learning (Isolation Forest, Z-score), chúng tôi đã thành công trong việc lọc nhiễu, tìm ra service gốc rễ (`cart-service`). 
Đặc biệt, việc kết hợp (Fusion) dòng thời gian của Metrics với các Log Templates được trích xuất từ thuật toán Drain3 đã tạo ra bằng chứng không thể chối cãi. Chúng tôi hiểu ra rằng, sự cố hiếm khi đột ngột xảy ra mà thường có một "Silent Period" kéo dài nhiều giờ trước đó (như vụ rò rỉ RAM âm ỉ). Nếu có một hệ thống AIOps tự động phát hiện được tín hiệu chìm này, on-call engineer đã có thể ngăn chặn thảm họa từ trước khi nó ảnh hưởng tới khách hàng.

## Contribution
- **Thành viên 1:** Thiết lập môi trường, viết script EDA (Heatmap, Side-by-side timeline).
- **Thành viên 2:** Nghiên cứu và code thuật toán Z-score, Isolation Forest để lập bảng First Alert.
- **Thành viên 3:** Code script Log Clustering bằng Drain3, trích xuất mốc thời gian lỗi.
- **Thành viên 4:** Thực hiện Log + Metric Fusion, chắp nối các sự kiện và viết Postmortem (FINDINGS.md).
- **Thành viên 5 (Bạn):** Đưa ra định hướng chiến lược (Multi-service/Multi-metric), nâng cấp kịch bản phá án lên chuẩn SRE Senior và hoàn thiện báo cáo cuối.
