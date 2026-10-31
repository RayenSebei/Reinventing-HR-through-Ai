"""Typed API errors. SENTINEL asserts on `code`, never on message text."""
from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str = "", **extra):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code.replace("_", " ").capitalize()
        self.extra = extra

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, **self.extra}}


def unauthenticated():
    return ApiError(401, "UNAUTHENTICATED", "Log in first.")


def forbidden(code: str = "FORBIDDEN", message: str = "You don't have access to this."):
    return ApiError(403, code, message)


def not_found(what: str = "Resource"):
    # Used for both "doesn't exist" and "exists but not yours", so IDs can't be probed.
    return ApiError(404, "NOT_FOUND", f"{what} not found.")


def invalid(message: str, **extra):
    return ApiError(422, "SCHEMA_INVALID", message, **extra)


def conflict(code: str, message: str):
    return ApiError(409, code, message)
