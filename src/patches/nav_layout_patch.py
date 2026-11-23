"""导航栏布局补丁：左侧一整列只留一个滚动条，底部 5 项固定。

现状（qfluentwidgets + ok-script 2.0.6）：侧栏分三个区

- ``topLayout``：本项目 9 个自定义页（我们用 ``NavigationItemPosition.TOP``）——**不滚动**；
- ``scrollArea``：框架自己的「Capture / Triggers / Tasks / Templates / Schedule」——**带滚动条**；
- ``bottomLayout``：Debug / Run Code / Notification / Settings / About——固定。

于是左侧看着是「9 项不动 + 下面另起一段带滚动条的列表」，滚动条出现在列表中间，
很难看出整列还能滚。

这个补丁在 ``MainWindow.__init__`` 之后把 ``topLayout`` 里的项**按原顺序搬到滚动区最前面**：

- 视觉顺序不变（自定义页仍在最上面，然后是 Capture / Triggers / Tasks…）；
- 整列共用一个滚动条（滚动区现在包含除底部 5 项以外的全部项）；
- 底部 5 项保持固定（框架本来就是 ``NavigationItemPosition.BOTTOM``）。
"""

from __future__ import annotations

import contextlib

_INSTALLED = False


def merge_top_into_scroll(main_window) -> int:
    """把侧栏顶部区里的项搬进滚动区（插到最前面），返回搬了几项。

    拿不到导航面板就返回 0，不抛异常（补丁不该影响启动）。
    """
    try:
        panel = main_window.navigationInterface.panel
        top_layout = panel.topLayout
        scroll_layout = panel.scrollLayout
    except Exception:
        return 0

    moved = 0
    index = 0
    try:
        while top_layout.count():
            item = top_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is None:
                continue
            scroll_layout.insertWidget(index, widget)
            index += 1
            moved += 1
    except Exception:
        return moved
    return moved


def install_nav_layout_patch() -> bool:
    """包一层 ``MainWindow.__init__``：窗口建好后合并布局（幂等）。"""
    global _INSTALLED
    if _INSTALLED:
        return True
    try:
        from ok.ui.qt.MainWindow import MainWindow
    except Exception:
        return False

    original_init = MainWindow.__init__
    if getattr(original_init, "_ok_ap_nav_layout", False):
        _INSTALLED = True
        return True

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        with contextlib.suppress(Exception):
            merge_top_into_scroll(self)

    __init__._ok_ap_nav_layout = True
    MainWindow.__init__ = __init__
    _INSTALLED = True
    return True
