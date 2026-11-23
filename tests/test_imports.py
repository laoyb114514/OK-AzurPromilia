"""导入体检：把 ``src/`` 下每个模块都 import 一遍。

回归测试大多只碰到自己关心的模块，GUI 页和补丁模块经常没人碰——
一个拼错的名字可以一直躺到用户点开那一页才炸。这个测试把整棵树都导一遍，
不需要游戏、不需要窗口（Qt 控件 import 不需要 QApplication）。
"""

import importlib
import unittest
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"

SKIP_PARTS = {"__pycache__"}


def iter_modules() -> list[str]:
    names = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        relative = path.relative_to(SRC_ROOT.parent).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        names.append(".".join(parts))
    return names


class TestImports(unittest.TestCase):
    def test_every_module_imports(self):
        modules = iter_modules()
        self.assertGreater(len(modules), 50, "src 下模块数量异常")
        failures = []
        for name in modules:
            try:
                importlib.import_module(name)
            except Exception as exc:  # 收集全部失败再一起报，避免只看到第一个
                failures.append(f"{name}: {type(exc).__name__}: {exc}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_config_tabs_and_tasks_resolve(self):
        """config.py 里声明的每个 Tab / 任务都能真的导到类。"""
        from src.config import config

        failures = []
        for group in ("custom_tabs", "onetime_tasks", "trigger_tasks"):
            for module_name, class_name in config.get(group, []):
                try:
                    module = importlib.import_module(module_name)
                    getattr(module, class_name)
                except Exception as exc:
                    failures.append(f"{group}: {module_name}.{class_name}: {exc}")
        self.assertEqual(failures, [], "\n".join(failures))


class TestStaticReferences(unittest.TestCase):
    """字符串/属性引用对不对——这类错误只有跑到那一步才会炸。"""

    def test_action_allowlist_exists_on_base_task(self):
        """流程里能调的 action，必须在 BaseGameTask 上真的有这个方法。

        ``dodge`` 曾经在白名单里但方法不存在：用户写到这一步才会 AttributeError。
        """
        from src.core.base_game_task import BaseGameTask
        from src.core.flow.executor import ACTION_ALLOWLIST

        missing = sorted(name for name in ACTION_ALLOWLIST if not hasattr(BaseGameTask, name))
        self.assertEqual(missing, [], f"白名单里有但 BaseGameTask 没有：{missing}")

    def test_feature_list_references_exist(self):
        """``FeatureList.xxx`` 的每一处**真实代码引用**都必须存在（docstring 不算）。"""
        import ast

        from src.data.feature_list import FeatureList

        absent: list[str] = []
        for path in SRC_ROOT.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):  # 语法错误由导入体检负责抓
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "FeatureList"
                    and not hasattr(FeatureList, node.attr)
                ):
                    absent.append(f"{path.relative_to(SRC_ROOT)}:{node.lineno} FeatureList.{node.attr}")
        self.assertEqual(absent, [], "\n".join(absent))

    def test_config_option_names_unique(self):
        """全局配置项的 key 不能重名（重名会互相覆盖，用户改了没生效）。"""
        import importlib

        from src.config import config

        keys: dict[str, str] = {}
        duplicates: list[str] = []
        modules = set()
        for group in ("configs", "global_configs"):
            for item in config.get(group, []) or []:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    modules.add((item[0], item[1]))
        for module_name, attr in modules:
            try:
                module = importlib.import_module(module_name)
                option = getattr(module, attr)
            except Exception:
                continue
            name = getattr(option, "name", "") or attr
            if name in keys:
                duplicates.append(f"{name}（{keys[name]} 与 {attr}）")
            keys[name] = attr
        self.assertEqual(duplicates, [], "\n".join(duplicates))


if __name__ == "__main__":
    unittest.main()
