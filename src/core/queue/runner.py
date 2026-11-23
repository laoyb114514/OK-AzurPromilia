"""队列执行器。

调用方注入 ``resolver(item) -> callable(budget_seconds) -> bool``：

```python
def resolver(item):
    if item.kind == "flow":
        return lambda budget: run_flow(item.ref, budget)
    if item.kind == "task":
        return lambda budget: run_task(item.ref)
    return None   # 未知类型 → 记失败
```

这样队列不知道任务怎么跑，只知道「这一项有没有成功、花了多久」。
"轮椅方案"（``scheme``）在批次 D 才落地，这里先按未知项处理。
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from src.core.queue.model import QueueItem, TaskQueue

Resolver = Callable[[QueueItem], Callable[[float | None], bool] | None]


@dataclass
class QueueItemResult:
    item: QueueItem
    ok: bool = False
    skipped: bool = False
    elapsed: float = 0.0
    error: str | None = None
    budget_exceeded: bool = False

    def summary(self) -> str:
        if self.skipped:
            return f"跳过 {self.item.label}"
        state = "完成" if self.ok else "失败"
        text = f"{state} {self.item.label}（{self.elapsed:.1f}s）"
        if self.budget_exceeded:
            text += "，超出预算"
        if self.error:
            text += f"：{self.error}"
        return text


@dataclass
class QueueRunResult:
    ok: bool = False
    results: list[QueueItemResult] = field(default_factory=list)
    elapsed: float = 0.0

    @property
    def completed(self) -> int:
        return sum(1 for result in self.results if result.ok and not result.skipped)

    @property
    def failed(self) -> int:
        return sum(1 for result in self.results if not result.ok and not result.skipped)

    def summary(self) -> str:
        state = "队列完成" if self.ok else "队列中断"
        return (
            f"{state}：成功 {self.completed} 项，失败 {self.failed} 项，"
            f"用时 {self.elapsed:.1f}s"
        )


class QueueRunner:
    """顺序执行队列项，按 ``stop_on_failure`` 决定失败后是否继续。"""

    def __init__(
        self,
        queue: TaskQueue,
        resolver: Resolver,
        log: Callable[[str], None] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self.queue = queue
        self.resolver = resolver
        self._log = log
        self._clock = clock or time.monotonic

    def run(self) -> QueueRunResult:
        result = QueueRunResult(ok=True)
        started = self._clock()

        for item in self.queue.items:
            if not item.enabled:
                result.results.append(QueueItemResult(item=item, skipped=True))
                self._info(f"跳过未启用项 {item.label}")
                continue

            runner = self._resolve(item, result)
            if runner is None:
                continue

            budget = item.budget_seconds
            item_started = self._clock()
            error = None
            ok = False
            try:
                ok = bool(runner(budget))
            except Exception as exc:  # 单项异常不该炸掉整条队列
                ok = False
                error = str(exc)
            elapsed = self._clock() - item_started
            budget_exceeded = budget is not None and elapsed > budget

            item_result = QueueItemResult(
                item=item,
                ok=ok,
                elapsed=elapsed,
                error=error,
                budget_exceeded=budget_exceeded,
            )
            result.results.append(item_result)
            self._info(item_result.summary())

            if not ok:
                result.ok = False
                if self.queue.stop_on_failure:
                    self._info("队列设置为失败即停，剩余项不再执行")
                    break

        result.elapsed = self._clock() - started
        return result

    def _resolve(self, item: QueueItem, result: QueueRunResult):
        try:
            runner = self.resolver(item)
        except Exception as exc:
            runner = None
            reason = f"解析队列项失败：{exc}"
        else:
            reason = f"找不到队列项的实现：{item.kind}:{item.ref}"

        if runner is None:
            result.ok = False
            result.results.append(QueueItemResult(item=item, ok=False, error=reason))
            self._info(reason)
            return None
        return runner

    def _info(self, message: str) -> None:
        if self._log:
            with contextlib.suppress(Exception):
                self._log(message)
