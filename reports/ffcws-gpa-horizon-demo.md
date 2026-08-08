# FFCWS GPA Horizon Demo：实施记录

## 本轮范围

本轮仅实现方案 §C 的通用学习曲线分析层及其合成数据测试：跨重复观测中位数聚合、幂律和指数渐近线拟合、最大样本量外推自检、按指定重复单位的 bootstrap 区间、非增保序回归与显式方差归一化。没有实现 §A、§B 或 §D，也没有读取真实数据、修改面板或修改外部引擎。

## 合成数据验证边界

- Bootstrap 覆盖率使用 40 个独立、非对称高斯噪声合成数据集；每个数据集 48 次共享重复单位 bootstrap，名义覆盖率 90%。实测覆盖 **37/40 = 92.5%**，平均区间宽度为 **0.020117**。这验证的是该合成设定，不能替代真实网格上的覆盖评估。
- 单调化只验证了：给定任意长度序列时，模块保留原值，并同时输出只下调的前缀最小值与可能上调局部值的保序回归。本轮没有真实多档结果，不能验证真实场景的跨档约束。
- 归一化接受调用方明确传入的测试集方差，并以给定数值测试；本轮未读取真实测试集，不能实测该方差。

## 待澄清问题

1. `n_grid` / `k_grid` 的正式取值尚未确定；这属于 §B，本轮未创建或运行网格。
2. `preset` 与正式网格的算力预算尚未确定；这属于 §B，本轮未运行外部引擎。

## 第 2 轮修改

- **R1**：`project/analysis/learning_curve.py` 的 `_pointwise_envelope` 现在分别取最小误差和上游 `observation_count` 的整数和；测试将 envelope 的计数逐个样本量与所有 individual 行计数之和比较。
- **R2**：`_resample_units` 现在只从全表抽一次 `sample_column` 多重集合并应用到所有组，同时拒绝任何组缺少共享单位的输入；测试锁住每组抽得完全相同的单位多重集合。正式调用继续要求显式传入 `sample_column`；引擎输出应传入 `seed`。
- **R3**：删除正负成对噪声构造，改为重复覆盖率实验；上述 40 次实测覆盖率和平均区间宽度是本轮固定种子验证结果。
- **R4**：指数真模型与幂律错配的 C2 测试改为绝对阈值：匹配形式相对偏差小于 `1e-6`，错配形式大于 `0.05`。
- **R5**：`_fit_series` 先完成主拟合；`_extrapolation_check` 将截断点无效、点数不足或诊断拟合失败记录为 `extrapolation_check_status`，并将三项诊断数值置为 `NaN`，不再连坐主估计。测试覆盖 3 和 4 个点的点数不足诊断。
- **R6**：`monotonize_nonincreasing` 现在同时输出原始值、主口径 `running_minimum` 与对照 `isotonic_value`。测试锁住前缀最小值逐点只下调，而保序投影可以上调局部原始值。

## 第 3 轮修改（§A：波次划分）

### 改动清单

- `project/src/ffcws_data_processor/landmarks.py`：新增 FFCWS 波次解析纯函数和 landmark schema 导出器；按 source 名字的字母前缀后首位数字分类，无法归类的 source 显式写出且不进入任一 predictor 集合。
- `project/build_landmark_schemas.py`：新增 GPA landmark 产物的可复现命令入口；读取既有 ARD 表并生成五份 schema，不复制 `data.parquet` 或 `test.parquet`。
- `project/schema/ffc_median_mode_gpa_lm{0,1,3,5,9}.json` 与同名 feature-universe JSON：提交五套版本化引擎输入契约；每套 feature universe 均由外部引擎公开的 `canonical_feature_universe()` 生成。
- `project/tests/test_landmarks.py`：新增 pytest 参数化的波次解析、合成 schema 契约及真实 FFCWS 回归检查。
- **为保证「严格嵌套」要求而新增的行为变更**：导出器在发现相邻 landmark 的 predictor 集合没有严格增大时显式报错，不猜测为缺失波次补列；该失败路径有合成测试覆盖。

生成但按仓库规则不入 Git 的产物位于
`project/data/ard/ffc_median_mode_gpa/`：`source_wave_labels.csv`、
`unassigned_sources.csv`，以及每个 landmark 的 manifest 和 provenance。五套 schema
均回指既有的一对 GPA ARD parquet 文件。

### 验收标准逐条核对（本轮范围）

| # | 验收标准 | 结论 | 证据 |
|---|---|---|---|
| 2 | 五套 predictor 集合严格嵌套 | 满足 | `test_landmark_export_is_strictly_nested_and_excludes_future_sources` 与真实 FFCWS 回归测试均逐档断言真子集。 |
| 3 | 任一档没有晚于该档的采集波次列 | 满足 | 合成与真实回归测试均按 manifest 的 source→wave 映射逐个 predictor 断言上界。 |
| 4 | 未分配 source 显式写出且不入任何档 | 满足 | `unassigned_sources.csv` 由导出器写出；合成测试锁住该文件和 predictor 排除。 |

外部引擎的固定依赖仍为 `19890d3`，`project/requirements.txt` 未改；本轮未编辑已安装引擎或其源码。对本机另一个 `Aleatoric_Luck` checkout 的检查显示一个预先存在的未跟踪 `AGENTS.md`，因此不能把该 checkout 报为完全干净；本轮没有触碰它。

### 测试证据

- 测试要求 6：`test_derive_source_wave_labels_maps_each_supported_collection_wave`（参数化 1--5 波）和 `test_derive_source_wave_labels_keeps_unassigned_sources_separate`。
- 测试要求 7：`test_landmark_export_is_strictly_nested_and_excludes_future_sources`；另有 `test_landmark_export_rejects_an_input_without_strictly_growing_horizons` 覆盖失败路径。
- 测试要求 8：`test_real_ffcws_landmark_export_is_nested_and_has_no_future_wave_columns`。测试以真实 manifest 驱动，但所有写入均在 pytest 临时目录，且不对真实列数作断言。
- 已执行：`../.venv/bin/python -m pytest -q tests/test_landmarks.py` → **9 passed**；`../.venv/bin/python -m pytest -q` → **40 passed in 23.32s**。

### 偏离方案之处与待澄清问题

本轮对 §A 无设计偏离：波次按采集波次而非问题所指时期分配，波次 5 的回溯题仍在 9 岁档。`n_grid` / `k_grid` 的正式取值及 `preset`/算力预算仍是 §B 的待澄清问题，本轮没有创建 panel、网格或外部引擎运行。

### 未覆盖与已知风险

- 真实 FFCWS 回归测试在没有私有 ARD 产物的 checkout 会带理由跳过；本工作区已实际运行它。真实数据不是测试套件的安装前提。
- `unassigned_sources.csv` 记录所有无法从命名约定解析到 1--5 波的 source；它不会推断这些变量的内容时期。若将来出现新的合法命名约定，须先更新方案和解析规则。
- 本机外部引擎 checkout 有预先存在的未跟踪 `AGENTS.md`，所以仅能证明本轮未修改该 checkout，不能提供“干净工作树”的完整验收证据。

### 给审查者的重点

1. 请确认 `_SOURCE_WAVE_RE` 的“字母前缀后第一位数字”解释与 FFCWS 命名契约一致；它对实际 manifest 产生已验证的嵌套集合，但没有把任何现实列数写入代码或断言。
2. 请确认 landmark manifest 放在原 GPA ARD 目录的 `landmarks/` 子目录、schema 仍回指原始 parquet 的布局符合下游 panel 预期。
3. 请检查提交的五份 feature-universe JSON 是否适合纳入版本化 schema 契约；它们由外部引擎公开 API 生成，没有手写 predictor 定义。
