# 功能对照表：需求清单逐条落地在哪

这份表是给「验收」用的：需求里每一条对应到**代码位置 / 测试 / 文档**，
以及**框架已经提供**或**受框架限制**的部分。找不到对应行的，就是还没做。

状态说明：

- ✅ **已实现**：本项目代码实现，有离线测试；
- 🔧 **框架提供**：ok-script 自带能力，本项目只做配置或薄封装（不改框架）；
- ⚠️ **受限制**：框架层面做不到，见备注；
- 🚧 **需实机**：逻辑已就绪，但需要游戏内界面/截图才能落地具体模板或坐标。

---

## 一、模板与识别基础设施

| 需求 | 状态 | 代码 | 测试 | 文档 |
|------|------|------|------|------|
| 识别失败自动存帧（最近 N 张） | ✅ | `src/core/failure_frame_store.py` | `test_failure_frame_store.py` | [诊断](diagnostics_and_policy.md) §4 |
| 失败帧复测：整帧扫全部模板并报每个匹配分数 | ✅ | `src/core/template_rescorer.py` + 「工具与诊断」页 | `test_template_rescorer.py` | 同上 §5 |
| 模板标注工具（框选/命名/增删/存标注） | 🔧 | 框架 `ui/qt/markup` | — | 同上 §5 |
| 标注区域纹理检查（纯色块拒绝） | ✅ | `src/core/template_audit.py` | `test_template_audit.py` | 同上 §7 |
| 模板 SHA-256（重复检测） | ✅ | 同上 | 同上 | 同上 §7 |
| 模板/素材热更新（逐文件校验 + 备份 + 回滚） | ✅ | `src/core/asset_pack.py` | `test_asset_pack.py` | 同上 §6 |
| 超时/重试/动作后等待/失败帧数量可调 | ✅ | `src/core/runtime_config.py` + 全局配置「自动化策略」 | `test_runtime_config.py` | 同上 §1 |
| 低配模式（超时 ×1.5，阈值不动） | ✅ | 同上 | 同上 | 同上 §1 |
| 卡死检测（画面长时间不变告警） | ✅ | `src/core/base_game_task.py` `_check_stuck` | `test_stuck_and_recovery.py` | 同上 §2 |
| 失败自恢复（回主菜单，带次数上限） | ✅ | 同上 `recover_after_failure` | 同上 | 同上 §3 |

## 二、日常自动化

| 需求 | 状态 | 代码 | 测试 | 文档 |
|------|------|------|------|------|
| 一条龙：顺序可配、可拖动排序 | ✅ | `src/tasks/daily/order.py` + 「一条龙顺序」页 | `test_daily_order.py` | [路线](routes_and_replay.md) §1 |
| 一条龙每项自己的参数可见 / 可打开配置 | ✅ | `src/core/task_config_summary.py` | `test_task_config_summary.py` | 同上 §1 |
| 周常活跃奖励 | ✅ | `assets/flow_templates/周常活跃奖励.json`（只用已有模板，开箱可跑） | `test_flow_templates.py` | [流程](flows_and_queues.md) §7 |
| 危机讨伐 / 剧情委托 | 🚧 | `assets/flow_templates/`（骨架流程，各差 3 个模板；模板名已写死，标好照抄即可） | 同上 | 同上 §7 |
| 实时辅助（按设置持续操作） | ✅ | `src/tasks/trigger/auto_combat_assist_task.py` | `test_auto_combat_assist_task.py` | 同上 §4 |
| 导航测试 / 路线管理（航点串、断点续跑） | ✅ | `src/core/route.py` + 「导航路线」任务 | `test_route.py` | 同上 §2 |
| 动作录制 → 流程（框架录制器 + 转换） | ✅ | `src/core/flow/recording.py` | `test_flow_recording.py` | [流程](flows_and_queues.md) §2 |
| 轮椅方案（多段录制拼成固定流程） | ✅ | `src/core/replay.py`（可循环、可导出成流程、可进队列） | `test_replay.py` | [路线](routes_and_replay.md) §3 |

## 三、流程编排

| 需求 | 状态 | 代码 | 测试 | 文档 |
|------|------|------|------|------|
| JSON 流程（500 步 / 1000 次 / 4 层嵌套） | ✅ | `src/core/flow/model.py`、`executor.py` | `test_flow.py`、`test_flow.py` | [流程](flows_and_queues.md) §1 |
| 录制一键转流程（最多 400 步） | ✅ | `src/core/flow/recording.py` | `test_flow_recording.py` | 同上 §3 |
| 断点续跑（跳过已完成顶层步骤） | ✅ | `executor.CheckpointStore` | 同上 | 同上 §2 |
| 任务队列（含分钟预算、失败即停） | ✅ | `src/core/queue/` | `test_queue*.py` | 同上 §4 |
| 队列项支持流程 / 队列 / 任务 / 轮椅方案 | ✅ | `flow_task._queue_resolver` | `test_replay.py` | 同上 §4 |
| 定时触发（框架的计划任务） | 🔧 | `support_schedule_task = True` | — | 同上 §5 |
| 配置档（快照 / 应用前备份 / 增删） | ✅ | `src/core/profile_store.py` | `test_profile_store.py` | 同上 §6 |

## 四、养成计算

| 需求 | 状态 | 代码 | 测试 | 文档 |
|------|------|------|------|------|
| 角色/奇波/灵子/装备材料计算 | ✅ | `src/core/growth/` | `test_growth.py` | [离线工具](offline_tools.md) §1 |
| 数据来自数据文件（换版本只换数据） | ✅ | `assets/data/growth.json` | 同上 | 同上 §1 |
| 从 wiki 导出后导入（校验 + 备份 + 原子替换） | ✅ | `growth.import_dataset` + 「导入数据」 | 同上 | 同上 §1 |
| 导出 CSV / PNG | ✅ | `src/core/growth/export.py` | 同上 | 同上 §1 |

> ⚠️ 内置数据是**示例**（结构与真实一致、数值不完整），真实数值需要你导入。

## 五、抽卡分析

| 需求 | 状态 | 代码 | 测试 | 文档 |
|------|------|------|------|------|
| 概率模型（0.8% 基础、71 抽起加概率、90 硬保底） | ✅ | `src/core/gacha/model.py` | `test_gacha_model.py` | 同上 §2 |
| 预算内概率 / 期望抽数 / 最坏情况 | ✅ | 同上 | 同上 | 同上 §2 |

## 六、记账与报表

| 需求 | 状态 | 代码 | 测试 | 文档 |
|------|------|------|------|------|
| 结算界面 OCR 记账（多种写法） | ✅ | `src/core/ledger.py` + `settlement_task` | `test_ledger.py` | 同上 §3 |
| 运行报表（时长 / 成功率 / 按任务 / 失败原因；日常 + 流程/队列都记） | ✅ | `RunLog.by_task` / `failure_notes` / `report_lines`，写入点在 `DailyTaskRunner` 与 `FlowTask.run` | `test_ledger.py`、`test_flow_task_run_log.py` | 同上 §3 |

## 七、界面

| 需求 | 状态 | 代码 | 测试 | 文档 |
|------|------|------|------|------|
| 主题（浅色/深色/跟随系统） | 🔧 | 框架 `qfluentwidgets` 设置 | — | [界面行为](ui_behavior.md) §7 |
| 界面透明度 / 背景图 | ⚠️ | 框架 2.0.6 **无任何透明度 API**（`blurRadius` 是死配置） | — | 同上 §7 |
| HUD 悬浮条（状态/进度/预计剩余，暂停停止） | ✅ | `src/core/hud.py` + `src/gui/hud_window.py` | `test_ui_behaviors.py` | 同上 §5 |
| 托盘 / 系统通知 | 🔧 | 框架托盘与通知 | — | 同上 |
| 点 × 时询问（完全关闭 / 收托盘 / 记住） | ✅ | `src/patches/close_behavior_patch.py` | 同上 | 同上 §1 |
| 任务栏进度条 | ✅ | `src/core/taskbar.py`（ctypes 调 `ITaskbarList3`，可降级） | 同上 | 同上 §3 |
| 自定义全局快捷键 | ✅ | `src/core/hotkeys.py` + `ui_extras_patch` | 同上 | 同上 §4 |
| 提醒（04:00 重置 / 体力循环） | ✅ | `src/core/reminders.py` + 提醒线程 | 同上 | 同上 §2 |

## 八、扩展

| 需求 | 状态 | 代码 | 测试 | 文档 |
|------|------|------|------|------|
| UID 遮挡（≤8 块，纯色/马赛克） | ✅ | `src/core/privacy.py` + 「隐私遮挡」页 | `test_privacy_and_diagnostics.py` | [隐私](privacy_and_support.md) §1 |
| 1920×1080 参考坐标（分辨率无关） | ✅ | 同上 | 同上 | 同上 §1 |
| 仅前景时遮挡 | ✅ | 同上（`only_foreground`） | 同上 | 同上 §1 |
| 坐标拾取（客户区 ↔ 参考坐标）+ 取色 | ✅ | `src/core/coord_picker.py` | `test_privacy_and_diagnostics.py` | 同上 §2 |
| 全屏十字线拾取覆盖层 | ⚠️ | 已做「1 秒延时取点」替代（换算与取色完整）；全屏覆盖层涉及句柄/多屏/DPI，需真机验证 | — | 同上 §2 |

## 九、工具与诊断

| 需求 | 状态 | 代码 | 测试 | 文档 |
|------|------|------|------|------|
| 语言包（应用/还原，带备份，路径白名单） | ✅ | `src/core/lang_pack.py` | `test_privacy_and_diagnostics.py` | 同上 §4 |
| 诊断包（配置/日志/模板/失败帧/系统信息） | ✅ | `src/core/diagnostics_bundle.py` | `test_privacy_and_diagnostics.py` | 同上 §4 |
| 崩溃诊断（钩子 + 自动附诊断包，启动时安装） | ✅ | `src/core/crash_guard.py` + `src/patches/crash_guard_patch.py` | `test_privacy_and_diagnostics.py` | 同上 §5 |
| 在线仓库（索引 + 一键安装，同名不覆盖） | ✅ | `src/core/repo_index.py` + 「分享仓库」页 | `test_repo_index.py` | 同上 §6 |
| 单实例（防多开） | 🔧 | 框架 `ok.util.process.check_mutex`（cwd 命名互斥量，等待 5 秒后按记录的 PID 收尾，失败则拒绝启动） | — | 同上 §8 |

## 十、工程与质量

| 需求 | 状态 | 代码 | 测试 | 文档 |
|------|------|------|------|------|
| 安装自检（流程/队列/方案/路线/配置/i18n） | ✅ | `src/core/health_check.py` + `tools/health_check.py` | `test_health_check.py` | [诊断](diagnostics_and_policy.md) §9 |
| 离线回归 | ✅ | `tests/`（**1097 项**，不需要游戏） | 自身 | [开发指南](development.md) |
| CI 测试门禁 | ✅ | `.github/workflows/pr-test.yml` | — | [界面行为](ui_behavior.md) §6 |
| CI 只对改动文件跑 ruff | ✅ | 同上 | — | 同上 §6 |
| i18n 校验（6 语种、无空 msgstr） | ✅ | `scripts/validate_all.py` + `tools/task_i18n_helper.py` | — | 同上 §6 |

---

## 还差什么

| 缺口 | 原因 | 需要你做什么 |
|------|------|--------------|
| 危机讨伐 / 剧情委托 | 已给骨架流程，但入口/开始/结算三个按钮的**模板还没标** | 标这三个模板（名字照抄流程里的 `crisis_hunt_*` / `story_commission_*`），或给截图我来标 |
| 界面透明度 / 背景图 | ok-script 2.0.6 没有任何透明度 API | —（只能重写窗口合成，不建议） |
| 全屏十字线拾取 | 需要在真机上验证多屏/DPI/点击穿透 | 有需要时我再做，逻辑已就绪 |
| 养成真实数值 | 内置是示例数据 | 从 promilia.wiki 导出后用「导入数据」导入 |
