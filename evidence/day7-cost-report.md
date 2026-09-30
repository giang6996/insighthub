# Day 7 — Cost Report

## 1. Tổng chi phí phải trả

**Total payable cost: $0.00**

Trong suốt quá trình thực hiện InsightHub, tài khoản AWS cá nhân vẫn còn Free Tier / promotional credits, vì vậy các tài nguyên AWS đã sử dụng không tạo ra khoản thanh toán thực tế phải trả.

## 2. AWS usage

AWS chỉ được sử dụng cho **Day 3** để kiểm chứng:

- Terraform infrastructure
- EKS deployment
- RDS PostgreSQL
- ElastiCache Redis
- EFS
- ECR
- Load Balancer
- GitHub Actions CI/CD với AWS OIDC

Sau khi hoàn thành kiểm thử và thu thập evidence, các tài nguyên InsightHub trên AWS đã được teardown để tránh phát sinh chi phí tiếp tục.

Các Day còn lại chủ yếu chạy local bằng Docker Compose, Minikube, Prometheus, Grafana và các service local khác.

## 3. Cost attribution limitation

InsightHub được triển khai trên cùng tài khoản AWS cá nhân đang được sử dụng cho mục đích cá nhân. Tại thời điểm chạy Day 3 chưa cấu hình cost allocation riêng theo project/tag, nên không thể tách chính xác phần credit consumption thuộc riêng InsightHub sau khi chạy.

Vì tài khoản vẫn được AWS credits bao phủ, AWS Billing hiện ghi nhận:

**Payable cost: $0.00**

Do đó báo cáo này ghi nhận chi phí thực tế phải trả là `$0.00`, đồng thời ghi rõ rằng hệ thống vẫn có resource usage nhưng được thanh toán bằng AWS promotional/free credits.

## 4. AI API usage

Có một số lượng nhỏ AI API calls trong quá trình kiểm thử, chủ yếu liên quan tới Day 6 và các thử nghiệm kỹ thuật. Mức sử dụng này nhỏ và không được tách riêng hoàn toàn khỏi các hoạt động phát triển cá nhân khác

## 5. Kết luận

- **AWS payable cost:** `$0.00`
- **AI API payable cost:** không tách riêng đáng tin cậy
- **Total reported cost:** `$0.00`
- **AWS resources after validation:** đã teardown
- **Main reason for $0.00:** usage được bao phủ bởi Free Tier / promotional credits