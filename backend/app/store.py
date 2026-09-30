"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS


class StoreError(Exception):
    """落库失败时抛出：调用方负责保留现场，并给出可以再试一次的提示。"""


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def view(self, module: str) -> list[dict[str, Any]]:
        """只读查看：模块还不存在时返回空表，不像 rows() 那样顺手建表。"""
        return self._tables.get(module, [])

    def upsert(
        self,
        module: str,
        *,
        key: str,
        value: Any,
        entry: dict[str, Any],
    ) -> dict[str, Any]:
        """按 key 覆盖写入：同 key 记录整行替换（后到那一份覆盖），否则追加。

        先校验再落库；校验失败抛 StoreError，已有记录保持原值不动。
        """
        if not str(value or "").strip():
            raise StoreError(f"缺少定位字段「{key}」，无法落库")
        if not isinstance(entry, dict) or not entry:
            raise StoreError("写入内容为空，无法落库")
        rows = self.rows(module)
        new_entry = dict(entry)
        for index, row in enumerate(rows):
            if str(row.get(key, "")) == str(value):
                new_entry.setdefault("id", row.get("id"))
                rows[index] = new_entry
                return new_entry
        new_entry["id"] = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        rows.append(new_entry)
        return new_entry

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
