# Day 7 — Self Evaluation

## 1. Tổng cộng em nộp được bao nhiêu artifact?

em đã hoàn thành và nộp đủ **7/7 artifact** của running project InsightHub.

## 2. Artifact nào em tự đánh giá Level 4 (Excellence)?

em tự đánh giá các artifact sau ở mức Level 4:

- **Day 1 — Async Ingestion:** Redis + ARQ, worker riêng, lifecycle `pending → ready/failed`, retry và idempotency.
- **Day 2 — MCP Integration:** tích hợp và kiểm thử thực tế Filesystem, Docker, Kubernetes và Prometheus MCP với giới hạn quyền phù hợp.
- **Day 3 — Infrastructure & CI/CD:** Terraform, AWS/EKS và GitHub Actions CI/CD đã được triển khai và kiểm chứng thực tế.
- **Day 5 — ChatOps:** Slack Events, Redis/ARQ worker, MCP integration, audit log và mô hình phân quyền 3 cấp được triển khai và kiểm thử end-to-end.

Đây là các phần em cảm thấy mình hiểu rõ nhất cả về kiến trúc, cách triển khai và cách kiểm chứng kết quả.

## 3. Artifact nào em tự đánh giá dưới Level 3?

em tự đánh giá **Day 4, Day 6 và Day 7** dưới Level 3 ở thời điểm hiện tại.

Không phải vì các phần này chưa hoàn thành, mà vì chúng chứa nhiều kiến thức mới so với nền tảng Web Development hiện tại của em.

- **Day 4:** Prometheus, Grafana, alerting, anomaly detection và RCA cần thêm thời gian thực hành để hiểu sâu cách thiết kế observability thực tế.
- **Day 6:** AI security, Promptfoo, LiteLLM, guardrails và FinOps là những chủ đề khá mới và cần thêm nhiều tình huống thực tế để sử dụng tự tin.
- **Day 7:** em đã có thể tổng hợp và trình bày toàn bộ project, nhưng vẫn cần thêm thời gian để củng cố những kiến thức mới từ các ngày trước thành kỹ năng thực tế ổn định.

## 4. Pillar nào em học nhiều nhất?

- [x] **A. Develop with AI**
- [x] **B. Operate with AI**

Hai pillar này sát nhất với những gì em đã thực hành trong project: sử dụng coding agent để phát triển hệ thống, sau đó triển khai, quan sát, debug và vận hành hệ thống bằng các công cụ DevOps.

## 5. Tool nào em sẽ tiếp tục sử dụng sau khoá?

Các tool và kỹ thuật em muốn tiếp tục sử dụng gồm:

- **Codex** cho coding workflow và hỗ trợ điều tra/debug.
- **MCP** để kết nối agent với các tool và hệ thống bên ngoài theo phạm vi quyền rõ ràng.
- **Prometheus + Grafana** cho monitoring và observability.
- **Docker / Docker Compose** cho môi trường local.
- **Redis + ARQ** cho background job và asynchronous processing.
- **GitHub Actions** cho CI/CD.
- Các thành phần kiến trúc cốt lõi đã thực hành trong InsightHub khi phù hợp với project sau này.

## 6. Câu hỏi em muốn hỏi trainer Day 7

> Nếu tiếp tục học trong khoảng 1–2 tháng sau khoá, với nền tảng hiện tại là Web Development và DevOps ở mức junior, trainer khuyên nên ưu tiên đào sâu phần nào trước để biến những kiến thức đã học trong InsightHub thành kỹ năng có thể áp dụng tốt trong project thực tế?

## 7. Roadmap em muốn đi tiếp

Roadmap ưu tiên của em là:

- [x] **Autonomous Coding Agents (Devin, Replit Agent)**

Ngoài ra, em cũng đặc biệt quan tâm tới:

- **A2A Protocol & Multi-Agent Systems**

Em muốn tìm hiểu sâu hơn cách coding agent có thể làm việc độc lập hơn, sau đó mở rộng sang cách nhiều agent/tool phối hợp với nhau trong một workflow lớn hơn.

## 8. Feedback cho trainer

### 3 điều em thấy giá trị nhất

1. **Kiến thức thực tế và phạm vi rộng:** khoá học không chỉ dừng ở coding mà đi qua deployment, observability, ChatOps, security và FinOps.
2. **Sự hỗ trợ của trainer:** trainer hỗ trợ tốt khi gặp lỗi hoặc khi cần làm rõ những phần khó trong quá trình thực hành.
3. **Running project xuyên suốt:** việc tiếp tục mở rộng cùng một project giúp em thấy rõ một ứng dụng có thể tiến hoá từ code ban đầu thành một hệ thống có nhiều thành phần vận hành thực tế.

### 1 điều em muốn thay đổi

Em muốn có **nhiều thời gian hơn cho từng nhóm kiến thức mới**, đặc biệt là observability, AI security và FinOps. Với người xuất phát chủ yếu từ Web Development, lượng kiến thức mới trong một số ngày khá lớn và cần thêm thời gian thực hành để hiểu sâu thay vì chỉ hoàn thành task.

### Suggest cho khoá sau

Có thể dành thêm một khoảng thời gian nhỏ sau mỗi nhóm chủ đề để học viên:

- ôn lại kiến thức chính,
- tự thực hành thêm một use case đơn giản,
- và giải thích lại kiến trúc hoặc quyết định kỹ thuật của mình trước khi chuyển sang chủ đề tiếp theo.
