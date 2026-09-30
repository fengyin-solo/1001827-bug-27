"""内窥检测接口：维护检测报告，覆盖安排检测、确认出具、退回重检等动作。"""
from __future__ import annotations

import csv
import io
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.cctv import CctvService

router = APIRouter(prefix="/api/cctv", tags=["内窥检测"])

service = CctvService()

LIST_FIELDS = ["检测编号", "检测管段", "检测设备", "检测长度", "缺陷等级", "检测人员", "检测日期", "检测状态"]
STATUSES = ["待检测", "检测中", "已出具", "已退回"]


def _collect_filters(
    code: str | None,
    segment: str | None,
    device: str | None,
) -> dict[str, str]:
    """把筛选框带过来的字段条件收拢成服务层认识的字典，空值直接丢掉。"""
    filters = {"检测编号": code, "检测管段": segment, "检测设备": device}
    return {field: str(value).strip() for field, value in filters.items() if value and str(value).strip()}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按检测编号检索"),
    status: str | None = Query(default=None, description="待检测、检测中、已出具、已退回"),
    code: str | None = Query(default=None, alias="检测编号"),
    segment: str | None = Query(default=None, alias="检测管段"),
    device: str | None = Query(default=None, alias="检测设备"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按检测编号与状态过滤内窥检测列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    filters = _collect_filters(code, segment, device)
    items, total = service.list_entries(keyword=keyword, status=status, filters=filters, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 注意：/export、/review 必须写在 /{entry_id} 前面，
# 否则 "export" 会被当成 entry_id 解析，直接 422。
@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    code: str | None = Query(default=None, alias="检测编号"),
    segment: str | None = Query(default=None, alias="检测管段"),
    device: str | None = Query(default=None, alias="检测设备"),
) -> Response:
    """导出内窥检测清单：与列表同一筛选口径、退回重检不进入范围，直接给可另存的 CSV。"""
    filters = _collect_filters(code, segment, device)
    rows = service.export_entries(keyword=keyword, status=status, filters=filters)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(LIST_FIELDS)
    for row in rows:
        writer.writerow([row.get(field) or "" for field in LIST_FIELDS])
    # 带 BOM 的 UTF-8，Excel 直接打开中文不乱码
    content = buffer.getvalue().encode("utf-8-sig")
    filename = quote("内窥检测清单.csv")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Total-Count": str(len(rows)),
        },
    )


@router.get("/review", response_model=dict)
def review_entries() -> dict[str, Any]:
    """复核清单：退回重检的报告连同整改结论一起列出来。"""
    items = service.list_review()
    return {"module": "cctv", "total": len(items), "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条检测报告明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"检测报告 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条检测报告；同一检测编号只留后到的那一份，缺字段时说明原因而不是静默丢弃。"""
    entry, missing, outcome = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    if entry is None:
        return ActionResult(ok=False, message=outcome or "检测报告登记失败")
    if outcome == "updated":
        return ActionResult(ok=True, message="同编号检测报告已以后到的一份覆盖", entry=entry)
    return ActionResult(ok=True, message="检测报告已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条检测报告执行安排检测、确认出具、退回重检；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
