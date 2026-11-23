"""养成计算测试：数据载入、区间切分、潜能/升星、库存缺口、体力折算、导出。"""

import csv
import tempfile
import unittest
from pathlib import Path

from src.core.growth import (
    Dataset,
    GrowthDataError,
    GrowthInputError,
    Target,
    compute_plan,
    export_csv,
    export_png,
    material_rows,
    target_rows,
)

DATA_PATH = Path(__file__).resolve().parents[1] / "assets" / "data" / "growth.json"


def small_dataset() -> Dataset:
    return Dataset.from_dict(
        {
            "version": 1,
            "materials": {"尤尼": {"category": "currency"}, "星脉结晶": {"category": "currency"},
                          "风之碎晶": {"category": "ascension"}, "神秘素材": {"category": "ascension"}},
            "exp_items": {"小灵粹": 100, "大灵粹": 1000},
            "dungeons": [
                {"name": "贵的本", "stamina": 40, "drops": {"风之碎晶": 1}},
                {"name": "便宜的本", "stamina": 20, "drops": {"风之碎晶": 2}},
                {"name": "星辉本", "stamina": 40, "drops": {"星脉结晶": 1}},
            ],
            "aliases": {"星脉结晶": {"大星脉结晶": 5}},
            "entries": [
                {
                    "key": "hero",
                    "name": "英雄",
                    "kind": "character",
                    "max_level": 40,
                    "levels": [
                        {"from": 1, "to": 20, "exp": 1000, "credits": 500, "materials": {"风之碎晶": 2}},
                        {"from": 21, "to": 40, "exp": 3000, "credits": 1500, "materials": {"风之碎晶": 4}},
                    ],
                },
                {
                    "key": "beast",
                    "name": "灵兽",
                    "kind": "pet",
                    "max_level": 20,
                    "levels": [
                        {"from": 1, "to": 20, "exp": 2000, "credits": 800, "materials": {"神秘素材": 3}},
                    ],
                    "potentials": [
                        {"name": "生命", "levels": [{"level": 1, "exp": 100}, {"level": 2, "exp": 100}]},
                        {"name": "攻击", "levels": [{"level": 1, "exp": 100}, {"level": 2, "exp": 100}]},
                    ],
                },
                {
                    "key": "gear",
                    "name": "装备",
                    "kind": "equipment",
                    "max_level": 20,
                    "levels": [{"from": 1, "to": 20, "exp": 500, "credits": 200, "materials": {}}],
                    "star_stages": [
                        {"star": 1, "copies": 1, "materials": {"星脉结晶": 4}},
                        {"star": 2, "copies": 2, "materials": {"星脉结晶": 6}},
                    ],
                },
            ],
        }
    )


class TestDataset(unittest.TestCase):
    def test_builtin_data_loads(self):
        data = Dataset.load_default()
        summary = data.kinds_summary()
        self.assertGreater(summary["character"], 0)
        self.assertGreater(summary["pet"], 0)
        self.assertGreater(summary["spirit"], 0)
        self.assertGreater(summary["equipment"], 0)
        self.assertIn("示例", data.note)

    def test_all_kinds_present_in_builtin(self):
        data = Dataset.from_file(DATA_PATH)
        for kind in ("character", "pet", "spirit", "equipment"):
            self.assertTrue(data.entries_of(kind), kind)

    def test_entry_missing(self):
        with self.assertRaises(GrowthDataError):
            small_dataset().entry("nope")

    def test_missing_entries(self):
        with self.assertRaises(GrowthDataError):
            Dataset.from_dict({"version": 1})

    def test_bad_kind(self):
        with self.assertRaises(GrowthDataError):
            Dataset.from_dict({"entries": [{"key": "a", "kind": "spaceship"}]})

    def test_bad_level_range(self):
        with self.assertRaises(GrowthDataError):
            Dataset.from_dict(
                {"entries": [{"key": "a", "levels": [{"from": 20, "to": 10}]}]}
            )

    def test_duplicate_key(self):
        with self.assertRaises(GrowthDataError):
            Dataset.from_dict({"entries": [{"key": "a"}, {"key": "a"}]})

    def test_pet_has_six_potentials_in_builtin(self):
        data = Dataset.load_default()
        pet = data.entries_of("pet")[0]
        self.assertEqual(len(pet.potentials), 6)
        self.assertEqual(len(pet.potentials[0].levels), 9)


class TestSpanMath(unittest.TestCase):
    def test_full_range_sums_all_spans(self):
        plan = compute_plan(small_dataset(), [Target("hero")])
        self.assertAlmostEqual(plan.targets[0].exp, 4000)
        self.assertAlmostEqual(plan.targets[0].credits, 2000)
        self.assertEqual(plan.targets[0].stages, 2)

    def test_partial_range_uses_ratio(self):
        plan = compute_plan(small_dataset(), [Target("hero", from_level=21, to_level=40)])
        self.assertAlmostEqual(plan.targets[0].exp, 3000)
        self.assertEqual(plan.targets[0].stages, 1)

    def test_copies_multiply(self):
        plan = compute_plan(small_dataset(), [Target("hero", copies=3)])
        self.assertAlmostEqual(plan.targets[0].exp, 12000)
        self.assertAlmostEqual(plan.materials["风之碎晶"], 18)

    def test_levels_are_clamped(self):
        plan = compute_plan(small_dataset(), [Target("hero", from_level=1, to_level=999)])
        self.assertEqual(plan.targets[0].target.to_level, 40)


class TestPotentialsAndStars(unittest.TestCase):
    def test_potential_exp(self):
        plan = compute_plan(small_dataset(), [Target("beast", potential_level=2)])
        # 2 条潜能 × 2 级 × 100 = 400
        self.assertAlmostEqual(plan.targets[0].potential_exp, 400)
        self.assertAlmostEqual(plan.targets[0].exp, 2400)

    def test_star_copies_and_materials(self):
        plan = compute_plan(small_dataset(), [Target("gear", star=2)])
        self.assertEqual(plan.targets[0].star_copies, 3)
        self.assertAlmostEqual(plan.materials["星脉结晶"], 10)

    def test_star_is_clamped_to_available(self):
        plan = compute_plan(small_dataset(), [Target("gear", star=99)])
        self.assertEqual(plan.targets[0].target.star, 2)


class TestInventoryAndSources(unittest.TestCase):
    def test_gap_uses_inventory(self):
        plan = compute_plan(small_dataset(), [Target("hero")], inventory={"风之碎晶": 5})
        self.assertAlmostEqual(plan.materials["风之碎晶"], 6)
        self.assertAlmostEqual(plan.gap_of("风之碎晶"), 1)

    def test_no_gap_when_enough(self):
        plan = compute_plan(small_dataset(), [Target("hero")], inventory={"风之碎晶": 99})
        self.assertEqual(plan.gap_of("风之碎晶"), 0)

    def test_best_stamina_source_is_used(self):
        plan = compute_plan(small_dataset(), [Target("hero")])
        # 便宜的本：20 体力 / 2 个 = 10 体力每个；6 个 = 60 体力、3 次
        self.assertAlmostEqual(plan.stamina["风之碎晶"], 60)
        self.assertEqual(plan.runs["风之碎晶"], 3)

    def test_material_without_source(self):
        plan = compute_plan(small_dataset(), [Target("beast")])
        self.assertIn("神秘素材", plan.no_source)
        self.assertNotIn("神秘素材", plan.stamina)

    def test_crystals_prefer_big(self):
        plan = compute_plan(small_dataset(), [Target("gear", star=2)])
        self.assertEqual(plan.crystals.get("大星脉结晶"), 2)

    def test_crystals_use_gap(self):
        plan = compute_plan(small_dataset(), [Target("hero")], inventory={"尤尼": 99999})
        plan_gear = compute_plan(
            small_dataset(), [Target("gear", star=2)], inventory={"星脉结晶": 10}
        )
        self.assertEqual(plan_gear.crystals, {})

    def test_exp_items_greedy(self):
        plan = compute_plan(small_dataset(), [Target("hero")])
        # 4000 经验 → 4 个大灵粹
        self.assertEqual(plan.exp_items.get("大灵粹"), 4)


class TestPlanValidation(unittest.TestCase):
    def test_empty_targets(self):
        with self.assertRaises(GrowthInputError):
            compute_plan(small_dataset(), [])

    def test_too_many_targets(self):
        with self.assertRaises(GrowthInputError):
            compute_plan(small_dataset(), [Target("hero")] * 13)

    def test_unknown_entry(self):
        with self.assertRaises(GrowthDataError):
            compute_plan(small_dataset(), [Target("ghost")])

    def test_no_op_target_is_skipped(self):
        plan = compute_plan(small_dataset(), [Target("hero", from_level=40, to_level=40)])
        self.assertEqual(plan.targets, [])
        self.assertTrue(any("跳过" in note for note in plan.notes))

    def test_summary_lines(self):
        plan = compute_plan(small_dataset(), [Target("hero")])
        text = "\n".join(plan.summary_lines())
        self.assertIn("经验", text)
        self.assertIn("尤尼", text)


class TestExport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.plan = compute_plan(
            Dataset.load_default(),
            [Target("char_amber"), Target("pet_gale", potential_level=9)],
            inventory={"尤尼": 1000},
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_rows(self):
        rows = material_rows(self.plan)
        self.assertTrue(rows)
        self.assertIn("缺口", rows[0])
        self.assertEqual(len(target_rows(self.plan)), 2)

    def test_csv_export(self):
        path = export_csv(self.plan, self.root / "out.csv")
        text = path.read_text(encoding="utf-8-sig")
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertIn("养成目标", [row[0] for row in rows if row])
        self.assertIn("材料清单", [row[0] for row in rows if row])
        self.assertIn("总经验", [row[0] for row in rows if row])
        self.assertIn("琥珀", text)

    def test_png_export(self):
        path = export_png(self.plan, self.root / "card.png")
        self.assertTrue(path.is_file())
        self.assertGreater(path.stat().st_size, 5000)
        from PIL import Image

        with Image.open(path) as image:
            self.assertEqual(image.width, 1280)
            self.assertGreater(image.height, 200)


if __name__ == "__main__":
    unittest.main()
