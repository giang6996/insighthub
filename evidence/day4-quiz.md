# Day 4 — Self-Check Answers
## AIOps

1. ServiceMonitor scrape mấy service? 30s interval đủ chưa?

Trong thiết kế Day 4, có ba ServiceMonitor chính dùng để scrape API, Redis exporter và PostgreSQL exporter. Web không dùng ServiceMonitor trực tiếp mà được kiểm tra qua Probe với blackbox exporter, còn ingestion-worker được quan sát thông qua các metric về trạng thái và tài nguyên của Kubernetes. Như vậy hệ thống vẫn bao phủ đủ năm logical components cần theo dõi.
Khoảng scrape 30 giây là phù hợp với InsightHub trong phạm vi bài lab vì hệ thống không yêu cầu phát hiện thay đổi ở mức vài giây. Nếu cần phản ứng nhanh hơn thì có thể giảm xuống 15 giây, nhưng điều đó cũng làm tăng số lượng sample, tải cho Prometheus và dung lượng lưu trữ.

2. Anomaly band 3×stddev — false positive rate trong 1h?

Ngưỡng mean + 3 × standard deviation là một cách đặt ngưỡng thống kê tương đối bảo thủ. Nếu dữ liệu gần với phân phối chuẩn thì xác suất một sample vượt phía trên ngưỡng 3σ chỉ khoảng 0.135%.
Tuy nhiên metric thực tế như latency, queue depth hay error rate không phải lúc nào cũng phân phối chuẩn hoặc độc lập với nhau. Vì vậy InsightHub không chỉ dựa vào 3σ mà còn dùng baseline rolling 1 giờ, for: 3m, cùng các operational guard như queue depth >= 2 và HTTP error rate >= 1% để giảm cảnh báo giả do spike ngắn.

3. 3 incident — cái nào dễ phát hiện nhất? Vì sao?

Incident dễ phát hiện nhất là Incident 3 — HTTP error-rate burst. Khi Redis bị dừng, các request POST /documents bắt đầu trả về 503 queue_unavailable, nên tỷ lệ lỗi HTTP tăng lên rất rõ ràng.
So với LLM latency hoặc queue backlog, đây là tín hiệu trực tiếp hơn vì có thể thấy ngay cả từ HTTP status code, Prometheus error-rate metric và trạng thái của document. Vì vậy quá trình phát hiện và xác nhận sự cố đơn giản hơn.

4. RCA report có cite metric + timestamp không? Confidence > 0.7?

Có. Mỗi RCA report đều ghi rõ metric, labels, timestamp và value của sample được dùng làm bằng chứng. Các sample này sau đó còn được query lại trên Prometheus để xác nhận rằng metric và giá trị thực sự tồn tại tại thời điểm được ghi trong incident.
RCA hiện tại không có một field confidence dạng số, nên không nên tự tạo một con số như 0.7 hay 0.9. Tuy nhiên mức độ tin cậy của RCA là cao vì nguyên nhân được đối chiếu với telemetry thật và với chính fault injection đã thực hiện trong từng incident.

5. Correlation > Detection — apply ở incident nào?

Nguyên tắc này thể hiện rõ nhất ở Incident 3 và cũng có thể thấy ở Incident 2.
Ở Incident 3, việc chỉ phát hiện HTTP error rate tăng chưa đủ để biết nguyên nhân. Khi liên kết nhiều tín hiệu với nhau — Redis bị down, enqueue thất bại, API trả 503, document chuyển sang failed, rồi hệ thống phục hồi sau khi Redis được restart — chúng ta mới xác định được nguyên nhân một cách thuyết phục.
Điểm chính là detection cho biết “có vấn đề”, còn correlation giúp trả lời “vấn đề đến từ đâu và các tín hiệu liên quan với nhau như thế nào”.

## MLOps

6. App vs Model artifact khác nhau ở 4 chiều nào?

App artifact và model artifact khác nhau trước hết ở nguồn gốc. App thường được tạo từ source code và quá trình build, trong khi model được tạo từ dữ liệu, thuật toán huấn luyện và các tham số hoặc weights.
Về testing, app thường mang tính deterministic hơn, nghĩa là với cùng input và cùng điều kiện thì kết quả có xu hướng ổn định. Model lại mang tính statistical hoặc probabilistic nhiều hơn, nên chất lượng thường được đánh giá bằng metric thay vì chỉ bằng pass/fail.
Về lifecycle, app có thể gặp bug, dependency issue hoặc configuration drift. Model ngoài các vấn đề runtime còn có thể giảm chất lượng do data drift hoặc concept drift.
Về storage và versioning, app thường version source code, binary và config. Model còn cần quản lý weights, training-data lineage, evaluation metrics và metadata để biết chính xác model nào đã được tạo và deploy.

7. Data drift vs Concept drift khác nhau thế nào?

Data drift xảy ra khi phân phối của input thay đổi theo thời gian. Ví dụ dữ liệu người dùng mới có đặc điểm khác so với dữ liệu mà model từng thấy, nhưng mối quan hệ giữa input và output mục tiêu vẫn tương đối giữ nguyên.
Concept drift xảy ra khi chính mối quan hệ giữa input và output thay đổi. Một input trước đây dẫn đến một kết quả nhất định nhưng về sau có thể không còn đúng nữa do thay đổi hành vi người dùng, môi trường hoặc yếu tố bên ngoài.

8. Nếu team có model riêng và drift fire, DevOps làm gì?

Khi drift alert xuất hiện, DevOps trước hết cần xác nhận alert, thu thập evidence và kiểm tra drift có ảnh hưởng đến runtime hoặc service hay không. Sau đó cần giữ hệ thống ở trạng thái an toàn, ví dụ isolate một deployment có vấn đề, rollback về model version ổn định hoặc chuyển sang một fallback đã được phê duyệt.
DevOps không tự quyết định retrain model. Việc phân tích nguyên nhân drift, quyết định retrain và đánh giá model candidate thuộc trách nhiệm chính của ML Engineer hoặc ML team. DevOps hỗ trợ hạ tầng, pipeline, deployment và rollback để quá trình đó diễn ra an toàn.

9. Khi nào DevOps tự retrain model?

DevOps không nên tự quyết định retrain model. Đây không phải là trách nhiệm chính của DevOps vì retraining yêu cầu hiểu về dữ liệu, model quality, evaluation metric và mục tiêu nghiệp vụ.
DevOps chịu trách nhiệm chính về hạ tầng, pipeline, deployment, monitoring và rollback. ML Engineer chịu trách nhiệm về training, retraining, evaluation và quyết định chất lượng model. DevOps có thể vận hành hoặc tự động hóa retraining pipeline nếu quy trình đó đã được ML team thiết kế và phê duyệt.

10. Ownership boundary table — stage nào DevOps own PRIMARY?

DevOps thường là primary owner ở các phần liên quan đến infrastructure, CI/CD, deployment, release, monitoring, observability, rollback và runtime reliability.
ML Engineer thường là primary owner ở các phần liên quan đến data/model development, training, evaluation và quyết định về model quality.
Một số bước như approval gate, production incident hoặc model promotion cần sự phối hợp giữa hai bên. DevOps đảm bảo model được deploy và vận hành an toàn, còn ML Engineer chịu trách nhiệm xác nhận model có đủ chất lượng để được promote hay không.