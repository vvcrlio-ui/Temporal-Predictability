---
status: ready-for-codex
---

# 从 ICPSR 完整 FFCWS 重建数据地基

批次：**独立，且阻塞其余全部工作包。**
本方案完成前，`plans/ffcws-gpa-horizon-demo.md` 之后的所有结果都建立在一份
被裁剪过的数据上（见下）。

引擎 pin：`vvcrlio-ui/Aleatoric_Luck@6a9a139`。**不触碰引擎**，但见 §R0 的前置条件。

## 为什么要有这一步

Fragile Families Challenge 分发的 `background.dta` 是完整 FFCWS 的一个**裁剪子集**，
而裁剪是**按波次不对称**的。实测对照（ICPSR 31622-2 vs 现用 background.dta）：

| 模块 | Challenge | ICPSR |
|---|---|---|
| p3 / o3（Y3 PCG 问卷 + 访员观察） | 0 / 0 | **535 / 102** |
| p4 / o4（Y5 PCG 问卷 + 访员观察） | 0 / 0 | **542 / 101** |
| t4（Y5 教师问卷） | 0 | **116** |
| t5（Y9 教师问卷） | 1 | **294** |
| d3 / e3 / r3 / s3 / u3（Y3 托育五套） | 全 0 | **394 / 56 / 351 / 50 / 56** |

后果：3 岁与 5 岁两档在现有数据里被系统性削弱，9 岁档没有。pilot 测到的
「5→9 一步吃掉全部落差」（−0.0452，95% CI [−0.0627, −0.0275]），其中有多少来自
真实的时间推进、多少来自这份文件的取舍，**在现有数据上无法分离**。

ICPSR 31622-2 有 19,120 个变量、4,898 个家庭，覆盖 Baseline 到 Year 22，
上述模块全部齐备。**本方案把地基换成它。**

### 为什么不做 crosswalk

ICPSR 用 `IDNUM`，Challenge 用 `challengeID`，两边无共同 ID。
用 12 个基线变量做指纹匹配，4,242 个 `challengeID` **匹配到 0 个** `IDNUM`。
诊断：类别变量分布两边一致（`cm1age` / `cm1edu` / `cm1ethrace` / `cm1bsex` 都对得上），
但连续变量被扰动——`cm1hhinc` 在 ICPSR 是 789 个唯一值、上限 133,750（整数），
在 Challenge 是 3,922 个唯一值、上限 150,102.92（浮点）。

即 Challenge 那份做了 ID 重编号加连续变量加噪。**逆转它属于去标识化的反向工程，
本方案不做**（研究方若需要官方对照表，应向 FFCWS 数据团队申请，见「待澄清问题」）。

代价：失去与 FFC 已发表 leaderboard 的直接可比性。这个代价可接受——本项目的
论点在 t 的变化上，不在 t=9 的水平，而现有 t=9 水平（`R=0.8413`）本来就比
已发表结果（约 0.80）更松。

## 目标

1. adapter 从 ICPSR 完整数据构建 ARD，每一档拿回该波次真实采集的全部工具。
2. 自建结果变量与训练/测试切分，并按 E6 把测试集拆成**开发半**与**锁定半**。
3. 五档 landmark schema 在新数据上重建，嵌套性与无越界重新验证。
4. 产出可复现的构建脚本与一份数据构建说明。

## 范围

**In scope**

- `project/config/ffc_icpsr.yaml`（新增，不改现有 `ffc.yaml`）
- `project/src/ffcws_data_processor/` 下的数据源适配、结果变量构建、切分
- `project/schema/` 下重建的五档 schema
- `project/panels.landmark.icpsr.yaml`
- 对应测试

**Out of scope**

- **不做** crosswalk / 反向识别（见上）。
- **不做** GPA 以外的结果（其余五个结果的重建留到本方案验收之后）。
- **不做** s > 15 的扩展（Year 22 数据虽在，但不在本方案内）。
- **不删除**现有基于 Challenge 文件的产物与 schema——它们作为对照保留，
  见 §R7。
- **不改**引擎。

## 🔒 前置条件与通用性约束

### R0. 先把 ridge 的修复接进本项目，再重跑

旧 `model_params.yaml` 把 ridge 的 alpha 候选定为 10⁻⁴…10⁴。实测在
`K_expanded ≥ 5776` 时该上限被顶穿（lm9 全量 K 上 4/4 次抽样选中 10⁴ 且为网格端点），
导致 ridge 的误差随 N **上升**；放宽上限后上翘消失、误差降 2.4 个百分点，
内部 CV 选中的 alpha 为 2.2×10⁴。

**上游已修复**：`Aleatoric_Luck@7ecda229e333cb1c0f1f951ff0b7d195f0dad252`
（"Expand Ridge alpha grids"）把独立 ridge 改为 10⁻⁴…10⁶ / 63 点，
并把 `super_learner` 内部原本写死的 `np.logspace(-4, 4, 50)` 改为由
`ridge_alpha_log10_min` / `ridge_alpha_log10_max` / `ridge_n_alphas` /
`ridge_scoring` 四个参数驱动，`algorithm_version` 升到 `nk-grid-v5-adapter-6`。

**本项目尚未接入**，重跑前必须完成三件事：

1. `project/requirements.txt` 的 pin 从 `6a9a139` 升到
   `7ecda229e333cb1c0f1f951ff0b7d195f0dad252`，并重装依赖。
2. `project/model_params.yaml`：ridge 段 `alpha_log10_max: 4→6`、`n_alphas: 50→63`；
   `super_learner` 段补上四个 `ridge_*` 参数；`algorithm_version` 改为
   `nk-grid-v5-adapter-6`。新引擎的参数契约校验更严
   （该 commit 给 `test_model_param_contract.py` 加了 40 行），旧配置会被拒绝。
3. 升级 pin 后按 `.system/CONTEXT_MAP.md#known-constraints` 的要求**重跑基线测试**，
   并把结果记入 `TESTS.md#verification-baselines`。

⚠️ 引擎升级会使基于 `6a9a139` 的既有结果作废——本方案本来就要重建，两者一并处理。

### R1. 数据集事实留在本仓库

ICPSR 的变量命名、波次划分、缺失码、结果变量构造规则，全部是 FFCWS 的数据集事实，
必须留在 `project/src/ffcws_data_processor/` 与 `project/config/`。
引擎只看到「一份 ARD 加若干 schema」。

## 技术方案

### R2. 数据源切换

新增 `project/config/ffc_icpsr.yaml`，与现有 `ffc.yaml` 并列，**不改动后者**。

关键差异，逐项必须显式配置、不得沿用默认：

| 项 | 现值（Challenge） | ICPSR |
|---|---|---|
| `paths.background` | `background.dta` | ICPSR `31622-0001-Data.dta` |
| `id_column` | `challengeID` | `IDNUM` |
| `paths.train` / `paths.test` | 外部 CSV | **无**，改为自建切分（§R4） |
| `split_mode` | `external_test` | 见 §R4 |
| `paths.metadata` | 无 | **新增**：`FFMetadata_v20_f.csv`（见 §R2b） |
| `missing_value_codes` | −9…−1 | −9…−1（**不变**，理由见 §R2c） |

变量名在 ICPSR 里是**大写**（`IDNUM`、`CM1AGE`），Challenge 里是小写。
读入后统一转小写，**转换必须在一处完成并有测试**，不得在多处各转一次。

⚠️ `FFMetadata_v20_f.csv` 是 **latin-1 编码**，用 UTF-8 或 cp1252 读都会抛
`UnicodeDecodeError`。编码在配置里写死并加一条读取测试。

### R2b. 波次与工具归属改用官方 metadata

`FFMetadata_v20_f.csv`（37,322 行 × 154 列）带有官方的逐变量元数据，
**取代现行的正则启发式**（`landmarks.py:34` 的 `^[A-Za-z]+(\d)`）：

| 列 | 用途 |
|---|---|
| `new_name` / `old_name` | 变量名，含改名映射 |
| `wave` | **官方波次**：`Baseline` / `Year 1` / `Year 3` / `Year 5` / `Year 9` / `Year 15` / `Year 22`（2 行为空） |
| `respondent` | 官方提问对象：Primary Caregiver 12124 / Child 10175 / Mother 6623 / Father 6112 / Child Care Provider 864 / Interviewer 632 / Teacher 418 / Couple 372 |
| `in_FFC_file` | 该变量是否在 Challenge 文件里（Yes 12662 / No 24660） |

- 波次归属**以 `wave` 列为准**。原正则降级为**交叉校验**：两者不一致的变量
  必须列入报告，不得静默采用其中一个。
- `wave` 为空的 2 行按现有约定归入 `unassigned_sources.csv`。
- `respondent` 列进入 feature manifest，供后续按提问对象做分解
  （不再需要从变量名前缀反推 `o5` 是不是访员观察——官方标了 Interviewer）。

### R2c. ≤ −10 的负值编码不是缺失值

metadata 全表统计，负值编码从 −1 一直到 −18。**但两段的语义完全不同**：

- **−1…−9**：标准缺失/跳答码（Refuse / Don't know / Missing / Multiple ans /
  Not asked / Skip / Missing lat-lon / Out of range / Not in wave）。
- **−10…−18**：**实质答案**，出现在 300 个变量里。多数是**区间回答**——
  例如户内成员年龄题 `m2f2c1`（"What is first person's age?"）的
  `-11 Newborn-15yrs` / `-12 16-21yrs` / `-13 22-30yrs` / `-14 31-50` /
  `-15 50-65` / `-16 Over 65`；另有 `-10 N/A (jail/shelter)`、
  `-17 Exchange`、`-18 Lease` 这类类别选项。

**因此不得把 −10…−18 加进 `missing_value_codes`**，那会把实质信息当缺失丢掉。

处理规则按变量类型分岔（**实测依据见「已完成的验证」第 7 条**）：

| 变量类型 | 规则 | 理由 |
|---|---|---|
| 类别（manifest `kind == "C"`） | **保持现状**，负码作为独立的 one-hot 层级 | 区间本来就是一个类别取值，信息完整保留 |
| 连续 / 序数（`kind == "X"` 等） | **≤ −10 判为缺失**，走既有插补 | "31-50" 不是连续尺度上的点值，读成数字 −14 是错的 |

该规则须在 `ffc_icpsr.yaml` 里显式配置（一个"按 kind 分岔的负码下界"参数），
**不得写死在代码里**，也不得对两类一视同仁。

### R3. 结果变量重建

FFC 的 `gpa` = Year 15 四科自报成绩的平均：
`K6B20A`（英语）、`K6B20B`（数学）、`K6B20C`（历史/社会）、`K6B20D`（科学）。

实测取值：四个变量均取 1…5 与 7，另有负值缺失码。
Challenge 的 `gpa` 实测为 **1.0…4.0、步长 0.25、n=2051、均值 2.8896、标准差 0.6592**，
13 个唯一值——这与「四个 1…4 整数取平均」完全吻合。

因此重建规则（**必须逐条验证，不得直接采信**）：

1. 反向编码 `1→4, 2→3, 3→2, 4→1`（A…D）。
2. 取值 **5 与 7 视为缺失**——若计入，最小值会低于 1.0，与 Challenge 实测的
   下限 1.0 矛盾。
3. 四科**全部有效**才计算平均；任一科缺失则结果缺失。
4. 负值一律按缺失码处理。

**验证（验收标准第 3 条）**：重建后的 GPA 边际分布须与 Challenge 的
`train.csv` + `test.csv` 中非空 `gpa` 的分布**形状一致**——同为 1.0…4.0、
步长 0.25、13 个唯一值，均值与标准差差距在合理范围内。
两份数据的家庭集合不同（4,898 vs 4,242）且不可配对，**因此只比分布，不比逐行**。
若唯一值集合或上下界对不上，说明构造规则错了，**必须阻断并报告，不得调参凑合**。

> 实测参考：ICPSR 中四科全部为非负的家庭有 3,178 个；至少一科非负的有 3,410 个。
> 排除取值 5 与 7 之后会更少。**这些数字只作对照，不得写成断言的期望值。**

### R4. 分析样本与切分（E6 的落点）

**样本**：全部具备有效重建 GPA 的家庭。**不**限制到 FFC 的 4,242 个子集——
本方案已放弃与 leaderboard 的可比性，再做这个限制只会白白丢样本。

**切分**：现有测试集已被适应性地使用过（在其上比较过七个模型、逐格取过最小、
看过曲线之后改变过分析决定），E6 因此要求拆分。本方案落实为**三分**：

| 部分 | 比例 | 用途 |
|---|---|---|
| 训练池 | **65%** | 抽 N、训模型 |
| **开发半** | **17.5%** | 全部模型比较、设计判断、诊断、调参 |
| **锁定半** | **17.5%** | **最终数字只在其上报告一次** |

比例由研究方于 2026-08-13 定为 65 / 17.5 / 17.5（保持 65/35 的训练-留出总比，
留出部分对半分以落实 E6）。

⚠️ **代价必须在报告中写明**：两个半各约 600 户（按有效 GPA 家庭数估算），
比现有 886 户的测试集小，**区间会比现在宽**。这是为控制适应性过拟合付出的代价，
不是缺陷。

- 比例与随机种子写进 `ffc_icpsr.yaml`，**一次定死，之后不得更改**。
- 切分必须可复现（显式 seed，不用全局随机数）。
- 引擎的 `split_mode` 用 `external_test`，由本仓库产出 train/test 表，
  沿用现有机制，**不改引擎**。
- 开发半与锁定半作为两份独立的 test 表产出；正式网格先只跑开发半。

⚠️ **锁定半在本工作包内不得被读取、不得进入任何统计输出。**
验收标准第 6 条对此有可核查的要求。

### R5. 泄漏防护

波次归属改用 metadata 的 `wave` 列（§R2b）。这同时解决了命名不一致的问题——
入户/儿童测评那一块在 Challenge 里叫 `hv3`/`hv4`/`hv5`，在 ICPSR 里
`hv3`/`hv4`/`hv5` **全部为 0**，对应的是 `ch3`（770）与 `ch4`（858）；
靠正则猜前缀无法处理，靠官方 `wave` 列则不需要处理。

landmark 与 `wave` 取值的对应：

| landmark | 允许的 `wave` 取值 |
|---|---|
| 0 | Baseline |
| 1 | + Year 1 |
| 3 | + Year 3 |
| 5 | + Year 5 |
| 9 | + Year 9 |

**新增的硬约束——泄漏防护（Challenge 文件里不存在这个风险）：**

ICPSR 覆盖到 Year 22。metadata 中 `wave` 为 `Year 15`（10,960 个变量，
**结果就在这一波**）与 `Year 22`（4,511 个）的变量合计 15,471 个。
旧数据止于 Year 9，所以从来不需要防这一手。

- **predictor 端必须只含 Baseline…Year 9。** `Year 15` 与 `Year 22` 的变量数
  在每一档中必须为 **0**，且这是一条**独立的、显式的**断言，
  不能只依赖「landmark 上限是 Year 9」这一条间接保证。
- 结果变量 `K6B20A–D` 本身属于 Year 15，被上一条自动排除；
  但仍须单独断言它们不出现在任何一档的 predictor 里。
- `wave` 为空或取不到波次的 source 一律排除并写入 `unassigned_sources.csv`，
  不得猜测归属。

嵌套性与无越界（主方案验收标准 2、3）在新数据上重新断言：
`P_0 ⊊ P_1 ⊊ P_3 ⊊ P_5 ⊊ P_9`，且第 t 档中采集波次 > t 的列数为 0。

### R6. schema 与 panel

五档 schema 按现有 `export_landmark_schemas()` 的机制重建，`dataset` 命名加
`_icpsr` 后缀以与现有产物区分（例：`ffc_icpsr_median_mode_gpa_lm0`）。

`project/panels.landmark.icpsr.yaml`：结构照抄 `panels.landmark.pilot.yaml`，
但 `n_grid` 上限与 `k_grid` 的全量值**必须从新 ARD 实测得出**，
不得沿用 1165 / 351·848·1701·2506·3397 这组旧数字。
须通过 `--dry-run` 并在报告里给出 `expected_output_rows` 与 `top_level_model_cells`。

### R7. 旧产物的处置

现有基于 Challenge 文件的 schema、panel 配置与 pilot 输出**保留不动**，
作为「文件裁剪造成多大偏差」的对照。报告中须说明两套结果不可直接比较
（样本、切分、结果变量构造均不同）。

`plans/ffcws-lm9-instrument-decomposition.md` 在本方案验收后**降级为可选**——
它测量的偏差，本方案在源头上消除了。是否仍跑那三个臂作为对照，
属于研究决策（见「待澄清问题」）。

## 验收标准

逐条可核查：

1. 引擎 pin 已升到 `7ecda229…`，依赖已重装，`model_params.yaml` 的
   `algorithm_version` 为 `nk-grid-v5-adapter-6` 且 ridge 与 super_learner 的
   alpha 参数与 §R0 一致；基线测试已重跑并记入 `TESTS.md`。
   **引擎源码本身未被编辑**（只升 pin），报告里给出证据。
2. `missing_value_codes` 仍为 −9…−1；≤ −10 的负码按 §R2c 的分岔规则处理，
   报告中给出受影响的变量数、按 `kind` 的分布，以及连续列里被判为缺失的单元格数。
3. 重建 GPA 的边际分布与 Challenge 的 `gpa` **形状一致**：同为 1.0…4.0、
   步长 0.25、13 个唯一值；均值与标准差一并报告。对不上即阻断。
4. 五档 predictor 集合**严格嵌套**，且第 t 档中 `wave` 晚于该档的列数为 0。
5. **`Year 15` 与 `Year 22` 的变量在任何一档的 predictor 中计数为 0**，
   `K6B20A–D` 单独断言不出现。这两条是独立断言。
5b. metadata 的 `wave` 列与原正则启发式的**不一致清单**已产出并写进报告
   （允许不一致，但必须逐条列出，不得静默采用其中一个）。
6. **锁定半未被读取**：本工作包产出的任何 CSV / JSON / 日志中，
   都不含锁定半家庭的任何统计量。可用「锁定半的行数在全部输出中从未出现」
   加代码走查双重确认，报告中说明确认方式。
7. 未分配 source 全部落在 `unassigned_sources.csv`，且不出现在任何一档里。
8. 五档的 K（全量）与训练池行数为实测值，与 dry-run 回显一致。
9. 数据构建说明写入 `reports/ffcws-icpsr-rebuild.md`，含：
   变量总数、家庭数、各档 source 与建模列数、结果变量构造与验证结果、
   切分比例与 seed、被排除的 source 数与原因分布。

## 测试要求

全部 `@pytest.mark.parametrize`，合成数据为主，真实数据只作回归检查：

1. **大小写归一**：构造大小写混合的列名，断言归一在一处完成且幂等。
2. **缺失码的两段语义**：参数化 −9…−1，断言全部被识别为缺失；
   参数化 −18…−10，断言**类别列保留为独立层级**、**连续列判为缺失**；
   断言正数与 0 不受影响。这条必须覆盖两个分支，只测一边不算通过。
2b. **metadata 读取**：断言用 latin-1 读成功、用 UTF-8 读会抛
   `UnicodeDecodeError`（锁住编码，防止有人"顺手"改成 UTF-8）。
2c. **波次以 metadata 为准**：构造 `wave` 列与变量名前缀冲突的合成样例，
   断言取 `wave` 列的值，且冲突被记录到不一致清单里而非静默丢弃。
3. **结果变量构造**：参数化构造四科取值（含 5、7、负值、部分缺失），
   断言反向编码正确、5 与 7 判为缺失、任一科缺失则结果缺失、
   取值落在 1.0…4.0 且步长 0.25。
4. **泄漏防护**：合成 manifest 含 wave 6/7 的 source，断言它们在**每一档**
   都被排除；再单独断言结果变量所在列被排除。**这条必须独立于波次上限逻辑**——
   即使有人把 landmark 上限误设为 7，这条也应拦住。
5. **切分可复现**：同一 seed 两次切分结果相同；不同 seed 不同；
   三部分互不相交且并集为全样本。
6. **锁定半隔离**：构造一个会读取锁定半的调用，断言被显式拒绝或有记录地跳过，
   **不得静默通过**。
7. **嵌套性与无越界**：合成 manifest 上断言验收标准 4。
8. **真实 ICPSR 回归检查**（缺数据时带理由 skip）：断言验收标准 3、4、5，
   **不断言具体列数或家庭数**。

从 `project/` 跑 `../.venv/bin/python -m pytest -q`，通过数不低于当前基线加本方案新增数。

## 表述约束

E1–E3b 全部继承。另加：

1. 本方案产出的结果与现有 Challenge 版结果**不可直接比较**（样本、切分、
   结果变量构造均不同），报告中不得并排给出两套数字而不加说明。
2. 换到完整数据后，各档的 `R` 是**更紧的上界**，但仍然只是上界，
   仍然只能说「至多」。
3. 各档信息集在工具类型上**依然不同**（托育问卷只在 Y3、教师问卷在 Y5 与 Y9、
   儿童自答从 Y9 起）。这是调查设计的真实特征，不再是文件裁剪的产物，
   但**仍须在报告中披露**，不得因为「用了完整数据」就宣称各档已经可比。

## 待澄清问题（写入 `reports/ffcws-icpsr-rebuild.md`，不得自行猜测）

1. **是否向 FFCWS 数据团队申请官方 ID 对照表**。若拿得到，可在完整数据上
   复现 FFC 的官方切分，恢复与 leaderboard 的可比性。这不改变本方案的其余部分。
2. **`plans/ffcws-lm9-instrument-decomposition.md` 是否仍作为对照跑**（§R7）。
3. **其余五个结果何时重建**。按 E4 的表，它们只在**尚未查看结果时**才能
   预注册为确认性分析——重建是重新开始的机会，值得先定下来。
4. **是否向 Aleatoric_Luck 提两条通用改进**（不阻塞本方案）：
   选中的 alpha 落在候选网格端点时在输出里加标记；候选范围与数据规模挂钩
   而非固定数字。7ecda22 把上限抬到 10⁶ 解决了当前数据，但换个规模的数据集
   仍会再撞一次。

> 已解决，不再是待澄清：ridge 的 alpha 上限（上游 7ecda22 已修，本方案 §R0
> 负责接入）；切分比例（研究方 2026-08-13 定为 65 / 17.5 / 17.5）；
> ≤ −10 负码的处理（§R2c，按 `kind` 分岔）。

## 已完成的验证（Claude，2026-08-13，只读核验，无需重做）

1. **模块缺失对照**已逐条实测，见「为什么要有这一步」的表。
2. **ID 不可配对**：12 个基线变量指纹匹配 0/4242；诊断为连续变量加噪
   （`cm1hhinc`：ICPSR 789 个唯一值 / 上限 133,750 整数，
   Challenge 3,922 个唯一值 / 上限 150,102.92 浮点）。
   类别变量分布两边一致。
3. **规模**：ICPSR 19,120 变量 / 4,898 家庭；Challenge 12,943 变量 / 4,242 家庭。
4. **wave 6/7 泄漏面**：3,753 个变量。
5. **结果变量线索**：`K6B20A–D` 四科成绩；Challenge `gpa` 实测
   1.0…4.0 / 步长 0.25 / n=2051 / 均值 2.8896 / 标准差 0.6592 / 13 个唯一值。
6. **ridge alpha 缺陷**已定位：不是引擎从 5 折改留一法引入的
   （两种设置实测结果相同），而是 `model_params.yaml` 的候选上限 10⁴ 过低。
   上游 `7ecda22` 已修，本项目未接入（`requirements.txt` 仍 pin `6a9a139`，
   venv 里的 `model_registry.py:648` 仍是 `np.logspace(-4, 4, 50)`，
   `model_params.yaml` 的 ridge 段未动）。
7. **≤ −10 负码在现有数据里的实际影响已量化**：metadata 中带这类码的变量
   300 个，其中 102 个进入了当前建模 manifest，对应 466 个建模列；
   按 `kind` 分为 **453 个类别列**（负码成为独立 one-hot 层级，处理正确）
   与 **13 个连续列**。连续列里实际仍带 ≤ −10 取值的有 12 列，
   合计 **105 个单元格，占全部连续单元格的 0.0138%**。
   受影响的都是户内成员年龄题（`m2f2c1` / `f3f2c1` / `m3f2c2` / `f4f2c1` 等，
   "What is first person's age?"）与 `m2f1`（`-10 N/A (jail/shelter)`）。
   **对现有 pilot 结果的影响可忽略，不构成单独重跑的理由**，但规则须按 §R2c 改正。
8. **metadata 的 `wave` / `respondent` / `in_FFC_file` 三列已核实可用**，
   取值分布见 §R2b。
9. **`FFMetadata_v20_f.csv` 的编码是 latin-1**：UTF-8 在偏移 176829 处、
   cp1252 在偏移 4512 处均解码失败。
