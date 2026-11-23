"""示例流程模板测试：解析校验、模板依赖收集、缺哪些、安装与不覆盖。"""

import json
import tempfile
import unittest
from pathlib import Path

from src.core.flow import validate_flow
from src.core.flow.templates import (
    FlowTemplateError,
    feature_names,
    install_templates,
    list_templates,
    load_template,
    missing_templates,
    required_templates,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def write_template(folder: Path, name: str, payload: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class TestShippedTemplates(unittest.TestCase):
    def test_three_templates_present(self):
        names = list_templates(REPO_ROOT / "assets" / "flow_templates")
        self.assertEqual(len(names), 3)
        self.assertIn("周常活跃奖励", names)

    def test_every_template_is_valid(self):
        for name in list_templates(REPO_ROOT / "assets" / "flow_templates"):
            with self.subTest(template=name):
                flow = load_template(name, REPO_ROOT / "assets" / "flow_templates")
                errors = [issue for issue in validate_flow(flow) if issue.level == "error"]
                self.assertEqual(errors, [], f"{name} 有错误: {errors}")
                self.assertGreater(flow.step_count(), 0)

    def test_weekly_template_needs_no_new_features(self):
        template_dir = REPO_ROOT / "assets" / "flow_templates"
        flow = load_template("周常活跃奖励", template_dir)
        self.assertEqual(missing_templates(flow), [])

    def test_skeletons_report_their_placeholders(self):
        template_dir = REPO_ROOT / "assets" / "flow_templates"
        crisis = missing_templates(load_template("危机讨伐（骨架）", template_dir))
        story = missing_templates(load_template("剧情委托（骨架）", template_dir))
        self.assertIn("crisis_hunt_entry", crisis)
        self.assertEqual(len(crisis), 3)
        self.assertIn("story_commission_settle", story)
        self.assertEqual(len(story), 3)

    def test_feature_names_reads_enum_values(self):
        names = feature_names()
        self.assertIn("loading_check", names)
        self.assertIn("confirm_button", names)
        self.assertNotIn("FeatureList.loading_check", names)


class TestRequiredTemplates(unittest.TestCase):
    def test_collects_nested_and_dedupes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_template(
                folder,
                "A",
                {
                    "name": "A",
                    "steps": [
                        {"type": "click", "template": "entry"},
                        {
                            "type": "loop",
                            "until_not_template": "claim",
                            "max": 3,
                            "steps": [
                                {"type": "if", "template": "confirm", "steps": [{"type": "click", "template": "entry"}]}
                            ],
                        },
                    ],
                },
            )
            flow = load_template("A", folder)
        self.assertEqual(required_templates(flow), ["entry", "claim", "confirm"])

    def test_missing_with_explicit_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_template(
                folder,
                "A",
                {"name": "A", "steps": [{"type": "wait_template", "template": "x"}, {"type": "wait", "seconds": 1}]},
            )
            flow = load_template("A", folder)
        self.assertEqual(missing_templates(flow, available={"x"}), [])
        self.assertEqual(missing_templates(flow, available=set()), ["x"])

    def test_flow_without_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_template(folder, "A", {"name": "A", "steps": [{"type": "wait", "seconds": 0.5}]})
            flow = load_template("A", folder)
        self.assertEqual(required_templates(flow), [])


class TestInstallTemplates(unittest.TestCase):
    def test_install_copies_and_skips_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "templates"
            target = root / "flows"
            write_template(source, "A", {"name": "A", "steps": [{"type": "wait", "seconds": 1}]})
            write_template(source, "B", {"name": "B", "steps": [{"type": "wait", "seconds": 1}]})

            report = install_templates(target_folder=target, folder=source)
            self.assertEqual(len(report.installed), 2)
            self.assertEqual(report.skipped, [])
            self.assertTrue((target / "A.json").is_file())

            again = install_templates(target_folder=target, folder=source)
            self.assertEqual(len(again.installed), 0)
            self.assertEqual(len(again.skipped), 2)
            self.assertIn("不覆盖", again.describe())

    def test_install_with_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "templates"
            target = root / "flows"
            write_template(source, "A", {"name": "A", "steps": [{"type": "wait", "seconds": 1}]})
            (target).mkdir()
            (target / "A.json").write_text("{}", encoding="utf-8")
            report = install_templates(target_folder=target, folder=source, overwrite=True)
            self.assertEqual(len(report.installed), 1)
            self.assertIn("steps", (target / "A.json").read_text(encoding="utf-8"))

    def test_bad_template_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "templates"
            source.mkdir()
            (source / "bad.json").write_text("{ oops", encoding="utf-8")
            report = install_templates(target_folder=root / "flows", folder=source)
            self.assertEqual(len(report.installed), 0)
            self.assertEqual(len(report.skipped), 1)

    def test_describe_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = install_templates(target_folder=Path(tmp) / "flows", folder=Path(tmp) / "none")
        self.assertEqual(report.describe(), "没有可安装的模板")

    def test_list_missing_folder(self):
        self.assertEqual(list_templates(Path("no-such-folder")), [])

    def test_load_missing_template(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(FlowTemplateError):
            load_template("nope", Path(tmp))


if __name__ == "__main__":
    unittest.main()
