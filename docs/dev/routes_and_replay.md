# 一条龙顺序、导航路线与轮椅方案（批次 D）

三块都是「把固定流程复用起来」的工具，共同点是**数据是 JSON、执行走任务体系**：

| 功能 | 数据位置 | 执行入口 |
|------|----------|----------|
| 一条龙顺序 | `configs/DailyTask.json` 的 `任务顺序` | 「一键日常」任务 |
| 导航路线 | `configs/routes/<名字>.json` | 「导航路线」任务 |
| 轮椅方案 | `configs/schemes/<名字>.json`，可导出成流程 | 「流程 / 队列」任务（跑导出的流程） |

## 1. 一条龙顺序

### 配置项

`一键日常` 新增 `任务顺序`（逗号分隔，`，`/`、`/`;` 也认）：

```text
家园每日,委托每日,每日收菜
```

排序规则（`src/tasks/daily/order.py`）：

- 只认已知任务名，**未知项忽略**（换版本删任务不会崩）；
- 配了但漏掉的任务**追加在末尾**并保持原有相对顺序 —— 新增任务不会因为老用户的
  顺序串里没有它就被静默跳过；
- 空串退回代码里的默认顺序。

默认顺序仍是「家园 → 委托 → 收菜」：委托战斗会推进日常/周常活跃与大月卡进度，
收菜殿后能把战斗产生的进度一并领走。

### 「一条龙顺序」页

`src/gui/daily_order_tab.py`：

- 列表**可拖动排序**（`QListWidget` 的 InternalMove；框架本身没有任何 drag&drop 控件）；
- 勾选框控制该项是否执行（写回对应开关键）；
- 「上移 / 下移 / 恢复默认 / 刷新 / 保存顺序与开关」；
- 保存时若任务正在运行会拒绝写入，避免和运行中的编排抢配置。

## 2. 导航路线

### 数据

```json
{
  "name": "每日委托路线",
  "description": "从主界面到委托面板",
  "waypoints": [
    {"page": "page_main"},
    {"template": "commission_icon", "timeout": 10},
    {"click": [0.5, 0.5], "wait": 1.0}
  ]
}
```

一个航点可以同时有多个动作，执行顺序固定为：**页面 → 等模板 → 点击 → 等待**。

| 字段 | 说明 |
|------|------|
| `page` | 目标界面名；走 `ui_ensure` 的 Page 拓扑导航，到不了算失败 |
| `template` | 等某个模板出现（超时算失败） |
| `click` | 比例坐标 `[x, y]`（0..1） |
| `wait` | 该航点做完后再等几秒 |
| `timeout` | 该航点的超时，默认 30s（页面导航与等模板共用） |
| `note` | 备注，不影响执行 |

校验（`Route.validate()`）会拒绝：空路线、空航点、`timeout <= 0`、比例坐标越界，
以及（如果传了已知界面集合）未注册的界面名。

### 执行

「导航路线」任务（`src/tasks/onetime/route_task.py`，`support_schedule_task=True`）：

- 配置 `路线文件`（`configs/routes` 下的名字）+ `从断点继续`；
- 断点**按整条航点**记录，复用流程那套 `CheckpointStore`（key 是 `route_<名字>`），
  跑通后自动清断点；
- 失败会调用 `mark_task_failure`（顺带存失败帧，可在「工具与诊断」里复测）。

## 3. 轮椅方案

「轮椅」= 重复度极高的固定操作。方案不需要新引擎：**录制段就是流程步骤**，
方案只是把若干段拼起来，再交给 `FlowExecutor` 跑。

```json
{
  "name": "深渊轮椅",
  "loop": 2,
  "between_wait": 0.5,
  "segments": [
    {"label": "进场", "events": [ ... 录制事件 ... ]},
    {"label": "输出循环", "steps": [{"type": "key", "key": "e", "duration": 0.2}]}
  ]
}
```

拼接规则（`src/core/replay.py`）：

- 每段优先用 `steps`（已经是流程步骤时），否则用 `events` 走
  `convert_recording()` 转换；
- 段与段之间插入 `between_wait` 秒的 `wait`（默认 0.5，0 表示不留缝）；
- `loop > 1` 时整串包进一个 `loop` 步骤（受流程 1000 次上限约束，`0` 会被拒绝）；
- 每段转换跳过的输入（右键/滚轮等）汇总进 `SchemeReport`，**如实报告**而不是忽略；
- 拼出来的流程同样过 `validate_flow`（500 步 / 4 层），超了直接报错而不是硬跑。

导出：`scheme_to_flow_file(scheme)` 把方案写成 `configs/flows/<名字>.json`，
之后就能在「流程 / 队列」任务或队列里跑。

## 4. 测试覆盖

| 测试 | 覆盖 |
|------|------|
| `tests/test_daily_order.py` | 配置串解析（多种分隔符/去重）、重排规则（未知项忽略、漏写追加）、上下移动、与 `DailyTask.build_task_plan` 的接线 |
| `tests/test_route.py` | 模型校验（空航点/越界/未注册界面）、存取、执行顺序、导航失败、模板超时、断点续跑与清除 |
| `tests/test_replay.py` | 分段转换与跳过统计、`between_wait`、`loop` 包装与边界、500 步校验、存取、导出成流程文件、经 `FlowExecutor` 真实回放 |

```bash
uv run python -m unittest discover -s tests
```
