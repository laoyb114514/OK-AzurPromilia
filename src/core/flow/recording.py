"""把键鼠录制转换成流程步骤。

数据源是 ok-script 的 ``Recorder.events``（见 ``ok/ui/qt/tasks/RecordScript.py``）：

- ``{'type': 'mouse_down', 'x': 0.51, 'y': 0.44, 'button': 'left', 'time': 12.3}``
- ``{'type': 'mouse_up', 'x': …, 'time': …}``
- ``{'type': 'key_down', 'key': 'w', 'time': …}`` / ``{'type': 'key_up', …}``

录制是「原始事件流」，流程是「语义步骤」，转换时做三件事：

1. down/up 配对成「点击」「按键」，按住时长写进 ``duration``；
2. 相邻动作之间的空档补 ``wait`` 步骤（小于阈值不补，避免步骤爆炸）；
3. 无法表达成流程步骤的输入（右键、中键、滚轮等）**如实计入 skipped**，
   转换上限 400 步，超了就截断并标记 ``truncated``。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

MAX_RECORDING_STEPS = 400
DEFAULT_GAP_THRESHOLD = 0.05
DEFAULT_KEY_DURATION = 0.05
MIN_DURATION = 0.01

#: 不支持的鼠标按键（流程里的 click 只表达左键）
SUPPORTED_BUTTONS = ("left",)
UNSUPPORTED_EVENT_TYPES = ("mouse_move", "scroll", "wheel", "mouse_wheel")


@dataclass
class RecordingConversion:
    """转换结果：``steps`` 可直接构成流程的 ``steps`` 数组。"""

    steps: list[dict] = field(default_factory=list)
    skipped: int = 0
    truncated: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.steps)

    def to_flow(self, name: str = "录制流程", description: str = "") -> dict:
        return {
            "name": name,
            "description": description or f"由录制转换，共 {self.count} 步",
            "version": 1,
            "steps": self.steps,
        }

    def summary(self) -> str:
        text = f"转换 {self.count} 步"
        if self.skipped:
            text += f"，跳过 {self.skipped} 个无法表达的输入"
        if self.truncated:
            text += f"，超过上限已截断（{MAX_RECORDING_STEPS} 步）"
        return text


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _event_type(event: Mapping[str, Any]) -> str:
    return str(event.get("type", "") or "").strip().lower()


def convert_recording(
    events: Iterable[Mapping[str, Any]] | None,
    max_steps: int = MAX_RECORDING_STEPS,
    gap_threshold: float = DEFAULT_GAP_THRESHOLD,
    default_key_duration: float = DEFAULT_KEY_DURATION,
) -> RecordingConversion:
    """把录制事件流转换成流程步骤。"""
    result = RecordingConversion()
    if not events:
        result.notes.append("没有录制事件")
        return result

    ordered = sorted(
        (event for event in events if isinstance(event, Mapping)),
        key=lambda event: _to_float(event.get("time"), 0.0),
    )

    # 先把 down/up 配平成「动作时间线」，再补 wait
    timeline: list[tuple[float, float, dict]] = []  # (start, end, step)
    pending_keys: dict[str, float] = {}
    pending_mouse: dict[str, float] | None = None

    for event in ordered:
        kind = _event_type(event)
        if kind in UNSUPPORTED_EVENT_TYPES:
            result.skipped += 1
            result.notes.append(f"跳过不支持的事件: {kind}")
            continue

        if kind == "mouse_down":
            button = str(event.get("button", "left") or "left").lower()
            if button not in SUPPORTED_BUTTONS:
                result.skipped += 1
                result.notes.append(f"跳过不支持的鼠标按键: {button}")
                continue
            pending_mouse = {
                "x": _to_float(event.get("x"), 0.0),
                "y": _to_float(event.get("y"), 0.0),
                "time": _to_float(event.get("time"), 0.0),
            }
            continue

        if kind == "mouse_up":
            if pending_mouse is None:
                continue
            end = _to_float(event.get("time"), pending_mouse["time"])
            x = _to_float(event.get("x"), pending_mouse["x"])
            y = _to_float(event.get("y"), pending_mouse["y"])
            timeline.append(
                (
                    pending_mouse["time"],
                    end,
                    {
                        "type": "click",
                        "x": round(x, 4),
                        "y": round(y, 4),
                        "duration": round(max(0.0, end - pending_mouse["time"]), 3),
                    },
                )
            )
            pending_mouse = None
            continue

        if kind == "key_down":
            key = str(event.get("key", "") or "").strip()
            if not key:
                result.skipped += 1
                continue
            pending_keys[key] = _to_float(event.get("time"), 0.0)
            continue

        if kind == "key_up":
            key = str(event.get("key", "") or "").strip()
            if not key:
                result.skipped += 1
                continue
            start = pending_keys.pop(key, None)
            end = _to_float(event.get("time"), start or 0.0)
            if start is None:
                # 只有 up 没有 down（录制从中间开始），按一次短按处理
                start = end - default_key_duration
            duration = max(MIN_DURATION, end - start) if end > start else default_key_duration
            timeline.append(
                (
                    start,
                    end,
                    {"type": "key", "key": key, "duration": round(duration, 3)},
                )
            )
            continue

    # 录制结束时还按着的键：补一次短按，并说明
    for key, start in pending_keys.items():
        timeline.append(
            (
                start,
                start + default_key_duration,
                {"type": "key", "key": key, "duration": default_key_duration},
            )
        )
        result.notes.append(f"按键 {key} 没有抬起事件，按 {default_key_duration}s 短按处理")
    if pending_mouse is not None:
        timeline.append(
            (
                pending_mouse["time"],
                pending_mouse["time"],
                {
                    "type": "click",
                    "x": round(pending_mouse["x"], 4),
                    "y": round(pending_mouse["y"], 4),
                    "duration": 0.0,
                },
            )
        )
        result.notes.append("鼠标按下没有抬起事件，按零时长点击处理")

    timeline.sort(key=lambda item: item[0])

    steps: list[dict] = []
    previous_end: float | None = None
    for start, end, step in timeline:
        if previous_end is not None:
            gap = start - previous_end
            if gap_threshold > 0 and gap > gap_threshold:
                if len(steps) >= max_steps:
                    result.truncated = True
                    break
                steps.append({"type": "wait", "seconds": round(gap, 2)})
        if len(steps) >= max_steps:
            result.truncated = True
            break
        steps.append(step)
        previous_end = max(previous_end or end, end)

    result.steps = steps
    return result


def suggest_flow_name(events: Sequence[Mapping[str, Any]] | None, fallback: str = "录制流程") -> str:
    """按事件数量给个默认名字（UI 里当占位符用）。"""
    count = len(events) if events else 0
    return f"{fallback}（{count} 事件）" if count else fallback
