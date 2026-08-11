# Review 意见：§C 学习曲线分析层

---

# 第 2 轮：通过

审查对象：commit `16df149`（`project/analysis/learning_curve.py`、
`project/tests/test_learning_curve.py`、`reports/ffcws-gpa-horizon-demo.md`）。

**结论：approved。** R1–R6 全部修复，逐条独立复验通过。§C 可以收工，
下一步进 §A。

## 逐条复验

| # | 意见 | 结论 | 证据 |
|---|---|---|---|
| R1 | envelope `observation_count` 是误差求和 | 已修 | 改为对上游 `observation_count` 具名聚合（`learning_curve.py:434-438`）。独立复验：2 模型 × 2 unit → 计数 `4`，正确 |
| R2 | bootstrap 按组独立重抽 seed | 已修 | `_resample_units` 改为全表抽一次并应用到所有组，另加"各组 unit 集合必须一致"的校验（`learning_curve.py:443-462`）。独立复验：`m1`/`m2` 抽到的多重集合均为 `[3,2,2,1]`，一致 |
| R3 | 未测名义覆盖率、构造抵消被测对象 | 已修 | 删掉正负成对构造，改用普通非对称噪声；40 次重复统计比例，按二项标准误设容差 |
| R4 | 错配阈值自指 | 已修 | 改为绝对阈值：匹配 `< 1e-6`、错配 `> 0.05`（`tests:167-170`） |
| R5 | 自检失败连坐主估计 | 已修 | 拆出 `_extrapolation_check`，返回 `NaN` + `extrapolation_check_status`（`invalid_cutoff` / `insufficient_points` / `fit_failed` / `ok`），主拟合照常输出 |
| R6 | 单调化主口径 | 已实现 | `running_minimum`（主）与 `isotonic_value`（对照）并存，原始值保留。测试锁住"前缀最小值只下调、保序投影可上调"的差异 |

## 覆盖率：换一批种子独立复验

Codex 报告 40 次重复得 92.5%。我用**另一组种子**、60 次重复重测：

```
实测覆盖 54/60 = 90.0%      名义 90%
偏离 = 0.00 个标准误（±1 SE = 3.9%）
平均区间宽度 = 0.0215       （第 1 轮：0.0061）
```

区间宽度约为原来的 3.5 倍。这印证了 R2 是根因：第 1 轮 83% 的欠覆盖，
来自组间独立重抽把区间做窄；恢复跨组配对之后，区间变宽、也变诚实。

## 其他复核

- `31 passed`，与报告一致。
- 模块未 import `aleatoric_nk_grid`；`requirements.txt` 未改；
  `Aleatoric_Luck` checkout 干净。
- 全文无 `wave` / `landmark` / `ffcws` / `gpa`，article-agnostic 保持。
- 提交只含本工作包的三个文件，未误收 `plans/` 与本 review 文件。

## 一处未声明的改动（不用返工，记录在案）

`_fit_parameters` 里 `OptimizeWarning` 的处理从 `simplefilter("error", ...)`
改成了 `simplefilter("ignore", ...)`（`learning_curve.py:387`）。报告的
「第 2 轮修改」没有提到这一条。

**这个改动本身是对的、而且是必要的**：`curve_fit` 在雅可比奇异时会发出
"Covariance of the parameters could not be estimated"，但本模块用
`parameters, _ = curve_fit(...)` 丢弃了协方差、从不使用它；区间是靠 bootstrap
得到的。第 1 轮 R5 里"5 个点、参数精确还原却整体失败"正是这个警告造成的，
不改就修不掉 R5。

风险是它同时放宽了"拟合成功"的判定。缓解是现成的：外推自检与 bootstrap 都会
暴露真正病态的拟合。因此**不要求改回**。

**要求**：下一个工作包交付时，凡是为了满足某条意见而顺带做出的行为变更，
都要在报告里单列一行。按 `AGENTS.md#response-contract`，这类信息属于
「关键变更」，不能只体现在 diff 里。

## 遗留（不阻塞，交给后续工作包）

1. **覆盖率测试容差偏松。** `±3 × 二项标准误`，40 次重复下约为 ±14%，
   即接受 76%–100%。作为快速回归够用，但如果以后区间出现系统性偏差，
   这个测试不一定拦得住。若 §A/§B 之后运行时间允许，建议提高重复次数
   并收紧到 ±2 SE。
2. **`bootstrap_failures` 是全局计数**，被写进每一行（`learning_curve.py:236`）。
   目前 `fit_learning_curves` 对一次抽样是全有或全无，所以数值正确；
   将来若改成按 series 容错，这里要跟着改成按组计数。
3. **谁负责过滤 `status != "ok"` 的引擎输出行**，目前没有归属。
   `aggregate_median_errors` 遇到 NaN 会直接报错，而真实引擎输出必然含
   失败 cell。`plans/ffcws-horizon-figures.md` 把过滤放在图层，但学习曲线层
   也直接读同一份 CSV。**这个归属要在 §B 或图层开工前定下来**，否则两边都
   假设对方做了。

## 流程

第 1 轮 R6（未提交）已解决，本轮提交为 `16df149`。

`AGENTS.md#mandatory-workflow` 的 Close 步骤仍未写明"交付时提交到
`codex/<slug>` 分支、不 push"，review 文件位置也仍未约定（本文件沿用
`reports/<slug>.review.md`）。建议补进 `AGENTS.md`，但属于文档变更，由用户决定。

---

# 第 1 轮：changes-requested（已全部处理，存档）

审查对象：当时未提交的工作区改动。

结论摘要——范围控制与架构边界正确，但存在两个必须修的缺陷、两处测试与方案要求
不符、一处设计问题、一处流程问题：

- **R1**：envelope 的 `observation_count` 实为误差求和（`.groupby(...)["observed_error"]`
  后两个聚合落在同一列）。实测输出 `0.898816`，与该 N 下误差求和逐位相等，真实计数应为 2。
- **R2**：`_resample_units` 在每个 group 内部各自重抽 seed，破坏跨组配对。
  实测 `m1` 抽到 `[3,2,2,1]`、`m2` 抽到 `[1,0,0,0]`。后果是包络区间失效
  （包络逐 N 取各模型最小值，预设同一 seed 下可比）与跨档比较失效。
- **R3**：只断言区间包含真值一次，未统计覆盖率；且
  `symmetric_noisy_power_records` 用正负成对扰动使中位数恒等于真值曲线，
  抵消了被测对象。独立实测覆盖 50/60 = 83%（名义 90%），属轻微欠覆盖。
- **R4**：`assert mismatched > matching * 100` 阈值自指，`matching` 趋近 0 时断言趋于恒真。
- **R5**：C2 自检的样本量要求被强加给 C1 主估计。实测 5 点序列主拟合可精确还原
  `[0.2, 1.5, 0.7]`，整体却抛异常。
- **R6**：改动未提交，分支停在 `0d55219`。本仓库 `AGENTS.md` 的 Close 步骤未要求提交，
  不计为过失。

另确认 Codex 提出的"保序回归与单向收紧口径冲突"成立，属方案表述缺陷。
已在 `plans/ffcws-gpa-horizon-demo.md` §C4 与「测试要求」第 4 条修正为：
主口径用前缀最小值，保序回归降为对照，两者都输出。

---

# 第 3 轮（§A 波次划分）：通过

审查对象：commit `949b5b9`。

**结论：approved。** 四条验收标准逐条独立复验通过，五套 schema 全部通过引擎自身校验。
§A 可以收工，下一步进 §B。

## 逐条复验（我自己算的，不是照抄报告）

| 验收 | 结论 | 证据 |
|---|---|---|
| 2 严格嵌套 | 通过 | `P0 ⊊ P1 ⊊ P3 ⊊ P5 ⊊ P9`，四个包含关系全部为真严格 |
| 3 无越界列 | 通过 | 对每档独立重算 `source_column → 采集波次`，越界列数均为 **0** |
| 4 未分配 source | 通过 | `unassigned_sources.csv` 含 3 行（`innatsm`/`incitysm`/`ihostat`），带 `reason` 列；未泄漏进任何一档 |
| 表复用 + 官方切分 | 通过 | 五档 `table`/`test_table` 均指向同一份 `data.parquet`/`test.parquet`，`split_mode` 全为 `external_test` |

各档规模与我在真实 manifest 上独立算出的累积值精确一致：

| 档 | 建模列 | source 组 | onehot / continuous |
|---|---|---|---|
| lm0（出生）| 1158 | 351 | 301 / 50 |
| lm1（1 岁）| 2867 | 848 | 733 / 115 |
| lm3（3 岁）| 5776 | 1701 | 1495 / 206 |
| lm5（5 岁）| 8509 | 2506 | 2211 / 295 |
| lm9（9 岁）| 11426 | 3397 | 3039 / 358 |

## 关键复验：引擎能不能读

方案没把这条写成验收标准，但它才是 §A 真正的成败条件。我对五套 schema 逐个跑了
引擎自己的 `load_input` + `validate_input`：

```
lm0 ✓  lm1 ✓  lm3 ✓  lm5 ✓  lm9 ✓
```

按 `Adapter/ADAPTER.md` §6，`validate_input` 会把"从实际 predictors 与 manifest
重算出的 universe"与定义文件内容比对。五档全过，说明 feature universe 内容正确。

## 关于"必须用引擎的 canonical_feature_universe()"

`landmarks.py` 里没有直接调用该函数，一度看像违反方案 §A2。核查后确认：
它委托给 `contract.write_engine_schema`，后者在 `contract.py:151-153` 使用
`source_groups()` + `canonical_feature_universe()` + `canonical_json()`。

**这比直接调用更好**——`ARCHITECTURE.md#3` 正是把"生成外部引擎 schema 与
feature universe"划给 `contract.py` 的。没有绕过契约，是正确的复用。

## 测试写法

- 波次映射函数按五个波次参数化，标签与真实前缀形态一致（`m1`/`p2`/`hv3`/`f4`/`t5`）。
- 未分配集合的测试里包含 `z6future`——**波次 6 是 15 岁那波**，必须被排除而不是
  静默纳入。这条方案没要求，是 Codex 自己加的防御，方向对。
- 真实数据那条只断言"嵌套 + 无越界 + 不含未分配"，**没有断言具体列数**，
  符合方案"不得写成常量或断言的期望值"。缺真实产物时 `skipif` 跳过，合理。
- `40 passed`（基线 31 + 9），与报告一致。

## 遗留（不阻塞）

1. **`project/build_landmark_schemas.py` 是第二个 CLI 入口，未进
   `ARCHITECTURE.md#3` 的模块表。** 该表目前只列了 `adapter.py` 作为 CLI 入口。
   建议补一行，并按 Codex 自己的建议在 `project/schema/README.md` 记录生成命令
   与 landmark manifest 路径（`data/ard/<dataset>/landmarks/lm{t}/`）。
2. 报告如实写了"外部引擎 checkout 有一个预先存在的未跟踪 `AGENTS.md`，
   无法证明工作树完全干净"。核实属实，该文件与本轮无关，属于诚实披露。
3. 本轮无未声明的行为变更；上一轮 `OptimizeWarning` 那类遗漏没有重复。

## 下一步（§B）开工前必须先定的两件事

这两条不属于 §A，但会挡住 §B：

1. **谁过滤引擎输出里 `status != "ok"` 的行。**`aggregate_median_errors` 遇到空值
   直接报错，图层方案把过滤写在图层，两层读同一份 CSV。建议放在
   `project/analysis/` 的公开入口，图层复用，口径不分叉。
2. **`seed` 在 `external_test` 下不切分数据。**`nk_grid.py:1611` 是
   `splits = {seed: fixed_split for seed in split_seeds}`——每个 seed 拿到完全相同的
   训练集，全部随机性来自 `SeedSequence([seed, draw])` 的排列。因此：
   - `seed` 与 `draw` 数学上可互换，只有乘积有意义；
   - §C 的 bootstrap 区间量的是**蒙特卡洛误差**，不是家庭层面的抽样误差
     （家庭与切分都是固定的，一次都没重抽）。**图注必须写明这一点**，
     否则会被读成"对总体的不确定性"。这条要补进图层方案。

---

# 第 4 轮（§B panel 配置 + §C0 过滤）：通过，带一条随后修

审查对象：commit `9047f74`。

**结论：approved。** §B 可以收工，**pilot 可以立刻开跑**。发现一个潜在缺陷（F1），
不阻塞本次试跑，随 §D 一并修。

## 逐条复验

| 项 | 结论 | 证据 |
|---|---|---|
| `n_grid` 末端加密 | 通过 | gpa 实际可用训练行 **1165**（`data.parquet` 中 `gpa` 非缺失数，独立核对）。`466 / 816 / 1165` 恰为 40% / 70% / 100% |
| `k_grid` 逐档不同 | 通过 | 全量 K 为 `351 / 848 / 1701 / 2506 / 3397`，与各档 source 数逐一对应 |
| 两份配置 + dry-run | 通过 | 正式 71,680 = 8N × 4K × 64 × 7模型 × 5档；pilot 5,600 = 5N × 2K × 16 × 7 × 5 |
| §C0 无硬编码列名 | 通过 | 全文无 `status` / `constant_prediction` / `underdetermined` 字面量（唯二命中是 `extrapolation_check_status`，无关） |
| §C0 规则由调用方传入 | 通过 | `validity_column` + `validity_values` + `exclusion_flag_columns`，且校验了互相依赖、重复列、空集合 |
| 过滤在聚合之前 | 通过 | `fit_learning_curves` 先 `_filter_records`（:119）再 `aggregate_median_errors` |
| 过滤在重抽之前 | 通过 | `bootstrap_asymptote_intervals` 先过滤（:202）再 `_resample_units`（:229）。顺序正确——先剔无效行再抽单位，否则会抽到整单位无效 |
| 旧测试未被弱化 | 通过 | 新增 4 个过滤测试，既有 40 项未改断言强度；`44 passed` |

## Codex 自己标出的不一致：属实，且已实测

报告指出「方案里 7 个模型，但成本算式按 6 个模型算」。**这是对的**，是我给方案补成本
表时的疏漏——我实测的六模型没含 `super_learner`。

补测结果（M2 单线程）：

| N | K | 六模型 | `super_learner` | 占比 |
|---|---|---|---|---|
| 466 | 300 | 8.5 s | 3.5 s | +41% |
| 1165 | 300 | 138.4 s | 8.6 s | +6% |
| 466 | 3397 | 37.7 s | 42.3 s | +112% |

结论：`super_learner` 在大 N / 小 K 时很便宜，在大 K 时约等于再加一份。
整体成本估计上浮 **10%–100%**，量级不变。主动指出这条是对的。

## F1（随 §D 一并修）：字符串型布尔标志会静默丢掉好行

`_filter_records` 中：

```python
keep &= ~records[column].fillna(False).astype(bool)
```

当标志列是**字符串** dtype 时，`astype(bool)` 对任何非空字符串都返回 `True`，
包括 `"False"`。实测：

```
输入 4 行，其中只有 1 行 underdetermined 为真
列 dtype = str  →  实际剔除 3 行，只保留 1 行   ❌
列 dtype = bool →  实际剔除 1 行               ✓
```

**失败模式是静默丢弃有效数据**，比报错更糟——曲线会照常画出来，只是基于更少的数据。

**当前不会触发**：我核过引擎的失败行构造（`nk_grid.py:1823` → `_empty_diagnostics()`），
`constant_prediction` / `underdetermined` / `converged` 在失败时写的是真布尔 `False`，
不是空值，所以列不会退化成字符串。实测样本输出的这三列也确为 `bool` dtype。

**但仍要修**：本模块的设计前提就是 article-agnostic、接受任意来源的表格。
对一种完全合理的输入格式静默算错，与该前提冲突。

修法二选一，任选其一并加测试：
- 显式映射：仅接受真布尔/0-1/`{"true","false"}` 大小写不敏感字符串，其余抛错；
- 或严格化：非布尔 dtype 直接报错，要求调用方先转换。

**不要**保留现在这种"看起来能跑、结果悄悄错"的行为。

## F2（决策项，不是缺陷）：匹配 K 含 300，在出生档是 85%

方案里我写过「匹配值要明显小于 351」，并把 300 → 出生档抽 85% 作为警示例子。
配置取的正是 `[100, 200, 300]`。

Codex 已把「正式 N/K 精确档位」列入待确认，处理方式正确——这是留给人工的研究参数，
不是实现错误。

需要注意的连带影响：**pilot 中 lm0 的 `k_grid` 是 `[300, 351]`**，两个臂几乎相同
（300 / 351 = 85%），该档基本没有"匹配 vs 全量"的对比度。作为流水线试跑无妨，
正式跑之前应重新取值。

## F3（次要）：bootstrap 路径丢弃了排除计数

`bootstrap_asymptote_intervals` 里 `filtered_records, _, _ = _filter_records(...)`，
排除行数与占比被丢掉，返回的区间表也不含这两列。只走 bootstrap 入口的调用方
（图层很可能如此）拿不到 `excluded_cell_ratio`。建议在返回表中补上，或在
`figures` 侧明确改为从 `fit_learning_curves` 取。

## Pilot 耗时估计

按实测成本对 pilot 网格求和，单线程约 **12–13 小时**，四核并行约 **3–4 小时**，
落在方案设定的目标内。但成本曲线不单调（同一 K 下 N=1165 实测 138 s 高于
N=1500 的 84 s），估计上下浮动可达一倍。**建议直接跑，用实测代替估计**——
这本来就是 pilot 的用途。引擎自带断点续跑，跑不完可以中断看部分结果。
