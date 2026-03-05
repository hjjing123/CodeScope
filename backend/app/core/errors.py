from __future__ import annotations


class AppError(Exception):
    code: str
    status_code: int
    message: str
    detail: dict[str, object]

    def __init__(
        self,
        *,
        code: str,
        status_code: int,
        message: str,
        detail: dict[str, object] | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


def unauthorized_error(message: str = "认证失败", code: str = "UNAUTHORIZED") -> AppError:
    return AppError(code=code, status_code=401, message=message)


def forbidden_error(message: str = "无权限访问", code: str = "FORBIDDEN") -> AppError:
    return AppError(code=code, status_code=403, message=message)
