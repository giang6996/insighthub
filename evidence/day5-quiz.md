# Day 5 Quiz

##1. Signature verification có reject request > 5 phút không?

Có. Bot kiểm tra `X-Slack-Request-Timestamp` trước khi xử lý request và sẽ từ chối nếu request cũ hơn khoảng 5 phút. Việc này giúp hạn chế việc request cũ bị gửi lại nhiều lần.

## 2. 3 intents - intent nào dùng nhiều tool call nhất?

Trong implementation hiện tại, health intent dùng nhiều call nhất vì nó kiểm tra `/healthz`, `/readyz` và lấy thêm thông tin từ Prometheus MCP. Hai intent còn lại chủ yếu gọi một backend chính để lấy danh sách document hoặc pod.

## 3. Audit log có field nào? Có timestamp + user + tool + result không?

Có. Audit log có các field chính như `event_id`, `action`, `user`, `timestamp` và `decision`. Ngoài ra log còn có thể lưu backend/tool được gọi và kết quả hoặc lỗi của request để dễ kiểm tra lại khi cần.

## 4. Permission tier - write asks confirm thế nào? Token expires sau bao lâu?

Hiện tại bot có ba mức permission chính. Read được phép chạy, write sẽ trả về `approval_required`, còn destructive hoặc unrestricted request sẽ bị `denied`. Phần approval token và thời gian hết hạn chưa được triển khai trong phiên bản hiện tại.

## 5. Bot respond < 3s - tôi dùng BackgroundTasks pattern không?

Không . Bot sử dụng Redis queue và một ARQ worker riêng. FastAPI chỉ nhận request, kiểm tra và đưa job vào queue, sau đó worker mới xử lý các tác vụ lâu hơn nên bot có thể trả ACK nhanh cho Slack.

## 6. Service catalog có những service nào? Owner đầy đủ chưa?

Hiện tại chưa triển khai service catalog vì đây không phải phần bắt buộc của Day 5. Các service chính trong hệ thống gồm web, API, PostgreSQL, Redis, ingestion worker, ChatOps bot, ChatOps worker, Prometheus, Grafana, Alertmanager và các MCP backend. Vì chưa có service catalog chính thức nên owner của từng service cũng chưa được khai báo đầy đủ.

## 7. Vì sao bot cần audit log?

Audit log giúp theo dõi ai đã gửi request, request đó yêu cầu hành động gì, permission được quyết định như thế nào và kết quả hoặc lỗi là gì. Điều này giúp kiểm tra lại hoạt động của bot khi debug hoặc khi xảy ra sự cố.