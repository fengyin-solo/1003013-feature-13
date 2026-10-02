"""节能改造业务规则。

节电率口径：按改造前后实测用电计算——
    基准期日均用电 = 基准期用电 / 基准期天数
    观察期日均用电 = 连续观察期用电 / 观察期天数
    实测节电率 = (基准期日均 - 观察期日均) / 基准期日均 × 100%
投资回收期：实际投资 / (年节省电费 / 12)，年节省电费由实测节电量折算。
验收只认同一项目的第一次提交；口径调整后已验收项目统一重算，当初的结论留档。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.store import store

MODULE = "energyeff"
REQUIRED_FIELDS = ["项目编号", "所属站点", "改造内容"]
STATUS_ORDER = ["待立项", "改造中", "评估中", "已验收"]
ACCEPT_ACTION = "验收评估"
ACTION_RULES = {"申请立项": "改造中", "开始改造": "评估中", ACCEPT_ACTION: "已验收"}
# 各状态允许执行的动作：已验收后任何动作都不再开放（验收只认第一次）。
STATUS_ACTIONS = {
    "待立项": ["申请立项"],
    "改造中": ["开始改造"],
    "评估中": [ACCEPT_ACTION],
    "已验收": [],
}

# 立项预估与实测节电率的允许偏差：绝对差超过该百分点数即标异常并说明差在哪。
DEVIATION_LIMIT_POINTS = 10.0
# 验收观察期最短天数：连续观察期不足 7 天的实测数据不予采信。
MIN_OBSERVATION_DAYS = 7
DAYS_PER_YEAR = 365

DISPLAY_FIELDS = [
    "项目编号", "所属站点", "改造内容", "预估节电率", "实测节电率",
    "投资金额", "实际投资", "承包单位", "投资回收期", "项目状态",
]


def _to_number(value: Any) -> float | None:
    """把表单里可能出现的 12、'12'、'12.5'、'12%'、'' 统一解析成数字。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def _parse_percent(value: Any) -> float | None:
    """预估节电率可能登记成 '25%'、'25' 或 0.25，统一换算成百分数数值。"""
    number = _to_number(value)
    if number is None:
        return None
    text = str(value).strip()
    if isinstance(value, str) and "%" not in text and 0 < number <= 1:
        number *= 100
    return number


def _format_percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def _format_money(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f} 元"


def _parse_months(text: Any) -> float | None:
    """从历史回收期文本（如 '约20个月'）里尽量还原月数，便于和重算值比较。"""
    number = _to_number(text)
    return number if number is not None and number > 0 else None


def _snapshot(entry: dict[str, Any], *, source: str, stamped_at: str) -> dict[str, Any]:
    """把一份验收结论原样留档，后续重算与修改都不覆盖档案。"""
    return {
        "来源": source,
        "留档时间": stamped_at,
        "项目编号": entry.get("项目编号"),
        "预估节电率": entry.get("预估节电率"),
        "实测节电率": entry.get("实测节电率"),
        "基准期用电": entry.get("基准期用电"),
        "基准期天数": entry.get("基准期天数"),
        "观察期用电": entry.get("观察期用电"),
        "观察期天数": entry.get("观察期天数"),
        "电价": entry.get("电价"),
        "实际投资": entry.get("实际投资", entry.get("投资金额")),
        "投资回收期": entry.get("投资回收期"),
        "验收结论": entry.get("验收结论", ""),
    }


def compute_metrics(entry: dict[str, Any]) -> dict[str, Any]:
    """所有派生指标只在这里算一次，列表与详情共用，保证两处读到的节电率一致。"""
    result: dict[str, Any] = {
        "预估节电率数值": None,
        "基准期日均用电": None,
        "观察期日均用电": None,
        "实测节电率数值": None,
        "实测节电率": None,
        "观察期节电量": None,
        "年节电量": None,
        "年节省电费": None,
        "实测回收期月数": None,
        "节电率偏差": None,
        "偏差超限": False,
        "差异说明": "",
    }

    result["预估节电率数值"] = _parse_percent(entry.get("预估节电率"))

    baseline = _to_number(entry.get("基准期用电"))
    baseline_days = _to_number(entry.get("基准期天数"))
    observed = _to_number(entry.get("观察期用电"))
    observed_days = _to_number(entry.get("观察期天数"))
    price = _to_number(entry.get("电价"))

    if baseline is not None and baseline_days and baseline_days > 0:
        result["基准期日均用电"] = baseline / baseline_days
    if observed is not None and observed_days and observed_days > 0:
        result["观察期日均用电"] = observed / observed_days

    base_avg = result["基准期日均用电"]
    obs_avg = result["观察期日均用电"]
    accepted = entry.get("status") == STATUS_ORDER[-1]
    if accepted and base_avg is not None and obs_avg is not None and base_avg > 0:
        rate = (base_avg - obs_avg) / base_avg * 100
        result["实测节电率数值"] = rate
        result["实测节电率"] = _format_percent(rate)
        period_saving = (base_avg - obs_avg) * observed_days
        result["观察期节电量"] = period_saving
        annual_saving_kwh = (base_avg - obs_avg) * DAYS_PER_YEAR
        result["年节电量"] = annual_saving_kwh
        if price is not None:
            result["年节省电费"] = annual_saving_kwh * price

        actual_investment = _to_number(entry.get("实际投资"))
        if actual_investment is None:
            actual_investment = _to_number(entry.get("投资金额"))
        annual_bill_saving = result["年节省电费"]
        if actual_investment is not None and annual_bill_saving is not None:
            if annual_bill_saving > 0:
                result["实测回收期月数"] = actual_investment / (annual_bill_saving / 12)
                result["投资回收期"] = f"{result['实测回收期月数']:.1f}个月"
            else:
                result["投资回收期"] = "无法回收（实测未节电）"

        estimated = result["预估节电率数值"]
        if estimated is None:
            result["差异说明"] = "立项时未登记预估节电率，无法与实测值比对，请补齐立项资料。"
        else:
            deviation = rate - estimated
            result["节电率偏差"] = deviation
            if abs(deviation) > DEVIATION_LIMIT_POINTS:
                result["偏差超限"] = True
                direction = "低于" if deviation < 0 else "高于"
                lines = [
                    f"实测节电率 {rate:.1f}% 比立项预估 {estimated:.1f}% {direction} "
                    f"{abs(deviation):.1f} 个百分点，超过 {DEVIATION_LIMIT_POINTS:.0f} 个百分点的允许偏差。",
                    f"基准期日均用电 {base_avg:.1f} 度，连续观察期日均用电 {obs_avg:.1f} 度，"
                    f"折年节电 {annual_saving_kwh:.0f} 度。",
                ]
                old_months = _parse_months(entry.get("立项回收期"))
                if price is not None:
                    lines.append(
                        f"按电价 {price:.2f} 元/度折年节省电费 {annual_bill_saving:.0f} 元。"
                    )
                if result["实测回收期月数"] is not None:
                    if old_months is not None:
                        delta = result["实测回收期月数"] - old_months
                        tail = "拉长" if delta >= 0 else "缩短"
                        lines.append(
                            f"立项估回收期 {old_months:.1f} 个月，按实际投资与实测节费重算为 "
                            f"{result['实测回收期月数']:.1f} 个月，回收期{tail} {abs(delta):.1f} 个月。"
                        )
                    else:
                        lines.append(
                            f"投资回收期按实际投资与实测节费重算为 {result['实测回收期月数']:.1f} 个月。"
                        )
                elif annual_bill_saving is not None and annual_bill_saving <= 0:
                    lines.append("观察期用电不低于基准期，实测未产生节电收益，投资无法按预期回收。")
                result["差异说明"] = "".join(lines)

    return result


def decorate(entry: dict[str, Any]) -> dict[str, Any]:
    """给记录补上统一口径的派生字段。原始字段不动，计算逻辑全部走 compute_metrics。"""
    metrics = compute_metrics(entry)
    entry.update(metrics)
    entry["项目状态"] = entry.get("status")
    # 未验收时回收期沿用立项/改造阶段登记的口径，避免列表详情读到空白。
    if entry.get("status") != STATUS_ORDER[-1] and not entry.get("投资回收期"):
        entry["投资回收期"] = "待验收"
    return entry


class EnergyeffService:
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
        page_rows = [decorate(dict(row)) for row in rows[start:start + size]]
        return page_rows, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return decorate(dict(entry)) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ["项目编号", "所属站点", "改造内容", "承包单位"]:
            entry[field] = str(values.get(field) or "").strip()
        estimated = _parse_percent(values.get("预估节电率"))
        entry["预估节电率"] = _format_percent(estimated) if estimated is not None else ""
        investment = _to_number(values.get("投资金额"))
        entry["投资金额"] = investment
        entry["投资回收期"] = "待立项测算"
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return decorate(dict(entry)), []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"节能项目 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于节能改造可执行范围"
        allowed = STATUS_ACTIONS.get(str(entry.get("status")), [])
        if action not in allowed:
            if entry.get("status") == STATUS_ORDER[-1]:
                return None, "该项目已验收，同一项目重复提交验收只认第一次，结论修改请走验收结论修改入口"
            return None, f"当前状态「{entry.get('status')}」不允许执行「{action}」"

        values = values or {}
        if action == "开始改造":
            message = self._save_baseline(entry, values)
            if message:
                return None, message
        if action == ACCEPT_ACTION:
            message = self._accept(entry, values)
            if message:
                return None, message
            return decorate(dict(entry)), "节能项目已按改造前后实测用电完成验收，节电率与回收期已按新口径计算"

        target = ACTION_RULES[action]
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        return decorate(dict(entry)), f"节能项目已{action}"

    def _save_baseline(self, entry: dict[str, Any], values: dict[str, Any]) -> str:
        """开始改造时固定基准期用电；基准期一旦留档，验收时不允许再改。"""
        baseline = _to_number(values.get("基准期用电"))
        baseline_days = _to_number(values.get("基准期天数"))
        if baseline is None and baseline_days is None:
            return ""  # 允许改造开始时先不录，验收提交前补齐即可
        if baseline is None or baseline <= 0:
            return "基准期用电必须为大于 0 的数字（单位：度）"
        if baseline_days is None or baseline_days <= 0:
            return "基准期天数必须为大于 0 的数字"
        if entry.get("基准期用电") is not None and baseline != _to_number(entry.get("基准期用电")):
            return "基准期用电已留档，不得修改"
        entry["基准期用电"] = baseline
        entry["基准期天数"] = int(baseline_days)
        return ""

    def _accept(self, entry: dict[str, Any], values: dict[str, Any]) -> str:
        baseline = _to_number(values.get("基准期用电"))
        baseline_days = _to_number(values.get("基准期天数"))
        # 基准期此前没留档的，验收提交时必须一并补齐；已留档的只能沿用，不能借验收改数。
        if entry.get("基准期用电") is None:
            if baseline is None or baseline <= 0:
                return "缺少改造前基准期用电，请先补录基准期用电（单位：度）再提交验收"
            if baseline_days is None or baseline_days <= 0:
                return "缺少基准期天数，请补录基准期统计天数"
            entry["基准期用电"] = baseline
            entry["基准期天数"] = int(baseline_days)
        elif baseline is not None and (
            baseline != _to_number(entry.get("基准期用电"))
            or (baseline_days is not None and int(baseline_days) != int(entry.get("基准期天数")))
        ):
            return "基准期用电在改造开始时已留档，验收时不得修改；如需更正请走结论修改并说明原因"

        observed = _to_number(values.get("观察期用电"))
        observed_days = _to_number(values.get("观察期天数"))
        if observed is None or observed < 0:
            return "缺少连续观察期用电，请填写观察期实测用电（单位：度）"
        if observed_days is None or observed_days < MIN_OBSERVATION_DAYS:
            return f"连续观察期不得少于 {MIN_OBSERVATION_DAYS} 天，当前实测数据不足，暂不采信"
        price = _to_number(values.get("电价"))
        if price is None or price <= 0:
            return "缺少电价或电价不大于 0，无法折算节省电费"
        actual_investment = _to_number(values.get("实际投资"))
        if actual_investment is None:
            actual_investment = _to_number(entry.get("投资金额"))
        if actual_investment is None or actual_investment < 0:
            return "缺少实际投资，请填写项目实际投资金额"

        entry["立项回收期"] = entry.get("投资回收期")
        entry["观察期用电"] = observed
        entry["观察期天数"] = int(observed_days)
        entry["电价"] = price
        entry["实际投资"] = actual_investment
        conclusion = str(values.get("验收结论") or "").strip() or "验收通过，节电率与投资回收期以改造前后实测数据重算结果为准。"
        entry["验收结论"] = conclusion
        entry["验收时间"] = date.today().isoformat()
        entry["status"] = STATUS_ORDER[-1]
        entry["pending"] = False

        decorated = decorate(dict(entry))
        entry["abnormal"] = bool(decorated.get("偏差超限"))
        archive = entry.setdefault("验收档案", [])
        record = _snapshot(decorated, source="验收评估", stamped_at=entry["验收时间"])
        archive.append(record)
        return ""

    def update_conclusion(self, entry_id: int, conclusion: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"节能项目 {entry_id} 不存在或已归档"
        if entry.get("status") != STATUS_ORDER[-1]:
            return None, "只有已验收项目可以修改验收结论"
        text = conclusion.strip()
        if not text:
            return None, "验收结论不能为空"
        decorated = decorate(dict(entry))
        archive = entry.setdefault("验收档案", [])
        archive.append({
            "来源": "验收结论修改",
            "留档时间": date.today().isoformat(),
            "原结论": entry.get("验收结论", ""),
            "新结论": text,
            "实测节电率": decorated.get("实测节电率"),
            "投资回收期": decorated.get("投资回收期"),
        })
        entry["验收结论"] = text
        return decorate(dict(entry)), "验收结论已更新，实测节电率与投资回收期口径不变"

    def stats(self) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        accepted = [row for row in rows if row.get("status") == STATUS_ORDER[-1]]
        abnormal = 0
        for row in accepted:
            if decorate(dict(row)).get("偏差超限"):
                abnormal += 1
        return [
            {"label": "待立项项目", "value": sum(1 for r in rows if r.get("status") == "待立项")},
            {"label": "改造/评估中项目", "value": sum(1 for r in rows if r.get("status") in ("改造中", "评估中"))},
            {"label": "已验收项目", "value": len(accepted)},
            {"label": "偏差超限项目", "value": abnormal},
        ]


def migrate_legacy_accepted(store_obj: Any) -> int:
    """口径调整：已验收但还没有验收档案的老项目，先把当初结论留档，再按实测重算。"""
    migrated = 0
    today = date.today().isoformat()
    for row in store_obj.rows(MODULE):
        if row.get("status") != STATUS_ORDER[-1] or row.get("验收档案"):
            continue
        legacy = dict(row)
        legacy["实测节电率"] = "（旧口径未计算实测节电率）"
        archive_record = _snapshot(legacy, source="口径调整前历史结论留档", stamped_at=today)
        archive_record["说明"] = "节电率与回收期口径调整，历史结论按当初登记原样留档，之后按实测数据重算"
        row["验收档案"] = [archive_record]
        row["立项回收期"] = row.get("投资回收期")
        # 老数据可能缺投资金额或电价，缺的字段保持原样，由计算函数显式给出空值而不是编造。
        decorated = decorate(dict(row))
        row.update({key: decorated[key] for key in (
            "实测节电率", "投资回收期", "偏差超限", "差异说明",
            "实测节电率数值", "年节省电费", "实测回收期月数",
        ) if decorated.get(key) is not None})
        row["abnormal"] = bool(decorated.get("偏差超限"))
        row["pending"] = False
        migrated += 1
    return migrated
