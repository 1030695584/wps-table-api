import json
import hmac
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests
from loguru import logger


class WPSAPIError(Exception):
    def __init__(self, message: str, *, status_code: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class WPS365DBSheetAPI:
    """WPS 365 多维表格 API 封装"""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.app_id = app_id or client_id
        self.app_secret = app_secret or client_secret
        self.access_token: Optional[str] = None
        self.base_url = "https://openapi.wps.cn"
        self.timeout = 30

    def get_access_token(self) -> str:
        if self.access_token:
            return self.access_token

        try:
            response = requests.post(
                f"{self.base_url}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise WPSAPIError("获取 access_token 请求失败") from exc

        logger.info(f"应用授权获取 token 响应状态: {response.status_code}")
        try:
            result = response.json()
        except ValueError as exc:
            raise WPSAPIError("获取 access_token 响应不是合法 JSON", status_code=response.status_code) from exc
        self.access_token = result.get("access_token")
        if not self.access_token:
            raise WPSAPIError("应用授权获取 access_token 失败", status_code=response.status_code, payload=result)
        return self.access_token

    def _build_url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _generate_kso1_signature(self, method: str, path: str, date_str: str, body: str = "") -> str:
        sha256_hex = hashlib.sha256(body.encode("utf-8")).hexdigest() if body else ""
        sign_string = f"KSO-1{method}{path}application/json{date_str}{sha256_hex}"
        logger.debug(f"签名请求: {method} {path}")
        signature_hex = hmac.new(
            self.app_secret.encode("utf-8"),
            sign_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"KSO-1 {self.app_id}:{signature_hex}"

    def _get_headers(self, method: str = "GET", path: str = "", body: str = "") -> Dict[str, str]:
        if not self.access_token:
            self.get_access_token()

        date_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Kso-Date": date_str,
            "X-Kso-Authorization": self._generate_kso1_signature(method, path, date_str, body),
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        raw_body: str = "",
        extra_headers: Optional[Dict[str, str]] = None,
        files: Optional[Dict[str, Any]] = None,
        use_kso1: bool = True,
    ) -> Dict[str, Any]:
        request_method = method.upper()
        query_string = urlencode(params or {})
        signed_path = f"{path}?{query_string}" if query_string else path
        body = raw_body or (json.dumps(json_data, ensure_ascii=False) if json_data is not None else "")

        headers = self._get_headers(request_method, signed_path, body) if use_kso1 else {
            "Authorization": f"Bearer {self.get_access_token()}"
        }
        if extra_headers:
            headers.update(extra_headers)
        if files:
            headers.pop("Content-Type", None)

        try:
            response = requests.request(
                request_method,
                self._build_url(path),
                headers=headers,
                params=params,
                json=json_data,
                data=raw_body if raw_body else data,
                files=files,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise WPSAPIError(f"请求失败: {request_method} {path}") from exc

        logger.info(f"{request_method} {signed_path} -> {response.status_code}")

        try:
            result = response.json()
        except ValueError:
            result = response.text

        if response.status_code < 200 or response.status_code >= 300:
            raise WPSAPIError(
                f"接口请求失败: {request_method} {path}",
                status_code=response.status_code,
                payload=result,
            )
        return result if isinstance(result, dict) else {"data": result}

    def get_sheet_id_by_name(self, file_id: str, sheet_name: str) -> Optional[str]:
        schema = self.get_schema(file_id)
        if "error" in schema:
            logger.error(f"获取Schema失败: {schema}")
            return None

        sheets = schema.get("data", {}).get("sheets", [])
        for sheet in sheets:
            if sheet.get("name") == sheet_name:
                return str(sheet.get("id"))
        logger.warning(f"未找到名为 '{sheet_name}' 的工作表")
        return None

    def get_schema(self, file_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v7/coop/dbsheet/{file_id}/schema")

    def create_sheet(self, file_id: str, sheet_name: str, fields: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/v7/coop/dbsheet/{file_id}/sheets/create",
            json_data={"name": sheet_name, "fields": fields or []},
        )

    def get_sheets(self, file_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v7/coop/dbsheet/{file_id}/sheets")

    def get_sheet_info(self, file_id: str, sheet_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}")

    def update_sheet(self, file_id: str, sheet_id: str, name: Optional[str] = None, description: Optional[str] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if name:
            data["name"] = name
        if description:
            data["description"] = description
        return self._request("PUT", f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}", json_data=data)

    def delete_sheet(self, file_id: str, sheet_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}")

    def create_field(self, file_id: str, sheet_id: str, field_name: str, field_type: str, field_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/fields",
            json_data={"name": field_name, "type": field_type, "config": field_config or {}},
        )

    def get_fields(self, file_id: str, sheet_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/fields")

    def update_field(self, file_id: str, sheet_id: str, field_id: str, name: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if name:
            data["name"] = name
        if config:
            data["config"] = config
        return self._request("PUT", f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/fields/{field_id}", json_data=data)

    def delete_field(self, file_id: str, sheet_id: str, field_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/fields/{field_id}")

    def create_record(self, file_id: str, sheet_id: Optional[str] = None, sheet_name: Optional[str] = None, fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if sheet_name and not sheet_id:
            sheet_id = self.get_sheet_id_by_name(file_id, sheet_name)
            if not sheet_id:
                return {"error": "sheet_not_found", "message": f"未找到名为 '{sheet_name}' 的工作表"}
        if not sheet_id:
            return {"error": "missing_parameter", "message": "必须提供 sheet_id 或 sheet_name"}
        return self._request(
            "POST",
            f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/records",
            json_data={"fields_value": fields or {}},
        )

    def batch_create_records(self, file_id: str, sheet_id: Optional[str] = None, sheet_name: Optional[str] = None, records: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        if sheet_name and not sheet_id:
            sheet_id = self.get_sheet_id_by_name(file_id, sheet_name)
            if not sheet_id:
                return {"error": "sheet_not_found", "message": f"未找到名为 '{sheet_name}' 的工作表"}
        if not sheet_id:
            return {"error": "missing_parameter", "message": "必须提供 sheet_id 或 sheet_name"}
        return self._request(
            "POST",
            f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/records/batch/create",
            json_data={"records": records or []},
        )

    def get_records(self, file_id: str, sheet_id: Optional[str] = None, sheet_name: Optional[str] = None, view_id: Optional[str] = None, filter_formula: Optional[str] = None, sort: Optional[List[Dict[str, Any]]] = None, page_size: int = 100, page_token: Optional[str] = None) -> Dict[str, Any]:
        if sheet_name and not sheet_id:
            sheet_id = self.get_sheet_id_by_name(file_id, sheet_name)
            if not sheet_id:
                return {"error": "sheet_not_found", "message": f"未找到名为 '{sheet_name}' 的工作表"}
        if not sheet_id:
            return {"error": "missing_parameter", "message": "必须提供 sheet_id 或 sheet_name"}
        params: Dict[str, Any] = {"page_size": page_size}
        if view_id:
            params["view_id"] = view_id
        if filter_formula:
            params["filter"] = filter_formula
        if sort:
            params["sort"] = json.dumps(sort, ensure_ascii=False)
        if page_token:
            params["page_token"] = page_token
        return self._request("GET", f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/records", params=params)

    def get_record(self, file_id: str, sheet_id: str, record_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/records/{record_id}")

    def update_record(self, file_id: str, sheet_id: str, record_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        return self._request(
            "PUT",
            f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/records/{record_id}",
            json_data={"fields": fields},
        )

    def batch_update_records(self, file_id: str, sheet_id: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._request(
            "PUT",
            f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/records/batch/update",
            json_data={"records": records or []},
        )

    def delete_record(self, file_id: str, sheet_id: str, record_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/records/{record_id}")

    def batch_delete_records(self, file_id: str, sheet_id: str, record_ids: List[str]) -> Dict[str, Any]:
        return self._request(
            "DELETE",
            f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/records/batch/delete",
            json_data={"record_ids": record_ids or []},
        )

    def create_view(self, file_id: str, sheet_id: str, view_name: str, view_type: str = "grid", config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/views",
            json_data={"name": view_name, "type": view_type, "config": config or {}},
        )

    def get_views(self, file_id: str, sheet_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/views")

    def update_view(self, file_id: str, sheet_id: str, view_id: str, name: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if name:
            data["name"] = name
        if config:
            data["config"] = config
        return self._request("PUT", f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/views/{view_id}", json_data=data)

    def delete_view(self, file_id: str, sheet_id: str, view_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/views/{view_id}")

    def upload_attachment(self, file_id: str, sheet_id: str, record_id: str, field_id: str, file_path: str) -> Dict[str, Any]:
        with open(file_path, "rb") as file_obj:
            return self._request(
                "POST",
                f"/v7/coop/dbsheet/{file_id}/sheets/{sheet_id}/attachments",
                data={"record_id": record_id, "field_id": field_id},
                files={"file": file_obj},
                use_kso1=False,
            )
