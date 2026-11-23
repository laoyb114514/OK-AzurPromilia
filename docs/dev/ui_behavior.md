# 界面行为：关闭询问、提醒、任务栏进度、快捷键（批次 E-2）

「界面与提醒」页集中管理这四件事，设置写到 `configs/` 下的 JSON，改完立即生效
（提示线程每轮都会重新读配置；快捷键例外，见下）。

## 1. 关闭询问

`src/core/close_behavior.py` + `src/patches/close_behavior_patch.py`。

框架只有一个「关闭时最小化到托盘」开关，没有「问一下」的余地。补丁把
`MainWindow.closeEvent` 换成三选一：

| 选择 | 行为 |
|------|------|
| 完全关闭 | 调用**原来的** `closeEvent`（看门狗、清理、托盘图标回收都不变） |
| 收到托盘 | `event.ignore()` + `hide()` |
| 取消 | `event.ignore()` |

- 可勾选「记住我的选择」，只记 `close` / `tray`（取消不该被记住）；
- 退出流程中（`exit_event` 已置位）**直接走框架逻辑**，不会弹窗卡住退出；
- 任何异常都退回框架逻辑 —— 补丁坏掉最多是「没弹窗」，不会关不掉。

配置：`configs/close_behavior.json`（`{"ask": true, "remember": ""}`）。
页面上三种模式：每次询问 / 直接关闭 / 最小化到托盘。

## 2. 提醒

`src/core/reminders.py` + `src/patches/ui_extras_patch.py` 里的提醒线程（30 秒轮询）。

- **每日重置**：过了 `daily_reset_hour`（默认 4 点）当天的第一次轮询提醒一次，
  同一天不重复；跨天自动重置；
- **体力提醒**：每 `stamina_interval_minutes` 分钟提醒一次（0 = 关闭）；
- 只发**右下角通知**，不打断任务；调度器是纯函数 + 注入时钟，测试不用真等 04:00。

配置：`configs/reminders.json`。

## 3. 任务栏进度

`src/core/taskbar.py` + 进度线程（0.5 秒轮询 `og.executor.current_task`）。

- 比例 = 已用时间 / 该任务的**历史平均用时**（`RunLog.estimate_seconds`），
  **封顶 0.97** —— 估到 100% 还在跑会误导人，结束时直接撤掉进度条；
- 没有历史数据就不显示（返回 `None`），不编一个假进度；
- 变化小于 1% 不推，避免每秒刷爆系统调用；
- 后端用 ctypes 直接调 `ITaskbarList3`（不依赖 pywin32）；**拿不到窗口句柄或 COM
  失败就安静降级成空实现**，绝不影响任务执行。

配置：`configs/ui_extras.json` 的 `taskbar_progress`。

## 4. 全局快捷键

`src/core/hotkeys.py` + 快捷键线程（`RegisterHotKey` + `PeekMessageW` 消息循环）。

| 动作 | 默认键 | 说明 |
|------|--------|------|
| `pause` | `ctrl+alt+p` | 暂停 / 继续（`executor.pause()` / `executor.start()`） |
| `stop` | `ctrl+alt+s` | 停止当前任务（`executor.stop_current_task()`） |
| `toggle_uid_mask` | `ctrl+alt+u` | 开关 UID 遮挡（改 `configs/privacy.json` 的 `enabled`） |

- 为什么不是 F9/F10：**F9–F12 已经被框架的启动/停止占用**，再绑会冲突；
  校验函数会直接报「被框架的启动/停止占用」；
- 纯字母键会被拒绝（会和游戏输入打架），必须带修饰键；
- 校验能提前发现：写法错误、重复绑定、占用框架键；
- 改完**需要重启**才重新注册（消息循环里注册一次）。

配置：`configs/hotkeys.json`。

## 5. HUD 悬浮条

`src/core/hud.py`（纯逻辑）+ `src/gui/hud_window.py`（窗口）+ `ui_extras_patch` 里挂载。

- **只在有任务运行时显示**，任务结束自动隐藏；
- 内容：`运行中 · 任务名  42%  预计还剩 12 分 30 秒`；
- 位置按**屏幕可用区域底部居中**（`hud_position`），用 Qt 的逻辑像素，150% 缩放也不歪；
- 窗口标志 `WindowStaysOnTopHint | Tool | FramelessWindowHint | WindowDoesNotAcceptFocus` +
  `WA_ShowWithoutActivating` —— **不抢游戏焦点、不打断输入**；
- 自带「暂停/继续」「停止」两个按钮（走 `executor.pause()/start()/stop_current_task()`）；
- 退出时通过 `app.aboutToQuit` 一起关掉，不留残影；
- 开关在「界面与提醒」页，写到 `configs/ui_extras.json` 的 `hud_enabled`。

剩余时间格式化（`format_remaining`）：`58 秒` / `12 分 30 秒` / `1 小时 1 分`，
数据缺失或异常时显示「未知」而不是编一个数。

## 6. 工程质量

- **CI 新增「只对改动文件跑 ruff」**（`.github/workflows/pr-test.yml`）：
  基线里还有历史告警，全量检查会挡住所有 PR；改成只检查 `git diff base...HEAD` 的
  `*.py`，新代码必须干净，确需保留的告警用 `# noqa: 规则名` 显式豁免。
- `pyproject.toml` 里把 `RUF003`（注释里的 `×`、`—` 等中文标点）加入 ignore：
  本项目注释大量引用游戏内文案，这类字符是故意的。
- 顺手把碰过的文件里的历史告警清零（`base_game_task.py` / `daily_task_runner.py` /
  `daily_task.py` / 若干测试），这样这条门禁对后续改动是可用的。

## 7. 明确没做的

- **界面透明度 / 背景图**：ok-script 2.0.6 **没有任何透明度 API**
  （`cfg.blurRadius` 是死配置），要做只能重写窗口合成，风险高、收益低，暂不做。

## 8. 测试覆盖

| 测试 | 覆盖 |
|------|------|
| `tests/test_ui_behaviors.py` | 关闭行为决策与记忆、配置读写容错；提醒设置校验、调度（每日一次/跨天/体力间隔/重置/剩余时间）；快捷键解析（修饰键、F 键、别名、纯字母拒绝、重复/占用检测、注册计划、持久化）；任务栏进度（节流、封顶、清除、无历史不显示、无句柄降级）；快捷键动作（暂停切换、停止当前任务、开关遮挡、未知动作、无执行器）；HUD 文案与位置（剩余时间格式化、进度封顶、隐藏剩余、底部居中、多屏偏移、超大窗口夹取、设置读写保留其它键） |

```bash
uv run python -m unittest discover -s tests
```
