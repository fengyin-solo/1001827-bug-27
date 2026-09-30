"""内窥检测业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import copy
from typing import Any

from app.store import store

MODULE = "cctv"
REQUIRED_FIELDS = ["检测编号", "检测管段", "检测设备"]
LIST_FIELDS = ["检测编号", "检测管段", "检测设备", "检测长度", "缺陷等级", "检测人员", "检测日期", "检测状态"]
STATUS_ORDER = ["待检测", "检测中", "已出具", "已退回"]
ACTION_RULES = {"安排检测": "检测中", "确认出具": "已出具", "退回重检": "已退回"}
NEGATIVE_ACTIONS = []
RETURNED_STATUS = "已退回"
# 列表筛选框能直接按这些字段做包含匹配
FILTER_FIELDS = ["检测编号", "检测管段", "检测设备"]
# 退回重检时随动作一起提交的结论字段，复核清单从这里取
CONCLUSION_FIELD = "整改结论"


class CctvService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter_rows(keyword=keyword, status=status, filters=filters)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def export_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """导出范围与列表当前筛选口径一致，但退回重检的报告不进入清单。"""
        rows = self._filter_rows(keyword=keyword, status=status, filters=filters)
        return [row for row in rows if row.get("status") != RETURNED_STATUS]

    def list_review(self) -> list[dict[str, Any]]:
        """复核清单：退回重检的报告连同整改结论一起列出来，等复核。"""
        items = []
        for row in store.rows(MODULE):
            if row.get("status") != RETURNED_STATUS:
                continue
            items.append({
                "id": row.get("id"),
                "检测编号": row.get("检测编号"),
                "检测管段": row.get("检测管段"),
                "检测设备": row.get("检测设备"),
                CONCLUSION_FIELD: row.get(CONCLUSION_FIELD) or "待补充",
                "检测状态": row.get("status"),
            })
        return items

    def _filter_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("检测编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        for field, value in (filters or {}).items():
            needle = str(value or "").strip()
            if field in FILTER_FIELDS and needle:
                rows = [row for row in rows if needle in str(row.get(field, ""))]
        return rows

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, ""
        rows = store.rows(MODULE)
        existing = next(
            (row for row in rows if str(row.get("检测编号", "")) == str(values.get("检测编号", ""))),
            None,
        )
        if existing is not None:
            # 同一检测编号只留后到的那一份：覆盖原记录，不再堆一条新的
            snapshot = copy.deepcopy(existing)
            try:
                for field in LIST_FIELDS + [CONCLUSION_FIELD]:
                    if values.get(field) is not None:
                        existing[field] = values.get(field)
                existing["status"] = STATUS_ORDER[0]
                existing["pending"] = True
                existing["abnormal"] = False
                store.save(MODULE)
            except Exception:
                # 落库失败时保留原值
                existing.clear()
                existing.update(snapshot)
                return None, [], "落库失败，已保留原值"
            return existing, [], "updated"
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in LIST_FIELDS + [CONCLUSION_FIELD]:
            if field not in entry and values.get(field) is not None:
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        try:
            store.save(MODULE)
        except Exception:
            rows.remove(entry)
            return None, [], "落库失败，已保留原值"
        return entry, [], "created"

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测报告 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于内窥检测可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        snapshot = copy.deepcopy(entry)
        try:
            entry["status"] = target
            entry["pending"] = target != STATUS_ORDER[-1]
            entry["abnormal"] = action in NEGATIVE_ACTIONS
            conclusion = str((values or {}).get(CONCLUSION_FIELD) or "").strip()
            if action == "退回重检" and conclusion:
                # 整改结论跟着报告走，复核清单才能读得到
                entry[CONCLUSION_FIELD] = conclusion
            store.save(MODULE)
        except Exception:
            # 落库失败时保留原值
            entry.clear()
            entry.update(snapshot)
            return None, f"检测报告{action}落库失败，已保留原值"
        return entry, f"检测报告已{action}"
