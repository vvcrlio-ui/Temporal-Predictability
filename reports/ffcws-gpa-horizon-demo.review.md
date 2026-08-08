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
