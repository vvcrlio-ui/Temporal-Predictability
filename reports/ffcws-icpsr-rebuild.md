---
status: needs-review
---

# ICPSR 数据重建实施说明

## 构建结果

- 输入为 `project/data/private/ffcws_icpsr.dta` 与
  `project/data/private/FFMetadata_v20_f.csv`。完整数据有 19,120 个变量和
  4,898 个家庭。
- `project/config/ffc_icpsr.yaml` 使用 `ffcws-adapter-v2`；
  `project/config/ffc.yaml` 保持 `ffcws-adapter-v1`。适配器会把版本写入
  ARD provenance，并在写出前拒绝将一个版本的输出写入另一个版本的产物树。本轮真实数据
  重跑后，正式 ARD 与五个 landmark 的 `provenance.json` 都含有
  `contract_version: ffcws-adapter-v2`。
  读取 Stata 后，ICPSR 列名在入口一次性转为小写；metadata 固定用 latin-1 读取。
- v1 是 Challenge 路线：主键为 `challengeID`，训练/测试来自官方 CSV；v2 是 ICPSR
  路线：主键为 `IDNUM`，训练池、开发半和锁定半由完整 ICPSR 数据自建，且 `≤−10`
  负码按变量类型分岔。因此两版的 ARD、schema、manifest 和 provenance 不能互换。
  ICPSR 正式路径为 `project/data/ard_icpsr/ffc_icpsr_median_mode_gpa/`，schema 为
  `project/schema/ffc_icpsr_median_mode_gpa*.json`；现有 Challenge ARD、schema 与
  pilot 输出没有被替换。
- 有两处未引用的重复 ARD，均含 `locked_test.parquet`，本次均未删除，避免未经研究方
  确认销毁私有数据：
  `project/data/ard_icpsr/ffc_median_mode_gpa/`，以及嵌套在正式目录内的
  `project/data/ard_icpsr/ffc_icpsr_median_mode_gpa/ffc_median_mode_gpa/`。
  后者的 provenance 标为 `ffc_median_mode_gpa`，且 `data.parquet` 与第一处的 SHA-256
  相同。其成因是 pipeline 的 `dataset_dir = ard_root / dataset`：一次 v1 命名的写出把
  `ard_root` 指到了 v2 正式数据集目录。当前默认配置没有该路径；新增的版本边界检查会在
  读入数据前拒绝这类嵌套跨版本写入。本轮重跑后嵌套目录仍存在，因为它按要求保留；其
  `data.parquet` 时间仍为 15:18:33，而正式 `data.parquet` 已更新为 17:15:14，证明本轮
  没有再次生成该副本。
- ICPSR 读取时跳过 Stata 值标签，避免为标签再读一次约 289 MB 的 `.dta`。这不影响类别
  处理：schema 按原始数值层级、有效率和训练池频率确定类别，不依赖标签文本。
- GPA 有效家庭按 seed `20260813` 以 65% / 17.5% / 17.5% 分为训练池、开发半和
  锁定半。整数行数按最大余数法分配；该规则只解决比例不能精确表示为整数时的余数，
  不改变配置比例。
- 真实数据重跑后的训练表有 1,843 行，开发测试表有 496 行，锁定半也有 496 行。五档的
  `(source 数, K)` 分别为：
  lm0 `(526, 1475)`、lm1 `(1194, 3484)`、lm3 `(2568, 7371)`、lm5
  `(3939, 11091)`、lm9 `(5851, 16172)`。

## GPA 构造与负码处理

`k6b20a` 至 `k6b20d` 均按 `1→4、2→3、3→2、4→1` 反向编码；5、7 和负值均视为
缺失，四科齐全才取平均。切分前的重建 GPA 有 2,835 个有效值，范围 1.0–4.0，步长
0.25，13 个唯一值，均值 2.8968，标准差 0.6539。Challenge 版对应值为 2,051 个、
均值 2.8896、标准差 0.6592，范围、步长和唯一值数相同，因此构造规则通过边际分布
核验。本轮真实数据重跑复算后，这些 ICPSR 数字均未变化。

`-9` 至 `-1` 仍是唯一全局缺失码。最终 schema 中，含 `≤−10` 值的类别 source 有
111 个、18,691 个单元格，作为独立 one-hot 层级保留；连续 source 有 15 个、233 个
单元格，按 `continuous_negative_missing_threshold: -10` 交给既有插补处理。这些数值已由
本轮重跑后的 schema 和原始数据重新核对，未变化。

`≤−10` 阈值在类型判定之后才施加是有意的：先用原始数值决定 source 是类别还是连续，
才能让已被判为类别的区间码保留为独立层级；只有连续 source 才把该区间视为缺失。边界
变量的原始层级数会影响类别/连续判定，这一行为已有回归测试固定：16 个原始整数层级
（包括 `-10`）超过 `categorical_max_levels: 15` 时，source 保持连续且编码时掩蔽 `-10`。

## 波次、泄漏与锁定半

波次以官方 metadata 的 `wave` 为准。所有 15,366 个 Baseline–Year 9 候选 source
均能匹配 metadata；变量名前缀正则与官方波次没有不一致项，未分配 source 为 0。
五个 landmark 的预测变量严格嵌套；每一档的 `Year 15`、`Year 22` predictor 数均为
0，`k6b20a`–`k6b20d` 也均为 0。本轮重跑后的五份 manifest 复核结果相同。

正式 schema 的 `test_table` 只指向开发半。锁定半只写入独立
`locked_test.parquet`；构建过程必须读取它以写出该表，但没有 schema、QA、JSON、CSV 或
日志记录它的 ID、行数或统计量。本工作包没有运行锁定半评估。集成测试会扫描
`output_root` 下全部 CSV/JSON，以及 `ard_root` 内除 `locked_test.parquet` 外的全部
CSV/JSON，断言其中不含锁定半标识或 ID。

完整数据消除了 Challenge 文件的波次裁剪，但不同波次的工具类型仍不相同，例如托育、
教师与儿童自答问卷的采集时间不同。因此 ICPSR 与 Challenge 结果不能直接比较：样本、
切分和结果变量构造都不同。

## 引擎与 panel 预检

`requirements.txt` 固定到 `Aleatoric_Luck@7ecda229e333cb1c0f1f951ff0b7d195f0dad252`；
`model_params.yaml` 使用 `nk-grid-v5-adapter-6`、ridge `10^-4..10^6 / 63`，并为
super learner 提供相同的 ridge 参数。仓库没有引擎源码修改。

完整 lm9 端点的 K 为 16,172，高于训练 N。`ffc_icpsr.yaml` 因此将构建期验证明确设为
`schema_only`：adapter 使用引擎 `load_input` 读取 ARD 与 schema，随后五档 schema 都
再次成功加载；不在数据构建过程中运行临时 OLS 拟合。模型拟合属于后续 panel 运行，
不会用“通过”替代实际模型计算。

本轮正式 `data.parquet` 的 16,172 个预测列均为 float64。float32 改回 float64 改变了
特征表的数据类型与内容身份哈希，但没有改变训练/开发/锁定切分、GPA、source 筛选、各档
K 或任何本报告列出的计数。

`project/panels.landmark.icpsr.yaml` 只声明每档实测的全量 `(N, K)` 端点。dry-run 对
每个 panel 给出 112 个 `expected_output_rows` 和 112 个 `top_level_model_cells`，五档
合计 560。它不是完整学习曲线网格。

## 待澄清问题

1. 是否向 FFCWS 数据团队申请官方 ID 对照表，以恢复与 leaderboard 的可比性？
2. `plans/ffcws-lm9-instrument-decomposition.md` 是否仍作为可选对照运行？本次没有实现它。
3. 其余五个 outcome 何时重建？确认性分析的预注册时点需要先确定。
4. 是否向 Aleatoric_Luck 提出 alpha 端点标记和随数据规模调整候选范围两项通用改进？
5. 后续正式网格的中间 `N` 与 `K` 档位尚未在本计划中定义。当前 panel 只使用实测
   全量端点；在运行学习曲线前应明确每档的中间网格与计算预算。

## 实际验证

- `../.venv/bin/python adapter.py --config config/ffc_icpsr.yaml`：使用真实私有 ICPSR
  数据完成，退出码 0。
- `../.venv/bin/python -m pytest -q`：79 passed（25.27s）。
- `../.venv/bin/python -m compileall -q adapter.py src tests`：通过。
- `../.venv/bin/aleatoric-nk-grid-panels --manifest panels.landmark.icpsr.yaml --dry-run`：
  五个 panel 均通过；每个 panel 预计 112 行输出与 112 个顶层模型单元，合计 560。

## 实现说明（第 2 轮）

1. **R1-1 契约版本**：ICPSR 配置改为 v2，Challenge 配置保持 v1。v1/v2 都有端到端
   覆盖，provenance 记录对应版本；测试同时验证 v1 不能写入 v2 ARD 目录。
2. **R1-2 锁定半**：删除未接入生产路径的 `reject_locked_test_analysis()` 及其循环论证
   测试。保留独立的 `locked_test.parquet`，并改为检查真实构建输出中没有锁定半披露。
3. **R1-3 残留目录**：已确认嵌套目录来自错误的 `ard_root` 与 v1 dataset 名称组合，非
   landmark 导出器复制表所致。版本边界检查阻止同类路径再次写入；两处既有数据均保留。
4. **R1-4 精度**：`median_mode` 的两处转换已恢复 float64，Challenge v1 的数值精度不再
   因本工作包改变；测试断言连续和 one-hot 编码均为 float64。
5. **R1-5 负码阈值**：见“GPA 构造与负码处理”的有意设计和边界回归测试说明。
6. **R1-6 Stata 标签**：见“构建结果”的读取说明；数值层级而非标签文本决定类别处理。

## 实现说明（第 3 轮）

1. **R2-1 真实重跑与重验**：已用 `project/data/private/` 的 ICPSR 数据重跑 adapter，再以
   新 schema 重跑五个 panel 的 dry-run。各档 `(source 数, K)` 仍为 lm0 `(526, 1475)`、
   lm1 `(1194, 3484)`、lm3 `(2568, 7371)`、lm5 `(3939, 11091)`、lm9 `(5851, 16172)`；
   训练/开发/锁定分别为 1,843/496/496；GPA 为 n=2,835、1.0–4.0、13 个唯一值、均值
   2.8968、标准差 0.6539。没有计数变化，因此无需另行解释；float64 只改变了数值 dtype
   与内容身份哈希。正式和五个 landmark provenance 均为 v2。嵌套残留仍在，但文件时间
   早于正式重跑产物，说明没有再次生成。
2. **R2-2 锁定半扫描范围**：合成 ICPSR 集成测试现在扫描 `output_root` 的全部 CSV/JSON，
   以及 `ard_root` 内除 `locked_test.parquet` 外的全部 CSV/JSON；两处均断言不存在
   `locked` 标识或锁定半 ID。
