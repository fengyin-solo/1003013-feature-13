"""节能改造验收口径回归测试。

覆盖：
- 节电率按基准期/连续观察期实测用电计算；
- 投资回收期按实际投资与节省电费重算；
- 估算与实测偏差超限要标出并说明差在哪；
- 同一项目重复提交验收只认第一次；
- 口径调整后已验收项目重算，历史结论原样留档；
- 验收结论修改后留档且不改实测结果；
- 列表与详情读到的节电率保持一致。
"""
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient


class EnergyeffFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        # 每个用例重建内存仓库，避免种子数据与上一条用例互相污染。
        from app import seed, store as store_module

        self.original_rows = seed.SEED_ROWS["energyeff"]
        seed.SEED_ROWS["energyeff"] = []
        store_module.store = store_module.Store()
        from app.services import energyeff as energy_service
        from app.routers import energyeff as energy_router

        energy_service.store = store_module.store
        energy_router.service = energy_service.EnergyeffService()
        from app.main import app

        self.client = TestClient(app)

    def tearDown(self) -> None:
        from app import seed, store as store_module

        seed.SEED_ROWS["energyeff"] = self.original_rows

    def _create(self, project_no: str = "ENER-T", estimated: str = "20%", investment: float = 24000.0) -> int:
        response = self.client.post(
            "/api/energyeff",
            json={"values": {
                "项目编号": project_no,
                "所属站点": "测试基站",
                "改造内容": "开关电源休眠改造",
                "预估节电率": estimated,
                "投资金额": investment,
            }},
        )
        self.assertTrue(response.json()["ok"], response.text)
        return int(response.json()["entry"]["id"])

    def _move_to_review(self, entry_id: int, baseline: float = 1000.0, days: int = 10) -> None:
        self.assertTrue(self.client.post(
            f"/api/energyeff/{entry_id}/actions", json={"values": {"action": "申请立项"}}
        ).json()["ok"])
        result = self.client.post(
            f"/api/energyeff/{entry_id}/actions",
            json={"values": {"action": "开始改造", "基准期用电": baseline, "基准期天数": days}},
        )
        self.assertTrue(result.json()["ok"], result.text)

    def _accept(
        self,
        entry_id: int,
        *,
        observed: float = 800.0,
        days: int = 10,
        price: float = 0.8,
        actual: float | None = None,
    ):
        values = {"action": "验收评估", "观察期用电": observed, "观察期天数": days, "电价": price}
        if actual is not None:
            values["实际投资"] = actual
        return self.client.post(f"/api/energyeff/{entry_id}/actions", json={"values": values})

    def test_saving_rate_from_metered_power_and_payback_recalculated(self) -> None:
        entry_id = self._create(estimated="20%", investment=24000.0)
        self._move_to_review(entry_id, baseline=1000.0, days=10)
        result = self._accept(entry_id, observed=800.0, days=10, price=0.8, actual=23360.0)
        body = result.json()
        self.assertTrue(body["ok"], body)
        entry = body["entry"]
        # 节电率 = (100 - 80) / 100 = 20%
        self.assertAlmostEqual(entry["实测节电率数值"], 20.0, places=6)
        self.assertEqual(entry["实测节电率"], "20.0%")
        # 年节省电费 = (100 - 80) * 365 * 0.8 = 5840 元；回收期 = 23360 / (5840/12) ≈ 48 个月
        self.assertAlmostEqual(entry["年节省电费"], 5840.0, places=6)
        self.assertAlmostEqual(entry["实测回收期月数"], 48.0, places=6)
        self.assertEqual(entry["投资回收期"], "48.0个月")
        self.assertFalse(entry["偏差超限"])

    def test_deviation_beyond_limit_flagged_and_explained(self) -> None:
        entry_id = self._create(estimated="40%")
        self._move_to_review(entry_id)
        body = self._accept(entry_id, observed=900.0).json()
        self.assertTrue(body["ok"], body)
        entry = body["entry"]
        # 实测 10%，预估 40%，偏差 -30 个百分点，超过 10 个百分点阈值。
        self.assertAlmostEqual(entry["实测节电率数值"], 10.0, places=6)
        self.assertTrue(entry["偏差超限"])
        self.assertIn("40.0%", entry["差异说明"])
        self.assertIn("10.0%", entry["差异说明"])
        self.assertIn("回收期", entry["差异说明"])
        self.assertTrue(entry["abnormal"])

    def test_first_acceptance_only(self) -> None:
        entry_id = self._create()
        self._move_to_review(entry_id)
        first = self._accept(entry_id, observed=800.0)
        self.assertTrue(first.json()["ok"], first.text)
        # 再提交一组"更好看"的数据，必须被拒绝，实测节电率不能被覆盖。
        second = self._accept(entry_id, observed=500.0)
        self.assertFalse(second.json()["ok"])
        self.assertIn("只认第一次", second.json()["message"])
        detail = self.client.get(f"/api/energyeff/{entry_id}").json()
        self.assertEqual(detail["实测节电率"], "20.0%")
        self.assertEqual(len(detail["验收档案"]), 1)
        self.assertEqual(detail["验收档案"][0]["来源"], "验收评估")

    def test_observation_period_too_short_rejected(self) -> None:
        entry_id = self._create()
        self._move_to_review(entry_id, baseline=1000.0, days=30)
        result = self._accept(entry_id, observed=200.0, days=5)
        self.assertFalse(result.json()["ok"])
        self.assertIn("观察期", result.json()["message"])

    def test_baseline_locked_after_renovation_start(self) -> None:
        entry_id = self._create()
        self._move_to_review(entry_id, baseline=1000.0, days=10)
        response = self.client.post(
            f"/api/energyeff/{entry_id}/actions",
            json={"values": {
                "action": "验收评估",
                "基准期用电": 600.0,
                "基准期天数": 10,
                "观察期用电": 800.0,
                "观察期天数": 10,
                "电价": 0.8,
            }},
        )
        self.assertFalse(response.json()["ok"])
        self.assertIn("基准期", response.json()["message"])

    def test_existing_baseline_not_overwritten(self) -> None:
        # 种子/历史带入的基准期数据（改造中状态）不能被再次「开始改造」覆盖。
        from app import seed, store as store_module

        legacy_rows = [{
            "id": 92,
            "status": "改造中",
            "pending": True,
            "abnormal": False,
            "项目编号": "ENER-OLD-2",
            "所属站点": "基准期已留档站点",
            "改造内容": "空调改造",
            "预估节电率": "20%",
            "投资金额": 10000.0,
            "基准期用电": 3000.0,
            "基准期天数": 30,
        }]
        original = seed.SEED_ROWS["energyeff"]
        seed.SEED_ROWS["energyeff"] = legacy_rows
        store_module.store = store_module.Store()
        from app.services import energyeff as energy_service
        from app.routers import energyeff as energy_router

        energy_service.store = store_module.store
        energy_router.service = energy_service.EnergyeffService()
        seed.SEED_ROWS["energyeff"] = original

        response = self.client.post(
            "/api/energyeff/92/actions",
            json={"values": {"action": "开始改造", "基准期用电": 1000.0, "基准期天数": 10}},
        )
        self.assertFalse(response.json()["ok"])
        self.assertIn("基准期", response.json()["message"])
        entry = store_module.store.find("energyeff", 92)
        self.assertEqual(entry["基准期用电"], 3000.0)
        self.assertEqual(entry["基准期天数"], 30)

    def test_conclusion_edit_archives_without_changing_metrics(self) -> None:
        entry_id = self._create()
        self._move_to_review(entry_id)
        self._accept(entry_id)
        edited = self.client.patch(
            f"/api/energyeff/{entry_id}/conclusion",
            json={"values": {"验收结论": "复查后结论不变，同意归档。"}},
        )
        body = edited.json()
        self.assertTrue(body["ok"], body)
        self.assertEqual(body["entry"]["实测节电率"], "20.0%")
        detail = self.client.get(f"/api/energyeff/{entry_id}").json()
        sources = [record["来源"] for record in detail["验收档案"]]
        self.assertEqual(sources, ["验收评估", "验收结论修改"])
        self.assertEqual(detail["验收结论"], "复查后结论不变，同意归档。")

    def test_list_and_detail_share_same_rate(self) -> None:
        entry_id = self._create(project_no="ENER-SAME", estimated="20%")
        self._move_to_review(entry_id)
        self._accept(entry_id)
        listed = self.client.get("/api/energyeff?keyword=ENER-SAME").json()["items"][0]
        detail = self.client.get(f"/api/energyeff/{entry_id}").json()
        self.assertEqual(listed["实测节电率"], detail["实测节电率"])
        self.assertEqual(listed["投资回收期"], detail["投资回收期"])

    def test_no_saving_means_payback_unrecoverable(self) -> None:
        entry_id = self._create(estimated="10%")
        self._move_to_review(entry_id, baseline=1000.0, days=10)
        body = self._accept(entry_id, observed=1100.0).json()
        self.assertTrue(body["ok"], body)
        self.assertAlmostEqual(body["entry"]["实测节电率数值"], -10.0, places=6)
        self.assertEqual(body["entry"]["投资回收期"], "无法回收（实测未节电）")
        self.assertTrue(body["entry"]["偏差超限"])


class LegacyMigrationTests(unittest.TestCase):
    def test_accepted_projects_recalculated_with_original_conclusion_archived(self) -> None:
        from app import seed, store as store_module

        legacy_rows = [{
            "id": 91,
            "status": "已验收",
            "pending": False,
            "abnormal": False,
            "项目编号": "ENER-OLD-1",
            "所属站点": "老口径站点",
            "改造内容": "空调改造",
            "预估节电率": "40%",
            "投资金额": 60000.0,
            "承包单位": "某节能公司",
            "投资回收期": "约20个月",
            "基准期用电": 15000.0,
            "基准期天数": 30,
            "观察期用电": 13800.0,
            "观察期天数": 30,
            "电价": 0.8,
            "实际投资": 62000.0,
            "验收时间": "2026-09-02",
        }]
        original = seed.SEED_ROWS["energyeff"]
        seed.SEED_ROWS["energyeff"] = legacy_rows
        store_module.store = store_module.Store()
        from app.services import energyeff as energy_service

        energy_service.store = store_module.store
        migrated = energy_service.migrate_legacy_accepted(store_module.store)
        seed.SEED_ROWS["energyeff"] = original

        self.assertEqual(migrated, 1)
        entry = store_module.store.find("energyeff", 91)
        self.assertEqual(entry["实测节电率"], "8.0%")
        self.assertTrue(entry["偏差超限"])
        self.assertAlmostEqual(entry["实测回收期月数"], 63.6986, places=1)
        archive = entry["验收档案"]
        self.assertEqual(archive[0]["来源"], "口径调整前历史结论留档")
        # 历史结论按当初那份留档：预估与旧回收期原文不动。
        self.assertEqual(archive[0]["预估节电率"], "40%")
        self.assertEqual(archive[0]["投资回收期"], "约20个月")
        self.assertIn("未计算", archive[0]["实测节电率"])


if __name__ == "__main__":
    unittest.main()
