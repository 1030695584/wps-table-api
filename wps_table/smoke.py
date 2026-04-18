"""WPS 多维表格接口全链路 Smoke 测试

执行顺序（每步独立计数，失败不中断后续步骤，最后汇总结果）：

    1.  get_schema
    2.  get_sheets / get_sheet_info
    3.  create_sheet           （创建临时 sheet，后续在其上操作）
    4.  create_field           （追加一列，便于校验字段接口）
    5.  get_fields / get_views
    6.  update_sheet           （改名）
    7.  create_record (单条)
    8.  batch_create_records
    9.  list_records
    10. get_records            （按页）
    11. search_records
    12. get_record
    13. update_record
    14. batch_update_records
    15. create_view / update_view / delete_view
    16. update_field
    17. delete_record / batch_delete_records
    18. delete_field
    19. delete_sheet           （清理）

用法：
    python -m wps_table.smoke
"""
from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from loguru import logger

from .api import WPS365DBSheetAPI, WPSAPIError
from .config import load_settings


TEMP_SHEET_PREFIX = "smoke_tmp_"


class SmokeResult:
    def __init__(self) -> None:
        self.records: List[Tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.records.append((name, ok, detail))
        icon = "PASS" if ok else "FAIL"
        logger.info(f"[{icon}] {name} {('- ' + detail) if detail else ''}")

    def summary(self) -> None:
        total = len(self.records)
        passed = sum(1 for _, ok, _ in self.records if ok)
        logger.info("=" * 60)
        logger.info(f"Smoke 结果: {passed}/{total} 通过")
        for name, ok, detail in self.records:
            icon = "PASS" if ok else "FAIL"
            logger.info(f"  [{icon}] {name} {('- ' + detail) if detail and not ok else ''}")


def _step(result: SmokeResult, name: str, fn: Callable[[], Any]) -> Any:
    try:
        value = fn()
        result.add(name, True)
        return value
    except WPSAPIError as exc:
        result.add(name, False, f"{exc} | status={exc.status_code} | payload={exc.payload}")
    except Exception as exc:  # noqa: BLE001
        result.add(name, False, f"{type(exc).__name__}: {exc}")
        logger.debug(traceback.format_exc())
    return None


def run_smoke(base_dir: str) -> None:
    settings = load_settings(base_dir)
    client_id = settings["client_id"]
    client_secret = settings["client_secret"]
    file_id = settings["file_id"]

    if not (client_id and client_secret and file_id):
        logger.error("缺少 WPS_CLIENT_ID / WPS_CLIENT_SECRET / WPS_FILE_ID 环境变量")
        return

    api = WPS365DBSheetAPI(client_id=client_id, client_secret=client_secret)
    result = SmokeResult()

    # 1. 获取 schema
    schema = _step(result, "get_schema", lambda: api.get_schema(file_id))

    # 2. sheets / sheet_info
    _step(result, "get_sheets", lambda: api.get_sheets(file_id))
    if schema:
        first_sheet = schema.get("data", {}).get("sheets", [{}])[0]
        first_sheet_id = str(first_sheet.get("id", ""))
        if first_sheet_id:
            _step(
                result,
                "get_sheet_info",
                lambda: api.get_sheet_info(file_id, sheet_id=first_sheet_id),
            )

    # 3. 创建临时 sheet
    tmp_sheet_name = f"{TEMP_SHEET_PREFIX}{int(time.time())}"
    created_sheet = _step(
        result,
        "create_sheet",
        lambda: api.create_sheet(
            file_id,
            tmp_sheet_name,
            fields=[
                {"name": "标题", "type": "MultiLineText"},
                {"name": "数量", "type": "Number"},
            ],
        ),
    )

    tmp_sheet_id: str = ""
    if created_sheet:
        data = created_sheet.get("data", {})
        tmp_sheet_id = str(data.get("id") or data.get("sheet", {}).get("id") or "")
        if not tmp_sheet_id:
            tmp_sheet_id = api.get_sheet_id_by_name(file_id, tmp_sheet_name) or ""

    if not tmp_sheet_id:
        logger.error("临时工作表未建出，后续步骤跳过")
        result.summary()
        return

    logger.info(f"临时 sheet_id = {tmp_sheet_id}")

    # 4. 新增字段
    created_field = _step(
        result,
        "create_field",
        lambda: api.create_field(file_id, tmp_sheet_id, field_name="备注", field_type="MultiLineText"),
    )

    # 5. fields / views
    fields_after = _step(result, "get_fields", lambda: api.get_fields(file_id, sheet_id=tmp_sheet_id))
    _step(result, "get_views", lambda: api.get_views(file_id, sheet_id=tmp_sheet_id))

    remark_field_id = ""
    title_field_id = ""
    if isinstance(fields_after, list):
        for field in fields_after:
            if field.get("name") == "备注":
                remark_field_id = str(field.get("id", ""))
            if field.get("name") == "标题":
                title_field_id = str(field.get("id", ""))

    # 6. 更新 sheet
    _step(
        result,
        "update_sheet",
        lambda: api.update_sheet(file_id, tmp_sheet_id, name=tmp_sheet_name + "_renamed"),
    )

    # 7. 创建单条记录
    created_record = _step(
        result,
        "create_record",
        lambda: api.create_record(
            file_id,
            sheet_id=tmp_sheet_id,
            fields={"标题": "hello", "数量": 1},
        ),
    )

    single_record_id = ""
    if created_record:
        records = created_record.get("data", {}).get("records") or []
        if records:
            single_record_id = str(records[0].get("id", ""))

    # 8. 批量创建
    batch_created = _step(
        result,
        "batch_create_records",
        lambda: api.batch_create_records(
            file_id,
            sheet_id=tmp_sheet_id,
            records=[
                {"fields_value": {"标题": "a", "数量": 10}},
                {"fields_value": {"标题": "b", "数量": 20}},
            ],
        ),
    )
    batch_record_ids: List[str] = []
    if batch_created:
        for rec in batch_created.get("data", {}).get("records") or []:
            rid = rec.get("id")
            if rid:
                batch_record_ids.append(str(rid))

    # 9 / 10 / 11 / 12 读取类
    _step(result, "list_records", lambda: api.list_records(file_id, sheet_id=tmp_sheet_id))
    _step(
        result,
        "get_records(page)",
        lambda: api.get_records(file_id, sheet_id=tmp_sheet_id, page_size=50, page_num=1),
    )
    probe_ids = [rid for rid in [single_record_id, *batch_record_ids] if rid]
    if probe_ids:
        _step(
            result,
            "search_records",
            lambda: api.search_records(file_id, sheet_id=tmp_sheet_id, record_ids=probe_ids),
        )
    if single_record_id:
        _step(
            result,
            "get_record",
            lambda: api.get_record(file_id, tmp_sheet_id, single_record_id),
        )

    # 13. 更新单条
    if single_record_id:
        _step(
            result,
            "update_record",
            lambda: api.update_record(
                file_id,
                tmp_sheet_id,
                single_record_id,
                fields={"标题": "hello-updated", "数量": 99},
            ),
        )

    # 14. 批量更新
    if batch_record_ids:
        _step(
            result,
            "batch_update_records",
            lambda: api.batch_update_records(
                file_id,
                tmp_sheet_id,
                records=[
                    {"id": rid, "fields_value": {"数量": idx * 100}}
                    for idx, rid in enumerate(batch_record_ids, start=1)
                ],
            ),
        )

    # 15. 视图
    created_view = _step(
        result,
        "create_view",
        lambda: api.create_view(file_id, tmp_sheet_id, view_name="tmp_view", view_type="Grid"),
    )
    tmp_view_id = ""
    if created_view:
        data = created_view.get("data", {})
        tmp_view_id = str(data.get("id") or data.get("view", {}).get("id") or "")
    if tmp_view_id:
        _step(
            result,
            "update_view",
            lambda: api.update_view(file_id, tmp_sheet_id, tmp_view_id, name="tmp_view_renamed"),
        )
        _step(
            result,
            "delete_view",
            lambda: api.delete_view(file_id, tmp_sheet_id, tmp_view_id),
        )

    # 16. 更新字段
    if remark_field_id:
        _step(
            result,
            "update_field",
            lambda: api.update_field(file_id, tmp_sheet_id, remark_field_id, name="备注2"),
        )

    # 17. 删除记录
    if single_record_id:
        _step(
            result,
            "delete_record",
            lambda: api.delete_record(file_id, tmp_sheet_id, single_record_id),
        )
    if batch_record_ids:
        _step(
            result,
            "batch_delete_records",
            lambda: api.batch_delete_records(file_id, tmp_sheet_id, batch_record_ids),
        )

    # 18. 删除字段
    if remark_field_id:
        _step(
            result,
            "delete_field",
            lambda: api.delete_field(file_id, tmp_sheet_id, remark_field_id),
        )

    # 19. 删除工作表（清理）
    _step(
        result,
        "delete_sheet",
        lambda: api.delete_sheet(file_id, tmp_sheet_id),
    )

    result.summary()


if __name__ == "__main__":
    run_smoke(str(Path(__file__).resolve().parents[1]))
