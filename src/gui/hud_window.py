"""HUD 悬浮条：置顶小条，显示「状态 + 任务 + 进度 + 预计剩余」，带暂停/继续与停止。

要点：

- 只在**有任务在跑**时显示，任务结束自动隐藏（不占屏幕）；
- ``WindowStaysOnTopHint | Tool | FramelessWindowHint``，并且
  ``WindowDoesNotAcceptFocus`` —— 不抢游戏焦点、不打断输入；
- 位置按屏幕可用区域**底部居中**（:func:`src.core.hud.hud_position`），
  Qt 用的是逻辑像素，所以 150% 缩放屏也不会错位；
- 关闭方式：在「界面与提醒」页关掉 HUD，或任务结束自动隐藏。

状态每秒刷新一次，数据来自 `og.executor.current_task` 与 `runs.jsonl` 的历史均值。
"""

from __future__ import annotations

import contextlib
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from src.core.hud import (
    DEFAULT_HEIGHT,
    DEFAULT_MIN_WIDTH,
    build_hud_text,
    hud_position,
    load_settings,
    remaining_seconds,
)
from src.core.ledger import RunLog

REFRESH_MS = 1000
HUD_STYLE = """
QWidget#hudRoot {
    background: rgba(20, 24, 32, 210);
    border: 1px solid rgba(120, 140, 170, 160);
    border-radius: 8px;
}
QLabel#hudText { color: #e8edf6; font-size: 12px; }
QPushButton#hudButton {
    color: #e8edf6; background: rgba(70, 90, 120, 180);
    border: none; border-radius: 4px; padding: 2px 8px; font-size: 12px;
}
QPushButton#hudButton:hover { background: rgba(90, 115, 150, 220); }
"""


def _tr(text: str) -> str:
    try:
        from ok import og

        app = getattr(og, "app", None)
        if app is not None:
            return app.tr(text)
    except Exception:
        pass
    return text


class HudWindow(QWidget):
    """置顶状态条。"""

    def __init__(self, run_log: RunLog | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("hudRoot")
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(HUD_STYLE)
        self.setMinimumWidth(DEFAULT_MIN_WIDTH)
        self.setFixedHeight(DEFAULT_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 8, 4)
        layout.setSpacing(8)

        self.text_label = QLabel("")
        self.text_label.setObjectName("hudText")
        layout.addWidget(self.text_label, 1)

        self.pause_button = QPushButton(_tr("暂停"))
        self.pause_button.setObjectName("hudButton")
        self.pause_button.clicked.connect(self._toggle_pause)
        layout.addWidget(self.pause_button)

        self.stop_button = QPushButton(_tr("停止"))
        self.stop_button.setObjectName("hudButton")
        self.stop_button.clicked.connect(self._stop)
        layout.addWidget(self.stop_button)

        self.run_log = run_log or RunLog()
        self._task = None
        self._started = 0.0
        self._settings = load_settings()

        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.hide()

    # ── 刷新 ─────────────────────────────────────────────
    def refresh(self):
        """读执行器状态并更新文案；空闲时自动隐藏。"""
        try:
            self._settings = load_settings()
            if not self._settings.enabled:
                self.hide()
                return
            task = self._current_task()
            if task is None:
                self._task = None
                self.hide()
                return

            if task is not self._task:
                self._task = task
                self._started = time.monotonic()

            name = str(getattr(task, "name", None) or task.__class__.__name__)
            paused = bool(getattr(task, "paused", False))
            estimate = self.run_log.estimate_seconds(name)
            elapsed = max(0.0, time.monotonic() - self._started)
            progress = None
            remaining = None
            if estimate > 0:
                from src.core.taskbar import compute_ratio

                progress = compute_ratio(self.run_log, name, elapsed)
                remaining = remaining_seconds(estimate, elapsed)

            text = build_hud_text(
                task_name=name,
                paused=paused,
                progress=progress,
                remaining_seconds=remaining,
                show_remaining=self._settings.show_remaining,
            )
            if not text:
                self.hide()
                return
            self.text_label.setText(text)
            self.pause_button.setText(_tr("继续") if paused else _tr("暂停"))
            self._place()
            if not self.isVisible():
                self.show()
        except Exception:
            self.hide()

    def _current_task(self):
        try:
            from ok import og

            executor = getattr(og, "executor", None)
            return getattr(executor, "current_task", None) if executor is not None else None
        except Exception:
            return None

    def _place(self):
        """按屏幕可用区域底部居中；多屏时用主屏。"""
        try:
            screen = QGuiApplication.primaryScreen()
            area = screen.availableGeometry()
            self.adjustSize()
            x, y = hud_position(
                area.x(),
                area.y(),
                area.width(),
                area.height(),
                self.width(),
                self.height(),
                self._settings.margin,
            )
            self.move(x, y)
        except Exception:
            pass

    # ── 动作 ─────────────────────────────────────────────
    def _toggle_pause(self):
        try:
            from ok import og

            executor = getattr(og, "executor", None)
            if executor is None:
                return
            if getattr(executor, "paused", False):
                executor.start()
            else:
                executor.pause()
            self.refresh()
        except Exception:
            pass

    def _stop(self):
        try:
            from ok import og

            executor = getattr(og, "executor", None)
            if executor is not None:
                executor.stop_current_task()
            self.refresh()
        except Exception:
            pass

    def closeEvent(self, event):
        with contextlib.suppress(Exception):
            self._timer.stop()
        super().closeEvent(event)
