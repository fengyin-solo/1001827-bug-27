"""内窥检测业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import StoreError, store

MODULE = "cctv"
REVIEW_MODULE = "cctv_review"
REQUIRED_FIELDS = ["检测编号", "检测管段", "检测设备"]
FILTER_FIELDS = ["检测编号", "检测管段", "检测设备"]
STATUS_ORDER = ["待检测", "检测中", "已出具", "已退回"]
ACTION_RULES = {"安排检测": "检测中", "确认出具": "已出具", "退回重检": "已退回"}
NEGATIVE_ACTIONS = []
EXPORT_EXCLUDED_STATUSES = {"已退回"}
REVIEW_KEY = "检测管段"


class CctvService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        filters: dict[str, str | None] | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._apply_filters(store.rows(MODULE), keyword=keyword, status=status, filters=filters)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def export_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        filters: dict[str, str | None] | None = None,
    ) -> list[dict[str, Any]]:
        """导出口径：与列表同一套筛选，再剔除退回重检的报告，保证条数对得上。"""
        rows = self._apply_filters(store.rows(MODULE), keyword=keyword, status=status, filters=filters)
        return [row for row in rows if row.get("status") not in EXPORT_EXCLUDED_STATUSES]

    def _apply_filters(
        self,
        rows: list[dict[str, Any]],
        *,
        keyword: str | None,
        status: str | None,
        filters: dict[str, str | None] | None,
    ) -> list[dict[str, Any]]:
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("检测编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        for field, value in (filters or {}).items():
            if field in FILTER_FIELDS and value:
                rows = [row for row in rows if str(value) in str(row.get(field, ""))]
        return rows

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测报告 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于内窥检测可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"检测报告已{action}"

    def list_review(self) -> list[dict[str, Any]]:
        """复核清单：只读查看，没有整改结论时就是空清单。"""
        return list(store.view(REVIEW_MODULE))

    def submit_conclusion(self, entry_id: int, conclusion: str) -> tuple[dict[str, Any] | None, str]:
        """整改结论落到复核清单：同一检测管段后到那一份覆盖；落库失败保留原值。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测报告 {entry_id} 不存在或已归档"
        conclusion = conclusion.strip()
        if not conclusion:
            return None, "整改结论不能为空，请补充后再提交"
        record = {
            "检测编号": entry.get("检测编号"),
            "检测管段": entry.get("检测管段"),
            "整改结论": conclusion,
            "提交时间": date.today().isoformat(),
        }
        try:
            saved = store.upsert(REVIEW_MODULE, key=REVIEW_KEY, value=record.get(REVIEW_KEY), entry=record)
        except StoreError as exc:
            return None, f"整改结论落库失败（{exc}），原复核记录保持原值，可重试"
        return saved, "整改结论已写入复核清单"
