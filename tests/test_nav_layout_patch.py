"""导航栏布局补丁的测试：顶部区并入滚动区、顺序不变、底部固定。

真实诉求：左侧一整列只留一个滚动条，且「开发工具 / 运行代码 / 通知 / 设置 / 关于」
固定在下半部分不跟着滚。
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app():
    try:
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])
    except Exception:
        return None


class FakePanel:
    """只保留补丁会用到的三个布局。"""

    def __init__(self, top, scroll, bottom):
        self.topLayout = top
        self.scrollLayout = scroll
        self.bottomLayout = bottom


class FakeNavigation:
    def __init__(self, panel):
        self.panel = panel


class FakeWindow:
    def __init__(self, panel):
        self.navigationInterface = FakeNavigation(panel)


class TestMergeTopIntoScroll(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _app() is None:
            raise unittest.SkipTest("Qt 离屏不可用")

    def _layouts(self):
        from PySide6.QtWidgets import QWidget
        from qfluentwidgets.components.navigation.navigation_panel import NavigationItemLayout

        top = NavigationItemLayout()
        scroll = NavigationItemLayout()
        bottom = NavigationItemLayout()
        top_items, scroll_items, bottom_items = [], [], []
        for name in ("全局配置", "流程与队列", "工具与诊断"):
            widget = QWidget()
            widget.setObjectName(name)
            top.addWidget(widget)
            top_items.append(widget)
        for name in ("Capture", "Triggers", "Tasks"):
            widget = QWidget()
            widget.setObjectName(name)
            scroll.addWidget(widget)
            scroll_items.append(widget)
        for name in ("Debug", "Run Code", "Notification", "Settings", "About"):
            widget = QWidget()
            widget.setObjectName(name)
            bottom.addWidget(widget)
            bottom_items.append(widget)
        return top, scroll, bottom, top_items, scroll_items, bottom_items

    def test_moves_top_items_to_front_of_scroll(self):
        from src.patches.nav_layout_patch import merge_top_into_scroll

        top, scroll, bottom, top_items, scroll_items, bottom_items = self._layouts()
        window = FakeWindow(FakePanel(top, scroll, bottom))

        moved = merge_top_into_scroll(window)

        self.assertEqual(moved, len(top_items))
        self.assertEqual(top.count(), 0, "顶部区应被搬空")
        self.assertEqual(bottom.count(), len(bottom_items), "底部区不该被改动")

        order = [
            scroll.itemAt(i).widget().objectName() for i in range(scroll.count())
        ]
        expected = [w.objectName() for w in top_items + scroll_items]
        self.assertEqual(order, expected, "顺序必须是「自定义页 → 框架页」")

    def test_missing_panel_is_safe(self):
        from src.patches.nav_layout_patch import merge_top_into_scroll

        class Broken:
            @property
            def navigationInterface(self):
                raise RuntimeError("没有导航栏")

        self.assertEqual(merge_top_into_scroll(Broken()), 0)

    def test_install_is_idempotent(self):
        from src.patches.nav_layout_patch import install_nav_layout_patch

        self.assertTrue(install_nav_layout_patch())
        self.assertTrue(install_nav_layout_patch())


if __name__ == "__main__":
    unittest.main()
