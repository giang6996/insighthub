# 1. Promptfoo final scan có HIGH không? Mỗi HIGH ban đầu fix thế nào?
Không có HIGH hoặc CRITICAL ở cả initial và final scan. Initial đạt 37/51, final đạt 45/51. Các vấn đề chính là PII/privacy boundary và prompt extraction, được harden bằng runtime guardrails, untrusted RAG context, PII protection và output redaction.

# 2. 6 lớp Defense in Depth — cover được mấy lớp?
InsightHub cover đủ 6 lớp ở mức lab: input guard, RAG/context trust boundary, runtime guardrail, output guard, authorization/tool permission và LiteLLM gateway/governance.

# 3. Threat model — 6 threats nào? Mitigation mỗi cái?
6 threat chính là direct prompt injection, indirect prompt injection, RAG poisoning, PII leakage, excessive agency và prompt extraction. Mitigation tương ứng gồm input/runtime guardrail, untrusted context, RAG poisoning test, PII/output protection, permission tiers/read-only MCP và prompt-extraction refusal.

# 4. LiteLLM gateway có bao nhiêu virtual keys? Tổng budget cap?
Có 3 virtual keys: insighthub $0.50, chatops $0.25 và coding $0.50. Tổng configured budget là $1.25. Budget không được coi là hard cap tuyệt đối khi có concurrency.

# 5. Cost dashboard hiển thị gì? Cost/hour hiện tại?
Dashboard hiển thị spend, token usage, request count, workload/model, cost per success, budget denial và latency khi có dữ liệu. Tổng observed spend trong lab là $0.01077662. Project chưa có workload ổn định đủ lâu để đưa ra cost/hour đáng tin cậy.

# 6. Bedrock Guardrails hoặc NeMo — enable filter nào? Why?
Project không dùng Bedrock Guardrails hoặc NeMo. InsightHub dùng application-level runtime guardrails cho prompt extraction, excessive agency, PII, secret-like output và untrusted RAG context vì application hiểu rõ trust boundary hơn gateway đơn thuần.

# 7. Indirect injection từ poisoned document — discovered thế nào? Fix layer nào ngăn được?
Test đi qua toàn bộ flow: poisoned document → upload → ARQ ingestion → embedding → pgvector → retrieval → LLM. Sau hardening, supplemental test đạt 5/5 intended facts và 0 malicious-instruction influence. Defense chính là RAG/context trust boundary + runtime guardrail.

# 8. Anthropic prompt caching — tiết kiệm bao nhiêu % cho system prompt?
Project không dùng Anthropic prompt caching. Về lý thuyết, cache hit có giá khoảng 0.1× normal input price, tức phần cached input có thể tiết kiệm khoảng 90%. Đây không phải 90% của toàn bộ request vì new input và output vẫn được tính riêng.

# 9. Model routing — bao nhiêu % request dùng từng model? Quality, latency và cost có đạt mục tiêu không?
Project chưa triển khai multi-model routing. Chat hiện dùng một model chính nên tỷ lệ chat là 100% model đó; embedding dùng text-embedding-3-small. Quality được kiểm tra bằng Promptfoo và benign regression, latency được monitor, cost được theo dõi bằng LiteLLM/Grafana. Chưa có A/B benchmark nên không claim routing optimization target.