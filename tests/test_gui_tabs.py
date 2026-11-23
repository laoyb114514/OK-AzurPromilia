"""GUI 页冒烟测试：离屏把每个自定义 Tab 真正构建一遍。

静态检查只能确认「名字存在」，确认不了「这一段构造代码能不能跑通」——
`QTableWidget.SelectionBehavior.SelectRows` 这种写错了，要等用户点开那一页才炸。
这里用 Qt 的 offscreen 平台把 9 个页面都构造 + build 一次。

⚠️ 需要 ``QT_QPA_PLATFORM=offscreen``：不弹窗、不需要显示器，CI 也能跑。
"""

import importlib
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _make_app():
    """离屏 QApplication；Qt 不可用就返回 None（测试会 skip）。"""
    try:
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])
    except Exception:
        return None


class _StubApp:
    """``og.app`` 的最小替身。

    真实运行时 ``og.app`` 一定存在（页面是框架在 ``OK`` 初始化后创建的），这里补一个
    只带 ``tr()`` 的替身，是为了让页面能在没有完整应用的情况下被构建一次。
    ``AccountConfigTab`` 直接用 ``og.app.tr(...)``，所以没有它会构造失败。
    """

    def tr(self, text: str) -> str:
        return text

    def get_config(self, *args, **kwargs):
        return {}


class TestGuiTabs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = _make_app()
        if cls.qapp is None:
            raise unittest.SkipTest("Qt 离屏不可用")

    def test_every_tab_builds(self):
        from src.config import config

        pairs = config.get("custom_tabs", []) or []
        self.assertGreaterEqual(len(pairs), 9)

        failures = []
        with mock.patch("ok.og.app", _StubApp(), create=True):
            for module_name, class_name in pairs:
                try:
                    module = importlib.import_module(module_name)
                    tab = getattr(module, class_name)()
                    build = getattr(tab, "_build", None)
                    if callable(build):
                        build()
                except Exception as exc:
                    failures.append(f"{class_name}: {type(exc).__name__}: {exc}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_tab_metadata_is_sane(self):
        """每个页的 name / icon / position 都要能取到（导航栏靠它们）。"""
        from src.config import config

        problems = []
        with mock.patch("ok.og.app", _StubApp(), create=True):
            for module_name, class_name in config.get("custom_tabs", []) or []:
                try:
                    module = importlib.import_module(module_name)
                    tab = getattr(module, class_name)()
                    name = tab.name
                    icon = tab.icon
                except Exception as exc:
                    problems.append(f"{class_name}: {type(exc).__name__}: {exc}")
                    continue
                if not isinstance(name, str) or not name.strip():
                    problems.append(f"{class_name}: name 为空")
                if icon is None:
                    problems.append(f"{class_name}: icon 为 None")
        self.assertEqual(problems, [], "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
