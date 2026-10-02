"""节能改造接口：维护节能项目，覆盖立项、改造基准期留档、实测验收与结论留档。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.energyeff import DISPLAY_FIELDS, EnergyeffService, STATUS_ORDER

router = APIRouter(prefix="/api/energyeff", tags=["节能改造"])

service = EnergyeffService()

LIST_FIELDS = DISPLAY_FIELDS
STATUSES = STATUS_ORDER


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按项目编号检索"),
    status: str | None = Query(default=None, description="待立项、改造中、评估中、已验收"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按项目编号与状态过滤节能改造列表；节电率/回收期均由统一口径实时算出，列表与详情同源。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats", response_model=dict)
def stats() -> dict[str, Any]:
    """看板统计：各状态项目数，以及预估与实测偏差超限的已验收项目数。"""
    return {"items": service.stats()}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出节能改造清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "energyeff", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条节能项目明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"节能项目 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条节能项目，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="节能项目已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """执行立项、开始改造（留基准期用电）、验收评估（观察期实测用电）。

    验收评估只在「评估中」开放：同一项目重复提交验收只认第一次，
    已验收项目再提交会被拦下并提示走结论修改入口。
    """
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.patch("/{entry_id}/conclusion", response_model=ActionResult)
def update_conclusion(entry_id: int, payload: EntryPayload) -> ActionResult:
    """修改已验收项目的验收结论；只改结论文字，实测数据与重算结果不变，修改痕迹留档。"""
    conclusion = str(payload.values.get("验收结论") or "")
    entry, message = service.update_conclusion(entry_id, conclusion)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
