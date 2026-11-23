"""「一条龙顺序」页：拖动调整「一键日常」里各子任务的执行顺序与开关。

拖动是 ``QListWidget`` 的内部移动（框架本身没有任何 drag&drop 控件）；
保存时把顺序写回 ``DailyTask`` 的 ``任务顺序`` 配置，把勾选状态写回各子任务的开关键。
任务正在运行时拒绝写入，避免和运行中的编排抢配置。
"""

from __future__ import annotations

from ok.gui.widget.CustomTab import CustomTab
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    NavigationItemPosition,
    PrimaryPushButton,
    PushButton,
)

from src.tasks.daily.order import split_order
from src.tasks.onetime.daily_task import DEFAULT_ORDER, DailyTask

PREBUILD_DELAY_MS = 3000
LIST_HEIGHT = 200


class DailyOrderTab(CustomTab):
    """拖动排序 + 开关编辑。"""

    def __init__(self):
        super().__init__()
        self._built = False
        self._build_scheduled = False
        self._task = None
        self.list_widget: QListWidget | None = None
        self.status_label: BodyLabel | None = None
        QTimer.singleShot(PREBUILD_DELAY_MS, self, self._schedule_build)

    # ── CustomTab 元信息 ─────────────────────────────────
    @property
    def name(self):
        return self.tr("一条龙顺序")

    @property
    def position(self):
        return NavigationItemPosition.TOP

    @property
    def add_after_default_tabs(self):
        return True

    @property
    def icon(self):
        return FluentIcon.TILES

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_build()
        if self._built:
            self.reload()

    # ── 构建 ─────────────────────────────────────────────
    def _schedule_build(self):
        if self._build_scheduled:
            return
        self._build_scheduled = True
        QTimer.singleShot(0, self, self._build)

    def _build(self):
        if self._built:
            return
        self._built = True
        card = QWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.MoveAction)
        self.list_widget.setFixedHeight(LIST_HEIGHT)
        layout.addWidget(self.list_widget)

        row = QHBoxLayout()
        row.setSpacing(6)
        for text, icon, slot in (
            (self.tr("刷新"), FluentIcon.SYNC, self.reload),
            (self.tr("上移"), FluentIcon.UP, lambda: self._move(-1)),
            (self.tr("下移"), FluentIcon.DOWN, lambda: self._move(1)),
            (self.tr("恢复默认"), FluentIcon.HISTORY, self._restore_default),
        ):
            button = PushButton(icon, text)
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch(1)
        save = PrimaryPushButton(FluentIcon.SAVE, self.tr("保存顺序与开关"))
        save.clicked.connect(self._save)
        row.addWidget(save)
        layout.addLayout(row)

        self.status_label = BodyLabel(
            self.tr("拖动任务调整顺序；勾选框控制该项是否执行。任务运行中不能保存。")
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.add_card(self.tr("一键日常的执行顺序"), card)

    # ── 数据 ─────────────────────────────────────────────
    def _resolve_task(self):
        executor = getattr(self, "executor", None)
        getter = getattr(executor, "get_task_by_class", None)
        if callable(getter):
            try:
                return getter(DailyTask)
            except Exception:
                return None
        return None

    def reload(self):
        if not self._built:
            return
        self._task = self._resolve_task()
        if self._task is None:
            self._set_status(self.tr("没有找到「一键日常」任务，无法编辑顺序"))
            self.list_widget.clear()
            return

        config = getattr(self._task, "config", {}) or {}
        default_order = split_order(config.get("任务顺序") or DEFAULT_ORDER)
        known = set(self._known_names())
        names = [name for name in default_order if name in known]
        for name in self._known_names():
            if name not in names:
                names.append(name)

        self.list_widget.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            item.setCheckState(Qt.Checked if config.get(name, True) else Qt.Unchecked)
            self.list_widget.addItem(item)
        self._set_status(self.tr("已载入当前顺序；拖动或勾选后点「保存」"))

    def _known_names(self) -> list[str]:
        """从默认顺序里取全部已知任务名（顺序串里可能有历史遗留项）。"""
        return split_order(DEFAULT_ORDER)

    def _current_names(self) -> list[str]:
        if self.list_widget is None:
            return []
        return [self.list_widget.item(index).text() for index in range(self.list_widget.count())]

    def _move(self, offset: int):
        if self.list_widget is None:
            return
        row = self.list_widget.currentRow()
        if row < 0:
            return
        target = max(0, min(self.list_widget.count() - 1, row + offset))
        if target == row:
            return
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(target, item)
        self.list_widget.setCurrentRow(target)

    def _restore_default(self):
        if self.list_widget is None:
            return
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.text() in split_order(DEFAULT_ORDER):
                item.setCheckState(Qt.Checked)
        self.reload()
        self._set_status(self.tr("已恢复默认顺序（记得点保存）"))

    def _save(self):
        task = self._task or self._resolve_task()
        if task is None:
            self._notify(self.tr("没有找到「一键日常」任务"), error=True)
            return
        if getattr(task, "running", False):
            self._notify(self.tr("任务正在运行，先停止再改顺序"), error=True)
            return

        names = self._current_names()
        if not names:
            self._notify(self.tr("列表是空的"), error=True)
            return
        try:
            task.config["任务顺序"] = ",".join(names)
            for index in range(self.list_widget.count()):
                item = self.list_widget.item(index)
                task.config[item.text()] = item.checkState() == Qt.Checked
        except Exception as exc:
            self._notify(self.tr("保存失败：{error}").format(error=exc), error=True)
            return
        self._set_status(self.tr("已保存：{order}").format(order=" → ".join(names)))
        self._notify(self.tr("顺序已保存"))

    # ── 工具 ─────────────────────────────────────────────
    def _set_status(self, text: str):
        if self.status_label is not None:
            self.status_label.setText(text)

    def _notify(self, message: str, error: bool = False):
        try:
            window = self.window()
            factory = InfoBar.error if error else InfoBar.success
            factory(
                title=self.tr("一条龙顺序"),
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=5000 if error else 3000,
                parent=window,
            )
        except Exception:
            self.logger.info(message)
