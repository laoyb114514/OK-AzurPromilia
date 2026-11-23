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


if __name__ == "__main__":
    unittest.main()
