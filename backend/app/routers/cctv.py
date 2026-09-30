"""内窥检测接口：维护检测报告，覆盖安排检测、确认出具、退回重检等动作。"""
from __future__ import annotations

import csv
import io
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.cctv import CctvService

router = APIRouter(prefix="/api/cctv", tags=["内窥检测"])

service = CctvService()

LIST_FIELDS = ["检测编号", "检测管段", "检测设备", "检测长度", "缺陷等级", "检测人员", "检测日期", "检测状态"]
STATUSES = ["待检测", "检测中", "已出具", "已退回"]


def _collect_filters(
    filter_code: str | None,
    filter_segment: str | None,
    filter_device: str | None,
) -> dict[str, str | None]:
    """把查询串里的字段条件收拢成服务层认识的筛选口径。"""
    return {"检测编号": filter_code, "检测管段": filter_segment, "检测设备": filter_device}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按检测编号检索"),
    status: str | None = Query(default=None, description="待检测、检测中、已出具、已退回"),
    filter_code: str | None = Query(default=None, alias="检测编号"),
    filter_segment: str | None = Query(default=None, alias="检测管段"),
    filter_device: str | None = Query(default=None, alias="检测设备"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按检测编号与状态过滤内窥检测列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    filters = _collect_filters(filter_code, filter_segment, filter_device)
    items, total = service.list_entries(keyword=keyword, status=status, filters=filters, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 注意：/export、/review 必须注册在 /{entry_id} 之前，否则会被当成 entry_id 匹配掉。
@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按检测编号检索"),
    status: str | None = Query(default=None, description="待检测、检测中、已出具、已退回"),
    filter_code: str | None = Query(default=None, alias="检测编号"),
    filter_segment: str | None = Query(default=None, alias="检测管段"),
    filter_device: str | None = Query(default=None, alias="检测设备"),
) -> Response:
    """导出内窥检测清单：与列表同一口径、剔除退回重检，列与条数都跟列表当前范围对齐。"""
    filters = _collect_filters(filter_code, filter_segment, filter_device)
    rows = service.export_entries(keyword=keyword, status=status, filters=filters)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(LIST_FIELDS)
    for row in rows:
        writer.writerow(["" if row.get(field) is None else row.get(field) for field in LIST_FIELDS])
    # 带 BOM 的 UTF-8，Excel 直接打开中文不乱码。
    content = "\ufeff" + buffer.getvalue()
    filename = quote("内窥检测清单.csv")
    headers = {
        "Content-Disposition": f"attachment; filename=\"cctv_export.csv\"; filename*=UTF-8''{filename}"
    }
    return Response(content=content, media_type="text/csv; charset=utf-8", headers=headers)


@router.get("/review", response_model=PageResult[dict])
def list_review() -> PageResult[dict]:
    """复核清单：整改结论按检测管段归集，同一管段后到那一份覆盖旧结论。"""
    items = service.list_review()
    return PageResult(items=items, total=len(items))


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条检测报告明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"检测报告 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条检测报告，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="检测报告已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条检测报告执行安排检测、确认出具、退回重检；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/conclusion", response_model=ActionResult)
def submit_conclusion(entry_id: int, payload: EntryPayload) -> ActionResult:
    """提交整改结论：落到复核清单；落库失败时保留原值，并提示可以再试一次。"""
    conclusion = str(payload.values.get("整改结论") or "")
    record, message = service.submit_conclusion(entry_id, conclusion)
    if record is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=record)
