"""节能改造业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "energyeff"
REQUIRED_FIELDS = ["项目编号", "所属站点", "改造内容"]
OPTIONAL_FIELDS = ["预估节电率", "投资金额", "承包单位", "基准期月均用电", "电价", "实际投资"]
STATUS_ORDER = ["待立项", "改造中", "评估中", "已验收"]
ACTION_RULES = {"申请立项": "改造中", "开始改造": "评估中", "验收评估": "已验收"}
NEGATIVE_ACTIONS = []

# 实测结论口径版本：已验收项目按这套规则重算过回收期后写入，避免重复迁移
CONCLUSION_VERSION = 2
# 估算与实测节电率允许的偏差（百分点），超出即标记并说明差在哪
DEVIATION_TOLERANCE = 5.0
# 验收时必须落实的实测数据：基准期用电、连续观察期用电、实际投资与电价
MEASURE_FIELDS = ["基准期月均用电", "观察期月均用电", "实际投资", "电价"]


def _to_float(value: Any) -> float | None:
    """把表单里带单位的输入（如 "18%"、"0.85"）转成浮点数；转不了就返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("%", "").replace("年", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class EnergyeffService:
    def __init__(self) -> None:
        # 规则调整后，已验收项目按实测口径重算一次回收期，当初的结论留档
        self.recalc_accepted()

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("项目编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            if field in values:
                entry[field] = values[field]
        entry["status"] = STATUS_ORDER[0]
        entry["项目状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["历史结论"] = []
        entry["结论版本"] = 1
        rows.append(entry)
        return entry, []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"节能项目 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于节能改造可执行范围"
        if action == "验收评估":
            return self._accept(entry, values or {})
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["项目状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"节能项目已{action}"

    # ---- 验收与回收期重算 ----

    def recalc_accepted(self) -> list[dict[str, Any]]:
        """已验收项目按实测口径重算回收期；当初的结论快照进历史结论留档。"""
        recalced = []
        for entry in store.rows(MODULE):
            if entry.get("status") != "已验收":
                continue
            if int(entry.get("结论版本") or 0) >= CONCLUSION_VERSION:
                continue
            if not self._has_measurements(entry):
                continue  # 缺实测数据的项目保持原样，补录后再算
            self._archive(entry, "首次验收结论")
            self._apply_conclusion(entry)
            recalced.append(entry)
        return recalced

    def _accept(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        # 同一个项目重复提交验收只认第一次，直接返回首次结论，不重算、不覆盖
        if entry.get("status") == "已验收":
            when = entry.get("验收时间") or "此前"
            return entry, f"该项目已于 {when} 完成验收，重复提交以首次验收结论为准"
        for field in MEASURE_FIELDS:
            if values.get(field) not in (None, ""):
                entry[field] = values[field]
        missing = [field for field in MEASURE_FIELDS if _to_float(entry.get(field)) is None]
        if missing:
            return None, f"验收实测数据不全，缺少：{'、'.join(missing)}"
        problem = self._validate_measurements(entry)
        if problem:
            return None, problem
        self._archive(entry, "立项估算")
        self._apply_conclusion(entry)
        entry["status"] = "已验收"
        entry["项目状态"] = "已验收"
        entry["pending"] = False
        entry["验收时间"] = date.today().isoformat()
        payback = entry["投资回收期"]
        payback_text = f"{payback} 年" if isinstance(payback, (int, float)) else str(payback)
        return entry, f"验收完成：实测节电率 {entry['实测节电率']}%，投资回收期重算为 {payback_text}"

    def _has_measurements(self, entry: dict[str, Any]) -> bool:
        return all(_to_float(entry.get(field)) is not None for field in MEASURE_FIELDS)

    def _validate_measurements(self, entry: dict[str, Any]) -> str | None:
        if (_to_float(entry.get("基准期月均用电")) or 0) <= 0:
            return "基准期月均用电必须大于 0，才能计算节电率"
        if (_to_float(entry.get("观察期月均用电")) or 0) < 0:
            return "观察期月均用电不能为负"
        if (_to_float(entry.get("电价")) or 0) <= 0:
            return "电价必须大于 0，才能折算节省的电费"
        if (_to_float(entry.get("实际投资")) or 0) < 0:
            return "实际投资不能为负"
        return None

    def _archive(self, entry: dict[str, Any], label: str) -> None:
        """把当前生效的结论快照进历史结论，留档之后再覆盖。"""
        history = entry.setdefault("历史结论", [])
        history.append({
            "口径": label,
            "节电率": entry.get("实测节电率", entry.get("预估节电率")),
            "投资回收期": entry.get("投资回收期"),
            "归档时间": date.today().isoformat(),
        })

    def _apply_conclusion(self, entry: dict[str, Any]) -> None:
        """按改造前后实测用电算节电率，再按实际投资与节省的电费重算回收期。"""
        baseline = _to_float(entry.get("基准期月均用电")) or 0.0
        observed = _to_float(entry.get("观察期月均用电")) or 0.0
        price = _to_float(entry.get("电价")) or 0.0
        invest = _to_float(entry.get("实际投资")) or 0.0
        rate = round((baseline - observed) / baseline * 100, 1)
        yearly_saving = round((baseline - observed) * 12 * price)
        entry["实测节电率"] = rate
        entry["年节省电费"] = yearly_saving
        if yearly_saving > 0:
            entry["投资回收期"] = round(invest * 10000 / yearly_saving, 1)
        else:
            entry["投资回收期"] = "无法回收"
        entry["结论版本"] = CONCLUSION_VERSION
        entry["abnormal"], entry["偏差说明"] = self._deviation(entry, rate, yearly_saving)

    def _deviation(self, entry: dict[str, Any], rate: float, yearly_saving: float) -> tuple[bool, str]:
        """估算与实测差得太多就标出来，并说明差在哪、对回收期有什么影响。"""
        notes: list[str] = []
        if yearly_saving <= 0:
            notes.append("观察期用电不低于基准期，改造未体现节电效果，投资无法回收")
        estimated = _to_float(entry.get("预估节电率"))
        if estimated is not None:
            gap = round(rate - estimated, 1)
            if abs(gap) > DEVIATION_TOLERANCE:
                direction = "高于" if gap > 0 else "低于"
                notes.append(
                    f"实测节电率 {rate}% {direction}立项估算 {estimated}%，"
                    f"偏差 {abs(gap)} 个百分点（容差 ±{DEVIATION_TOLERANCE}）"
                )
                notes.append(self._payback_impact(entry))
        return bool(notes), "；".join(note for note in notes if note)

    def _payback_impact(self, entry: dict[str, Any]) -> str:
        current = entry.get("投资回收期")
        previous = entry["历史结论"][-1] if entry.get("历史结论") else None
        if not previous:
            return ""
        old_payback = previous.get("投资回收期")
        if not isinstance(old_payback, (int, float)):
            return ""
        if not isinstance(current, (int, float)):
            return f"回收期由估算口径 {old_payback} 年变为无法回收"
        delta = round(current - old_payback, 1)
        if delta > 0:
            return f"回收期较估算口径 {old_payback} 年延长 {delta} 年"
        if delta < 0:
            return f"回收期较估算口径 {old_payback} 年缩短 {abs(delta)} 年"
        return ""
