from typing import Any, Optional

from fastapi.responses import JSONResponse


def success_response(data: Any = None, message: str = "success") -> dict:
    return {"code": 200, "message": message, "data": data}


def error_response(code: int, message: str, detail: Any = None) -> JSONResponse:
    resp = {"code": code, "message": message}
    if detail:
        resp["detail"] = detail
    return JSONResponse(status_code=code, content=resp)


def paginated_response(items: list, total: int, page: int, size: int) -> dict:
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
        },
    }
