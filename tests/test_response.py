import json
import pytest
from fastapi.responses import JSONResponse
from app.common.response import success_response, error_response, paginated_response


class TestSuccessResponse:
    def test_return_code_200(self):
        result = success_response()
        assert result["code"] == 200

    def test_default_message(self):
        result = success_response()
        assert result["message"] == "success"

    def test_with_data(self):
        result = success_response(data={"key": "value"})
        assert result["data"]["key"] == "value"

    def test_with_none_data(self):
        result = success_response(data=None)
        assert result["data"] is None

    def test_with_list_data(self):
        result = success_response(data=[1, 2, 3])
        assert result["data"] == [1, 2, 3]

    def test_custom_message(self):
        result = success_response(message="自定义消息")
        assert result["message"] == "自定义消息"

    def test_response_structure(self):
        result = success_response(data={"id": 1})
        assert set(result.keys()) == {"code", "message", "data"}

    def test_nested_data(self):
        result = success_response(data={"user": {"name": "test", "role": "admin"}})
        assert result["data"]["user"]["role"] == "admin"


def _parse(r):
    if isinstance(r, JSONResponse):
        return json.loads(r.body)
    return r


class TestErrorResponse:
    def test_with_code_and_message(self):
        r = error_response(400, "请求错误")
        body = _parse(r)
        assert body["code"] == 400
        assert body["message"] == "请求错误"
        assert r.status_code == 400

    def test_with_detail(self):
        r = error_response(422, "验证失败", detail={"field": "name", "error": "必填"})
        body = _parse(r)
        assert body["detail"]["field"] == "name"
        assert r.status_code == 422

    def test_without_detail(self):
        r = error_response(404, "未找到")
        body = _parse(r)
        assert "detail" not in body
        assert r.status_code == 404

    def test_with_empty_detail_string(self):
        r = error_response(400, "错误", detail="")
        body = _parse(r)
        assert "detail" not in body

    def test_error_structure_with_detail(self):
        r = error_response(403, "无权限", detail="仅管理员可操作")
        body = _parse(r)
        assert set(body.keys()) == {"code", "message", "detail"}
        assert r.status_code == 403

    def test_various_error_codes(self):
        for code in [400, 401, 403, 404, 409, 422, 429, 500, 502, 503]:
            r = error_response(code, f"错误{code}")
            body = _parse(r)
            assert body["code"] == code
            assert r.status_code == code

    def test_detail_as_dict(self):
        r = error_response(422, "验证失败", detail={"errors": ["字段A无效", "字段B无效"]})
        body = _parse(r)
        assert len(body["detail"]["errors"]) == 2
        assert r.status_code == 422


class TestPaginatedResponse:
    def test_basic_pagination(self):
        result = paginated_response([{"id": 1}], 1, 1, 20)
        assert result["code"] == 200
        assert result["data"]["items"] == [{"id": 1}]
        assert result["data"]["total"] == 1
        assert result["data"]["page"] == 1
        assert result["data"]["size"] == 20

    def test_empty_items(self):
        result = paginated_response([], 0, 1, 20)
        assert result["data"]["items"] == []
        assert result["data"]["total"] == 0

    def test_second_page(self):
        items = [{"id": i} for i in range(21, 31)]
        result = paginated_response(items, 50, 2, 10)
        assert result["data"]["page"] == 2
        assert result["data"]["size"] == 10
        assert len(result["data"]["items"]) == 10
        assert result["data"]["items"][0]["id"] == 21

    def test_last_page_partial(self):
        items = [{"id": i} for i in range(46, 50)]
        result = paginated_response(items, 49, 5, 10)
        assert len(result["data"]["items"]) == 4
        assert result["data"]["total"] == 49

    def test_response_structure(self):
        result = paginated_response([], 0, 1, 20)
        assert list(result["data"].keys()) == ["items", "total", "page", "size"]

    def test_large_page_size(self):
        items = [{"id": i} for i in range(100)]
        result = paginated_response(items, 100, 1, 100)
        assert len(result["data"]["items"]) == 100
        assert result["data"]["size"] == 100

    def test_string_items(self):
        result = paginated_response(["a", "b", "c"], 3, 1, 10)
        assert result["data"]["items"] == ["a", "b", "c"]

    def test_message_field(self):
        result = paginated_response([], 0, 1, 10)
        assert result["message"] == "success"

    def test_page_and_size_types(self):
        result = paginated_response([], 0, 1, 20)
        assert isinstance(result["data"]["page"], int)
        assert isinstance(result["data"]["size"], int)
        assert isinstance(result["data"]["total"], int)
