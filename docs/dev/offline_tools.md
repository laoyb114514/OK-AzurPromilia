# 离线工具：养成计算 / 抽卡分析 / 记账报表（批次 C）

这三个模块都不碰游戏、不截图、不发输入，纯计算与文件读写，因此可以完整离线测试：

| 模块 | 目录 | 作用 |
|------|------|------|
| 养成计算 | `src/core/growth/` | 目标 → 经验/尤尼/材料/体力/货币，库存缺口，多目标合并，CSV/PNG 导出 |
| 抽卡分析 | `src/core/gacha/` | 保底层 + 伯努利层概率模型：期望抽数、预算内完成概率、最坏情况 |
| 记账报表 | `src/core/ledger.py` | 结算文字 → `ledger.jsonl`；任务结果 → `runs.jsonl`；两者都能导出 CSV |

## 1. 养成计算

### 数据在数据文件里，代码只做聚合

`assets/data/growth.json` 描述每种目标每一段等级需要什么。**内置数据是示例**
（结构与真实数据一致、数值不完整）；真实数值请从 promilia.wiki 的养成规划器导出后
用 `Dataset.from_file(路径)` 载入。

```json
{
  "materials": {"星脉结晶": {"category": "currency"}},
  "exp_items": {"小型灵粹": 100, "普通的灵粹": 500, "浓缩灵粹": 2000},
  "dungeons": [{"name": "灵粹试炼", "stamina": 20, "drops": {"普通的灵粹": 8}}],
  "aliases": {"星脉结晶": {"大星脉结晶": 5}},
  "entries": [
    {
      "key": "char_amber", "name": "琥珀", "kind": "character", "max_level": 80,
      "levels": [{"from": 1, "to": 20, "exp": 4000, "credits": 2400,
                  "materials": {"风之碎晶": 3}}],
      "potentials": [{"name": "生命", "levels": [{"level": 1, "exp": 100}]}],
      "star_stages": [{"star": 1, "copies": 1, "materials": {"星脉结晶": 10}}]
    }
  ]
}
```

四种类型：`character`（角色）、`pet`（奇波）、`spirit`（灵子）、`equipment`（装备）。
装备的「强化」走 `levels`，「升星」走 `star_stages`（`copies` 是该阶段需要几份本体）。

### 计算规则

- **等级区间按比例切分**：目标 `21→40` 只取第 2 段的经验/材料；`1→999` 会被夹到 `max_level`。
- **份数**：`copies` 会同时放大经验、尤尼、材料与升星本体数。
- **奇波潜能**：`potential_level` 是「所有潜能统一练到几级」，6 条潜能会一起计入经验。
- **升星**：`star` 会累计到该星级的全部 `star_stages`（本体份数 + 材料）。
- **库存**：`inventory` 只影响「缺口」，不影响「需求」。
- **体力折算**：每种材料取 `drops/stamina` 最优的副本 → `体力 = 需求 × 每单位体力`，
  次数按副本掉落向上取整；没有任何副本掉落的材料记进 `no_source`，**不硬算**。
- **货币凑法**：`aliases` 里有兑换比的材料按「大单位优先」凑，余数用原单位，
  且用**缺口**而不是总需求计算（库存里的原单位先抵扣）。
- **经验道具**：贪心用最大的道具，余数用小的兜底。
- 一次最多合并 **12** 个目标。

### 导出

```python
from src.core.growth import Dataset, Target, compute_plan, export_csv, export_png

plan = compute_plan(Dataset.load_default(), [Target("char_amber")], inventory={"尤尼": 20000})
export_csv(plan, "养成材料单.csv")   # 目标表 + 材料单 + 汇总，utf-8-sig 供 Excel 直接打开
export_png(plan, "养成材料单.png")   # 1280 宽卡片，表头 + 斑马纹，缺口标红
```

PNG 用系统里的雅黑/黑体渲染中文；找不到字体时退回 Pillow 默认字体（中文会变方块）。

## 2. 抽卡分析

### 模型

`PityBernoulliModel` = **保底层**（第 i 抽出最高稀有度的概率）+ **伯努利层**
（这次是不是目标，概率 `target_rate`）。

内置参数（社区数值，游戏未公开官方概率表）：

| 项 | 值 |
|----|----|
| 基础概率 | 0.8% |
| 软保底 1 | 第 71 抽起，每抽 +2 个百分点（71 抽 = 2.8%） |
| 软保底 2 | 第 81 抽起，每抽 +8 个百分点（81 抽 = 28.8%） |
| 硬保底 | 第 90 抽 = 100% |

算出来的关键结论（`tests/test_gacha_model.py` 固化为回归基准）：

- 单份目标、`target_rate=100%`：**期望 58.3 抽**，90 抽内必出，最坏 90 抽；
- 单份目标、`target_rate=50%`：**期望 110.8 抽**，180 抽内完成 **82.85%**（与社区公开值一致）；
- `target_rate<100%` 时**不存在有限最坏情况**，结果里会如实说明而不是编一个数。

### 用法

```python
from src.core.gacha import PityBernoulliModel, GachaParams, parse_rate_table

model = PityBernoulliModel()                       # 默认 100% 出目标
print(model.plan(copies=1, pity=0, budget=180).summary())

half = PityBernoulliModel(target_rate=0.5)         # 小保底
half.probability_within(180, copies=1)

custom = PityBernoulliModel(GachaParams(custom_rates=parse_rate_table("2.8%,28.8%,100%")))
```

**已知局限**：模型不追踪游戏里的「大保底状态」。需要模拟大保底就把 `target_rate`
设成 1.0；已经从某个垫抽数开始就用 `pity`。`custom_rates` 的长度必须等于
`hard_pity`，且最后一抽必须是 100%。

## 3. 记账与运行报表

### 结算记账

`parse_settlement_text()` 支持这些写法（`×` 也可以写成 `x` / `*`）：

```text
获得的奖励：尤尼 ×1,500      → 收入 尤尼 1500
12 × 波力果                  → 收入 波力果 12
普通的灵粹*24                → 收入 普通的灵粹 24
消耗：星脉结晶 ×3            → 支出 星脉结晶 3
```

- 含「消耗 / 花费 / 扣除 / 支出 / 使用」的行记为**支出**，其余记为收入；
- 同一条条目被两个正则同时匹配时按位置去重；
- 一条都没解析出来会抛 `SettlementFormatError`，不会静默记 0。

存储是 `ledger.jsonl`（一行一条 JSON，追加写，坏行读取时跳过）：

```python
from src.core.ledger import Ledger

ledger = Ledger("ledger.jsonl")
ledger.record_text(ocr_text, source="结算界面")
ledger.totals()          # {'income': ..., 'expense': ..., 'net': ...}
ledger.today_summary()   # 按物品的今日收支
ledger.export_csv("ledger.csv")
```

### 运行报表

`RunLog` 写 `runs.jsonl`，用于成功率、平均用时与「预计剩余时间」：

```python
from src.core.ledger import RunLog

log = RunLog("runs.jsonl")
log.record("DailyTask", ok=True, seconds=312.0)
log.stats("DailyTask")               # count / success / failed / success_rate / avg_seconds
log.estimate_seconds("DailyTask")    # 任务栏「预计剩余」用
log.export_csv("runs.csv")
```

两个文件都是**追加写 + 读取时容错**，所以手工编辑、断电截断都不会让统计整个崩掉。

## 4. 测试覆盖

| 测试 | 覆盖 |
|------|------|
| `tests/test_growth.py` | 数据载入与校验、区间比例切分、份数/潜能/升星、库存缺口、最优体力来源、无来源标注、大单位优先凑货币、经验道具贪心、12 目标上限、CSV/PNG 导出 |
| `tests/test_gacha_model.py` | 概率表数值、单调性、硬保底、垫抽、期望区间、预算内概率单调、50% 概率的 82.85% 基准、最坏情况、自定义概率表校验 |
| `tests/test_ledger.py` | 四种结算写法、支出识别、去重、无匹配报错、JSONL 坏行容错、按天/按物品汇总、CSV 导出、运行统计与用时估算 |

```bash
uv run python -m unittest discover -s tests
```
