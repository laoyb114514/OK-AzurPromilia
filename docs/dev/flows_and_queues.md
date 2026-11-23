# 流程、队列与配置档（批次 B）

三层东西，互相独立又常一起用：

- **流程（flow）**：JSON 描述的步骤树，比键鼠录制更「可编程」，能嵌套循环和条件；
- **队列（queue）**：把「流程 / 一次性任务 / 触发任务」串成一条顺序队列，可以给每项设分钟预算；
- **配置档（profile）**：把 `configs/` 打成一个命名快照，切场景前一键换回来。

执行入口统一是任务 **「流程 / 队列」**（`src/tasks/onetime/flow_task.py`），
编辑与校验在 **「流程与队列」** 页（`src/gui/flow_tab.py`）。

## 1. 流程 JSON

文件位置 `configs/flows/<名字>.json`。

```json
{
  "name": "每日刷图",
  "description": "可选的说明",
  "version": 1,
  "steps": [
    {"type": "wait_template", "template": "main_ui", "timeout": 10},
    {"type": "click", "template": "commission_icon"},
    {"type": "wait", "seconds": 1.0},
    {"type": "loop", "times": 3, "steps": [
      {"type": "click", "x": 0.5, "y": 0.8},
      {"type": "wait_template", "template": "result_panel", "expect": "disappear", "settle": 0.5}
    ]},
    {"type": "if", "template": "confirm_button",
     "steps": [{"type": "action", "action": "back"}],
     "else": [{"type": "wait", "seconds": 0.2}]}
  ]
}
```

### 步骤类型

| type | 必填 | 可选 | 说明 |
|------|------|------|------|
| `move` | `direction` 或 `dx`/`dy` | `duration` | `direction` 是 `w/a/s/d` 组合（`wd` 表示右上）；`dx/dy` 是相对鼠标位移（转视角） |
| `click` | `x`+`y` 或 `template` | `times`、`duration` | 比例坐标 0..1；给了 `template` 就等它出现并点它的中心；`duration` 是点击后等待 |
| `action` | `action` | `args` | 调用白名单里的任务方法，`args` 原样作为关键字参数 |
| `key` | `key` | `duration`、`times` | `duration` 是按住时长 |
| `wait` | `seconds` | — | 纯等待（暂停感知） |
| `wait_template` | `template` | `expect`、`settle`、`threshold`、`timeout` | `expect` = `appear`（默认）/ `disappear`；`settle` = 状态需连续保持的秒数 |
| `loop` | `times` 或 `until_template` 或 `until_not_template` | `max`、`timeout` | `times` 固定次数；`until_*` 是「直到出现 / 消失」，`max` 是安全上限 |
| `if` | `template` | `steps`、`else`、`threshold` | 命中走 `steps`，否则走 `else` |

公共字段：`timeout`（这一步的等待上限）、`comment`（备注）。

### 硬限制

| 限制 | 值 | 行为 |
|------|----|------|
| 总步数 | 500 | 超过直接**校验失败**，不会「尽力执行」 |
| 单层循环次数 | 1000 | `times` / `max` 必须在 1..1000 |
| 嵌套深度 | 4 | 超过即校验失败 |

另外：`type` 不认识、字段名拼错（例如把 `seconds` 写成 `secs`）、
比例坐标超范围、`loop` 同时给了两个条件 —— 都会被 `validate_flow()` 报成 error，
执行前先校验，有 error 就不跑。

### 执行语义

- **断点续跑**：每完成一个**顶层**步骤写一次进度到 `configs/flow_progress/<流程名>.json`；
  任务里勾「从断点继续」就从下一个顶层步骤开始。顶层步骤内部的循环/条件会**重新执行**，
  因为半途状态无法可靠重建。
- **时间预算**：`FlowExecutor(budget_seconds=…)` 在每一步之前检查，超了就抛 `FlowError`，
  所以流程是**真的会被预算打断**的。
- **失败策略**：任务配置「失败后继续」= `continue_on_error`；失败项会记进
  `FlowRunResult.failed`，最后给出 `summary()`。
- 全部跑完会清掉断点，避免下次误跳过。

### 动作白名单

`{"type": "action", "action": "…"}` 只能调用
`src/core/flow/executor.py` 的 `ACTION_ALLOWLIST`（`back` / `ensure_main` / `dodge` /
`press_combat_key` / `click_relative` / `next_frame` / `sleep` / `wait_ui_stable` …）。

流程文件是用户可编辑的 JSON，**不能让任意字符串变成任意方法调用**。
需要新动作就往白名单里加一条，并在测试里补一个用例。

## 2. 录制转流程

`src/core/flow/recording.py` 的 `convert_recording(events)`：

- `mouse_down`/`mouse_up` 配对成 `click`，按住时长写进 `duration`；
- `key_down`/`key_up` 配对成 `key`，同样保留按住时长；
- 相邻动作之间超过 `gap_threshold`（默认 0.05s）的空档补一个 `wait` 步骤；
- **无法表达的输入如实计入 `skipped`**：右键、中键、滚轮、鼠标移动；
- 上限 **400 步**，超了截断并标记 `truncated`；
- 只按过没抬起的键、按下没抬起的鼠标，按短按/零时长处理并在 `notes` 里说明。

「流程与队列」页的「从录制 JSON 生成」接受两种格式：裸事件数组，或 `{"events": [...]}`。

## 3. 任务队列

文件位置 `configs/queues/<名字>.json`。

```json
{
  "name": "早上",
  "stop_on_failure": true,
  "items": [
    {"kind": "task", "ref": "DailyTask", "budget_minutes": 20, "name": "一条龙"},
    {"kind": "flow", "ref": "每日刷图", "budget_minutes": 10},
    {"kind": "scheme", "ref": "轮椅-深渊", "budget_minutes": 5}
  ]
}
```

| 字段 | 说明 |
|------|------|
| `kind` | `flow` / `task` / `assist` / `scheme` |
| `ref` | 流程名，或任务**类名**（也接受任务显示名） |
| `budget_minutes` | 这一项的预算；0 或缺省 = 不限 |
| `enabled` | 缺省 true；false 表示跳过（仍保留在队列里） |
| `stop_on_failure` | 队列级：失败即停（true）/ 失败后继续（false） |

`QueueRunner` 不知道任务怎么跑，靠调用方注入
`resolver(item) -> callable(budget_seconds) -> bool`，所以队列本身可以离线测试。

**预算的诚实边界**：流程能被预算真的打断；任务类（`DailyTask` 等）没法中途打断，
超预算只在结果里标 `budget_exceeded`，不会谎称已经停止。

队列项类型映射（`FlowTask._queue_resolver`）：

- `flow` → 作为子流程执行（预算透传）；
- `task` → 在 `executor.onetime_tasks` 里按类名/显示名找实例并调 `run()`
  （`run()` 返回 `False` 才算失败，与 `DailyTaskRunner` 的约定一致）；
- `assist` → 在 `executor.trigger_tasks` 里找实例并调一次 `run()`。
  **持续辅助**应在触发任务列表里启用，不要指望队列「持续」某件事；
- `scheme`（轮椅方案）→ 批次 D 提供，当前按未知项记失败。

## 4. 配置档

`src/core/profile_store.py`，目录 `configs/profiles/`。

```text
configs/profiles/
├── 工作/
│   ├── profile.json      # 名字、保存时间、文件清单（相对路径 + 大小）
│   └── files/…           # 与 configs/ 相对路径一致的快照
└── .backup_20261124_011530/   # 应用配置档前的自动备份
```

- **快照范围** = `configs/` 下除 `profiles/` 之外的全部文件（递归，含 `queues/`、`flows/`）；
- **应用前自动备份**当前的 `configs/`；
- 应用时只覆盖档里存在的文件，**不删除档里没有的文件**（避免误删），
  返回值 `extra` 如实报告「当前有、档里没有」的文件数；
- 名字校验拒绝空、`.` 开头、以及 `\/:*?"<>|` —— 防止路径逃逸；
- 全部写盘都是 `.tmp` + `os.replace`。

## 5. 任务「流程 / 队列」

`src/tasks/onetime/flow_task.py`，注册在 `src/config.py` 的 `onetime_tasks`，
并声明 `support_schedule_task = True`（可被 Windows 计划任务触发）。

| 配置项 | 默认 | 说明 |
|--------|------|------|
| `任务类型` | 执行流程 | 执行流程 / 执行队列 |
| `流程文件` | （空） | `configs/flows` 下的名字（不带 `.json`） |
| `队列文件` | （空） | `configs/queues` 下的名字 |
| `从断点继续` | True | 只对流程生效 |
| `失败后继续` | False | 流程单步失败后是否继续 |
| `预算(分钟)` | 30 | 0 = 不限 |

命令行也能跑：`ok-ap.exe -t 5`（序号按 `onetime_tasks` 顺序，`FlowTask` 目前是第 5 个）。

## 6. 「流程与队列」页

`src/gui/flow_tab.py`（懒加载）：

- **流程**：下拉选文件 → 预览结构化步骤树（含嵌套缩进）→ 「校验」列出全部问题 →
  导入 JSON / 从录制 JSON 生成 / 删除 / 打开目录；下方显示断点进度。
- **任务队列**：下拉选队列 → 预览每项的类型/预算/是否禁用 → 校验 / 新建空模板 / 删除。
- **配置档**：下拉选档 → 保存当前配置 / 应用 / 删除；状态行说明备份位置。

**这一页不发键鼠**：执行统一走任务体系（暂停、停止、调度、账号上下文都在框架里），
避免界面线程和正在跑的任务抢输入。

## 7. 测试覆盖

| 测试 | 覆盖 |
|------|------|
| `tests/test_flow.py` | 解析/校验（含 500 步、4 层、1000 次、字段拼错、比例越界）、全部步骤类型、循环/条件、失败策略、预算、断点存取与续跑 |
| `tests/test_flow_recording.py` | down/up 配对、空档补 wait、跳过右键/滚轮、未抬起处理、400 步截断 |
| `tests/test_task_queue.py` | 模型校验、文件存取、执行顺序、失败即停/继续、禁用项、未知项、预算标记 |
| `tests/test_profile_store.py` | 快照、应用前备份、不删档外文件、名字校验、损坏元信息容错 |

```bash
uv run python -m unittest discover -s tests
```
