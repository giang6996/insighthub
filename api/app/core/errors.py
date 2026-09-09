"""Public errors contain fixed messages, never provider bodies or credentials."""


class ServiceError(Exception):
    status_code = 500
    code = "internal_error"
    message = "Không thể xử lý yêu cầu."

    def __init__(self):
        super().__init__(self.message)


class ProviderError(ServiceError):
    status_code = 502
    code = "provider_error"
    message = "Dịch vụ AI không khả dụng hoặc trả dữ liệu không hợp lệ."


class InvalidDocument(ServiceError):
    status_code = 422
    code = "invalid_document"
    message = "Tài liệu trống, không hợp lệ hoặc không có nội dung văn bản."


class DocumentNotFound(ServiceError):
    status_code = 404
    code = "document_not_found"
    message = "Không tìm thấy tài liệu."


class DocumentConflict(ServiceError):
    status_code = 409
    code = "document_conflict"
    message = "Document ID đã gắn với nội dung hoặc cấu hình xử lý khác."


class IndexIdentityConflict(ServiceError):
    status_code = 409
    code = "index_identity_conflict"
    message = (
        "Embedding identity không khớp index. Cần rebuild index bằng cấu hình đã chọn."
    )


class SchemaMismatch(ServiceError):
    status_code = 503
    code = "schema_mismatch"
    message = "Schema chưa sẵn sàng hoặc dimension không khớp EMBEDDING_DIM."


class QueueUnavailable(ServiceError):
    status_code = 503
    code = "queue_unavailable"
    message = "Hàng đợi xử lý chưa sẵn sàng. Vui lòng thử lại sau."


class RetryNotAllowed(ServiceError):
    status_code = 409
    code = "retry_not_allowed"
    message = "Chỉ có thể retry khi tài liệu đang ở trạng thái failed."


class StagedPayloadMissing(ServiceError):
    status_code = 409
    code = "staged_payload_missing"
    message = "Không tìm thấy payload đã stage để retry tài liệu này."
