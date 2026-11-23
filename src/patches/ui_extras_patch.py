"""界面增强补丁：提醒线程 + 任务栏进度线程。

两个都是**守护线程 + 只读框架状态**，出任何问题都吞掉，不会影响任务执行：

- **提醒线程**：每 30 秒问一次 :class:`ReminderScheduler`，到点用框架的通知通道
  （``communicate.notification.emit``）发右下角提醒，不打断任务；
- **任务栏进度线程**：每 0.5 秒看一次 ``og.executor.current_task``，按历史平均用时
  推一次进度（封顶 97%），任务结束时撤掉进度条。拿不到窗口句柄就自动降级成空实现。

补丁挂在 ``MainWindow.__init__`` 之后启动线程：那时窗口已存在（拿得到句柄），
且框架还未开始跑任务。
"""

from __future__ import annotations

import contextlib
import threading
import time

from src.core.hotkeys import (
    HotkeyError,
    build_plan,
    find_action,
    load_hotkeys,
)
from src.core.reminders import ReminderScheduler
from src.core.reminders import load_settings as load_reminder_settings
from src.core.taskbar import (
    TaskbarProgress,
    compute_ratio,
    create_backend,
    default_run_log,
)
from src.core.taskbar import (
    load_enabled as load_taskbar_enabled,
)

POLL_INTERVAL = 30.0
TASKBAR_INTERVAL = 0.5
HOTKEY_INTERVAL = 0.05
WM_HOTKEY = 0x0312
_INSTALLED = False
_threads: dict[str, threading.Thread] = {}


def _notify(message: str, title: str) -> None:
    try:
        from ok import communicate

        communicate.notification.emit(message, title, False, True, False, None, None)
    except Exception:
        pass


def start_reminder_thread(stop_event: threading.Event | None = None) -> threading.Thread | None:
    """启动提醒线程（幂等）。"""
    global _threads
    existing = _threads.get("reminders")
    if existing is not None and existing.is_alive():
        return existing
    stop = stop_event or threading.Event()

    def loop():
        scheduler = ReminderScheduler(load_reminder_settings())
        last_settings = scheduler.settings
        while not stop.is_set():
            try:
                current = load_reminder_settings()
                if current != last_settings:
                    scheduler.settings = current
                    scheduler.reset()
                    last_settings = current
                for reminder in scheduler.poll():
                    _notify(reminder.message, reminder.title)
            except Exception:
                pass
            stop.wait(POLL_INTERVAL)

    thread = threading.Thread(target=loop, name="ok-ap-reminders", daemon=True)
    _threads["reminders"] = thread
    thread.start()
    return thread


def start_taskbar_thread(hwnd: int, stop_event: threading.Event | None = None) -> threading.Thread | None:
    """启动任务栏进度线程（幂等）；``hwnd`` 为 0 时线程直接退出。

    **后端必须在线程内部创建**：``ITaskbarList3`` 是单线程套间（STA）对象，
    在 A 线程 ``CoCreateInstance`` 出来、跑到 B 线程调用会被拒（或被 Qt 的套间
    搅成未定义行为）。所以 ``create_backend`` / ``CoInitialize`` 都放在 loop 里，
    线程退出时再 ``CoUninitialize``。
    """
    global _threads
    existing = _threads.get("taskbar")
    if existing is not None and existing.is_alive():
        return existing
    stop = stop_event or threading.Event()

    def loop():
        backend = create_backend(hwnd)
        progress = TaskbarProgress(backend)
        run_log = default_run_log()
        current = None
        started = 0.0
        try:
            while not stop.is_set():
                try:
                    if not load_taskbar_enabled():
                        if progress.last is not None:
                            progress.clear()
                        current = None
                        stop.wait(TASKBAR_INTERVAL)
                        continue
                    from ok import og

                    executor = getattr(og, "executor", None)
                    task = getattr(executor, "current_task", None) if executor is not None else None
                    if task is None:
                        if progress.last is not None:
                            progress.clear()
                        current = None
                    else:
                        if task is not current:
                            current = task
                            started = time.monotonic()
                        name = getattr(task, "name", None) or task.__class__.__name__
                        elapsed = time.monotonic() - started
                        ratio = compute_ratio(run_log, str(name), elapsed)
                        if ratio is not None:
                            progress.update(ratio)
                except Exception:
                    pass
                stop.wait(TASKBAR_INTERVAL)
        finally:
            with contextlib.suppress(Exception):
                progress.clear()
            with contextlib.suppress(Exception):
                from src.core.taskbar import uninitialize_backend

                uninitialize_backend(backend)

    thread = threading.Thread(target=loop, name="ok-ap-taskbar", daemon=True)
    _threads["taskbar"] = thread
    thread.start()
    return thread


def stop_all() -> None:
    for name, thread in list(_threads.items()):
        _threads.pop(name, None)
        with contextlib.suppress(Exception):
            thread.join(timeout=0.1)


# ── 快捷键 ───────────────────────────────────────────────
def perform_action(action: str) -> bool:
    """执行一个快捷键动作；拿不到执行器就安静失败。"""
    try:
        from ok import og

        executor = getattr(og, "executor", None)
        if action == "pause":
            if executor is None:
                return False
            if getattr(executor, "paused", False):
                executor.start()
            else:
                executor.pause()
            return True
        if action == "stop":
            if executor is None:
                return False
            executor.stop_current_task()
            return True
        if action == "toggle_uid_mask":
            from src.core.privacy import load_config, save_config

            config = load_config()
            save_config(
                type(config)(
                    enabled=not config.enabled,
                    only_foreground=config.only_foreground,
                    blocks=config.blocks,
                )
            )
            return True
    except Exception:
        return False
    return False


def start_hotkey_thread(stop_event: threading.Event | None = None) -> threading.Thread | None:
    """注册全局快捷键并跑一个消息循环（幂等）。"""
    global _threads
    existing = _threads.get("hotkeys")
    if existing is not None and existing.is_alive():
        return existing
    try:
        plan = build_plan(load_hotkeys())
    except HotkeyError:
        return None
    stop = stop_event or threading.Event()

    def loop():
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
        except Exception:
            return
        registered = []
        for entry in plan:
            try:
                if user32.RegisterHotKey(None, entry["id"], entry["modifiers"], entry["vk"]):
                    registered.append(entry["id"])
            except Exception:
                pass
        message = wintypes.MSG()
        try:
            while not stop.is_set():
                try:
                    if user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                        if message.message == WM_HOTKEY:
                            action = find_action(plan, int(message.wParam))
                            if action:
                                perform_action(action)
                        continue
                except Exception:
                    pass
                time.sleep(HOTKEY_INTERVAL)
        finally:
            for hotkey_id in registered:
                with contextlib.suppress(Exception):
                    user32.UnregisterHotKey(None, hotkey_id)

    thread = threading.Thread(target=loop, name="ok-ap-hotkeys", daemon=True)
    _threads["hotkeys"] = thread
    thread.start()
    return thread


def install_ui_extras_patch() -> bool:
    """挂在 MainWindow.__init__ 上：窗口创建后启动线程与 HUD。"""
    global _INSTALLED
    if _INSTALLED:
        return True
    try:
        from ok.ui.qt.MainWindow import MainWindow
    except Exception:
        return False

    original_init = MainWindow.__init__

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            hwnd = int(self.winId() or 0)
        except Exception:
            hwnd = 0
        try:
            start_reminder_thread()
            start_taskbar_thread(hwnd)
            start_hotkey_thread()
        except Exception:
            pass
        _attach_hud(self)

    MainWindow.__init__ = __init__
    _INSTALLED = True
    return True


def _attach_hud(main_window) -> object | None:
    """按设置创建 HUD，并在退出时一并关掉（不抢焦点、失败不影响启动）。"""
    try:
        from src.core.hud import load_settings

        if not load_settings().enabled:
            return None
        from src.gui.hud_window import HudWindow

        hud = HudWindow()
        main_window._ok_ap_hud = hud  # 防止被 GC
        app = getattr(main_window, "app", None)
        if app is not None:
            with contextlib.suppress(Exception):
                app.aboutToQuit.connect(hud.close)
        return hud
    except Exception:
        return None
