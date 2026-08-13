---
status: ready-for-codex
---

# 把 5→9 的台阶拆开：工具构成 vs 时间推进

批次：**独立**。依赖 `plans/ffcws-gpa-horizon-demo.md` 的 §E 全部约束（E1–E6 优先级最高）。
区间计算复用 `plans/ffcws-gpa-household-inference.md` 的 `household_inference.py`，
**本方案不重新实现推断逻辑**；若该模块尚未实现，本方案只产出逐行导出，推断留到其后。

引擎 pin：`vvcrlio-ui/Aleatoric_Luck@6a9a139`。**不触碰引擎。**

## 为什么要有这一步

pilot 的主结果是：五个 landmark 里前四个彼此分不开，落差几乎全部集中在 5→9 一步。
相邻档的家庭配对 bootstrap 差值为

| 相邻步 | 差值 | 95% CI |
|---|---|---|
| 0→1 | +0.0073 | [−0.0116, +0.0261] |
| 1→3 | −0.0021 | [−0.0201, +0.0155] |
| 3→5 | −0.0057 | [−0.0164, +0.0051] |
| **5→9** | **−0.0452** | **[−0.0627, −0.0275]** |

问题在于：**这一步上同时发生了三件事，而其中两件不是调查设计造成的。**

对照 FFCWS 官方 instrument 表与本仓库 ARD 的实测结果：

| 官方采集 | ARD 里的 source 数 |
|---|---|
| p3 / o3（Year 3 PCG 问卷 + 访员观察） | **0 / 0** |
| p4 / o4（Year 5 PCG 问卷 + 访员观察） | **0 / 0** |
| t4（Year 5 教师问卷） | **0** |
| d3 / e3 / r3 / s3 / u3（Year 3 托育机构五套） | **全部 0** |
| p5 / o5（Year 9 PCG 问卷 + 访员观察） | 352 / 96 |
| k5（Year 9 儿童自答） | 70 |
| t5（Year 9 教师问卷） | 1 |

Fragile Families Challenge 分发的 background 文件是完整 FFCWS 的**子集**（3400 个 source）：
保留了母亲、父亲、入户（`hv`）三条主线，Year 3 与 Year 5 的 PCG、访员观察、托育机构、
教师问卷全部未纳入，而 Year 9 的 PCG 与访员观察纳入了。

因此 9 岁档相对 3 岁、5 岁两档多出 450 个 source（`p5` 352 + `o5` 96 + `pcg5` 2），
**这批工具在 3 岁和 5 岁本来也采集过，只是这份文件没给**。
真正由调查设计带来的新工具只有 `k5`（儿童自答 70 个 source）——官方表确认
Child/Teen Survey 最早出现在 Year 9。

**在拆开这三者之前，5→9 的落差不能被解释为时间效应。**

## 目标

把 `R_SL(5) − R_SL(9)` 拆成三个可分别归因的部分：儿童自答、文件覆盖不对称、
以及母亲/父亲/入户三条主线随时间推进本身。

## 范围

**In scope**

- `project/src/ffcws_data_processor/landmarks.py`：新增按 (工具前缀, 波次) 排除的
  schema 导出能力，排除规则由调用方传入。
- 三份新 schema（均自 lm9 派生）+ 各自的 feature manifest。
- `project/panels.landmark.instrument.yaml`：三个 panel，只跑 `super_learner`、
  只跑 N=1165、只跑该变体的全量 K，并导出逐行预测。
- `project/tests/test_instrument_variants.py`。

**Out of scope**

- **不做**图。
- **不做**学习曲线 / 外推。
- **不改** `household_inference.py`、`learning_curve.py`、引擎、现有五份 landmark schema
  与 `panels.landmark.pilot.yaml`。
- **不做** GPA 以外的结果。
- **不做**对 lm3 / lm5 的镜像变体——`p3`/`o3`/`p4`/`o4` 在这份文件里根本不存在，
  无从排除，这正是本方案要量化的问题本身。
- **不申请**完整 FFCWS 数据（见「待澄清问题」）。

## 🔒 通用性约束

排除规则**必须由调用方传入**，形式为 `(字母前缀, 波次号)` 的集合。
`landmarks.py` 里**不得**出现 `k5` / `p5` / `o5` 这些字面量，也不得出现
"儿童自答""PCG"这类语义判断——模块只知道"按前缀和波次筛列"。
哪些前缀对应哪个工具、为什么要排除，全部留在 `panels.landmark.instrument.yaml`
的注释与本方案文档里。

## 技术方案

### I1. 工具前缀的导出

在 `landmarks.py` 新增纯函数，与既有 `source_wave_numbers()` 并列、复用同一正则
`_SOURCE_WAVE_RE`（`^[A-Za-z]+(\d)`）：

```python
def source_instrument_keys(
    source_columns: Iterable[object],
) -> dict[str, tuple[str, int]]:
    """Return (alphabetic prefix, collection wave) for each assignable source."""
```

取不到数字、或波次不在 `WAVE_LABELS` 里的 source，与 `source_wave_numbers()` 一致地
**跳过**，不猜测、不默认归属。

### I2. 变体 schema 的导出

新增公开入口：

```python
def export_instrument_variant_schema(
    *,
    dataset_dir: Path,
    schema_root: Path,
    dataset: str,
    outcome: str,
    id_column: str,
    base_landmark: int,
    variant_suffix: str,
    excluded_instruments: Collection[tuple[str, int]],
) -> Path:
```

行为：取 `base_landmark` 档的 predictor 集合，剔除所有落在 `excluded_instruments`
里的 source 所对应的建模列，其余一切（`table` / `test_table` / `split_mode` /
`imputation` / `id_column`）与基准档**完全一致**。

feature universe 仍用引擎的 `canonical_feature_universe()` 生成，不手写。
ARD 表不复制，五档与三个变体共用同一份 `data.parquet` / `test.parquet`。

`dataset` 命名为 `ffc_median_mode_gpa_lm9_<variant_suffix>`。

### I3. 三个变体

全部自 `base_landmark=9` 派生：

| suffix | 排除 | 回答什么 |
|---|---|---|
| `nokid` | `(k,5)`, `(ck,5)` | 儿童自答贡献了多少 |
| `nopcg` | `(p,5)`, `(o,5)`, `(pcg,5)` | 文件覆盖不对称贡献了多少 |
| `core` | 以上全部 | 剩下的（母亲/父亲/入户主线推进）贡献了多少 |

`core` 是本方案的核心臂：**它让 9 岁档与前四档在工具类型上真正可比**
（都只剩母亲、父亲、入户与构造变量）。若 `core` 相对 lm5 的落差仍在，
时间效应站得住；若塌了，台阶主要来自工具差异。

`ck5` 的三个 source（`ck5_kstatus` / `ck5kint` / `ck5saliva`）是儿童访问的
**参与状态标志**，随 `k5` 一同排除：它们编码"这个孩子有没有被访到"，
留着会从选择性侧门把同一批信息放回来。同理 `pcg5stat` / `pcg5idstat` 随 `p5`/`o5` 排除。

> **验证样本（不是实现目标）**：当前 lm9 有 3397 个 source / 11426 个建模列，
> wave-5 各工具的建模列数为 `p`=1331、`m`=495、`f`=283、`k`=297、`o`=264、`hv`=82、
> `cm`=76、`cf`=62、`cn`=7、`ck`=6、`pcg`=6、`cmf`=4、`t`=2、`cp`=2。
> 按上表排除后三个变体应分别得到约 11123 / 9825 / 9522 个建模列。
> **这些数字只用作回归对照，不得写成常量或断言的期望值**——
> 测试应断言嵌套关系与"排除项计数为 0"，不断言具体列数。

### I4. Panel 配置

新建 `project/panels.landmark.instrument.yaml`，**不改动**
`panels.landmark.pilot.yaml` 与 `panels.landmark.yaml`。

三个 panel，每个：

- `models: [super_learner]`——主预测器，构成见 E4，**不得**改为包络或换模型。
- `n_seeds: 4`、`n_draws: 4`（与 pilot 一致，保持蒙特卡洛噪声可比）。
- `n_grid: [1165]`——本方案只问满 N 处的分解，不问学习曲线。
- `k_grid: [<该变体的实际 source 数>]`——**逐变体不同，不得用 YAML 锚点共享**。
  取值从 I2 的导出结果读出，并用 dry-run 回显核对，不得凭上表的估计值填写。
- `prediction_export_cells: [{model: super_learner, N: 1165, K: <同上>}]`
- `preset: medium`；须确认显式 `n_grid`/`k_grid` 确实覆盖了 medium 的
  `max_n: 100` / `max_k: 100` 封顶（用 dry-run 回显核对，不要假设）。

配置须通过 `../.venv/bin/aleatoric-nk-grid-panels --manifest panels.landmark.instrument.yaml --dry-run`，
并在报告里给出 `expected_output_rows` 与 `top_level_model_cells`。

**成本估计**：3 变体 × 1 格 × 16 重复 = 48 次拟合。参照 pilot 实测
（N=1500 / K=3397 / 六模型 ≈ 228 s），预计 1–2 小时，不是整轮 13 小时。

### I5. 分解表

四个臂（`lm9` 基线复用 pilot 已有导出，不重跑）加上 lm5 基准，报告：

```
R_SL(5)                      = 0.8865   （pilot 已有）
R_SL(9, 全部)                = 0.8413   （pilot 已有）
R_SL(9, nokid)               = ?
R_SL(9, nopcg)               = ?
R_SL(9, core)                = ?
```

以及每个臂相对 `R_SL(5)` 的落差与家庭配对 bootstrap 区间（B=10000，percentile，
分母重算，先对每户 16 个损失取平均——全部沿用 E5b 与
`plans/ffcws-gpa-household-inference.md` §H1–H2 的口径，不得另立一套）。

⚠️ 三个臂的落差**相加不等于**总落差：排除的变量集之间有相关性，
不是正交分解。报告中**不得**把它们写成"贡献份额"或让它们加总到 100%，
只能各自报告"移除这组工具后落差还剩多少"。

## 验收标准

逐条可核查：

1. 引擎未被改动：`project/requirements.txt` 的 pin 与开工前一致；
   报告里给出证据。
2. 三个变体的 predictor 集合均为 lm9 的**真子集**，且嵌套关系成立：
   `P_lm5 ⊊ P_core ⊊ P_nokid ⊊ P_lm9` 且 `P_core ⊊ P_nopcg ⊊ P_lm9`。
   （`P_nokid` 与 `P_nopcg` 之间**不**要求可比，二者不嵌套。）
3. **无残留**：每个变体的 predictor 中，落在其 `excluded_instruments` 里的
   source 所对应的列数为 **0**。
4. 三个 panel 全部跑完，`status` 为 `ok` 的比例被记录；
   `constant_prediction` 的比例被记录（pilot 在 N=1165 处为 0，本方案应同样为 0，
   若不为 0 必须查明原因再继续）。
5. 逐行导出完整性：每个变体 1 格 × 16 重复 × 886 户 = **14,176 行**；
   每个 (格, 重复) 恰好覆盖全部 886 个 `row_id`；无 NaN、无重复键；
   `row_id` 与 pilot 五档的家庭集合**完全相同**（配对 bootstrap 要求各臂家庭集合一致）。
6. 由 `y_true`/`y_pred` 重算的 MSE 与主输出 CSV 的 `rmse**2` 相对偏差 < 1e-9。
7. I5 的分解表存在，五个 `R` 值与四个落差各自带点估计、区间、bootstrap SE。
8. 报告中明确写出：三个臂的落差**不构成加和分解**（见 I5 的警告）。

## 测试要求

全部 `@pytest.mark.parametrize`，合成数据，不依赖 FFCWS 的任何形状：

1. **前缀与波次解析**：参数化构造 source 名（含纯字母、字母后接多位数字、
   取不到数字、波次号超出 1–5），断言 `source_instrument_keys()` 的返回与
   `source_wave_numbers()` 在可分配集合上**完全一致**（同一正则，不得分叉）。
2. **排除生效**：合成 manifest，给定若干 `(前缀, 波次)`，断言输出集合等于
   基准集合减去被排除 source 的全部列，且顺序保持基准的相对顺序。
3. **空排除集**：传空集合时，输出与基准档**逐列相同**（含顺序）。
4. **排除不存在的工具**：传一个 manifest 里没有的 `(前缀, 波次)`，
   应正常返回基准档全集，**不得报错也不得静默产生空集**。
5. **嵌套性**：合成 manifest 上断言验收标准 2 的两条链。
6. **退化输入**：排除后 predictor 为空、manifest 缺 `source_column` 列、
   `base_landmark` 不在 `LANDMARK_WAVE_LIMITS` 里——应给出明确错误，不得静默返回。
7. **真实 FFCWS 回归检查**（缺私有数据时带理由 skip）：断言验收标准 2 与 3，
   **不断言具体列数**。

从 `project/` 跑 `../.venv/bin/python -m pytest -q`，通过数不低于当前基线加本方案新增数。

## 必须在报告中写明的表述约束

E1–E3b 全部继承，另加本方案特有的两条：

1. 各臂的 `R` 水平值只能说**"至多"**（上界），禁止"至少"。
   臂间落差与档间落差一样，**既不是上界也不是下界**（E3b）。
2. **不得**把本方案的结果表述为"台阶的 X% 来自儿童自答"。
   三个臂不是正交分解，任何百分比份额都无定义。
   允许的表述是"移除儿童自答后，5→9 的落差从 A 变为 B"。

## 待澄清问题（写入 `reports/ffcws-lm9-instrument-decomposition.md`，不得自行猜测）

1. **`cn5stat` / `cn5nint` 属于哪个工具**？官方 instrument 表的前缀清单里没有 `cn`。
   在查清之前，三个变体**一律保留**它们（保守：不排除等于把可能的增益留给 9 岁档，
   使台阶的估计偏大而非偏小）。查清后是否需要重跑，属于研究决策。
2. **`t5`（1 个 source / 2 列，Year 9 教师问卷残余）是否随 `core` 臂排除**？
   它同样是前四档没有的工具类型，按 `core` 臂的定义应当排除；
   但它只有 2 列，影响可忽略，且排除后 `core` 的含义要在报告里改写。
   本方案**默认保留**，须研究方确认。
3. **是否申请完整 FFCWS 数据发布版**（含 p3/o3/p4/o4/t4），
   把 3 岁与 5 岁两档补齐。这会使现有全部结果作废并需要新的数据使用协议，
   属于研究方向决策，不在本工作包内。

## 已完成的验证（Claude，2026-08-13，只读核验，无需重做）

1. **官方 instrument 表与 ARD 的差异已逐条核对**，见「为什么要有这一步」的表。
   `p3`/`o3`/`p4`/`o4`/`t4`/`d3`/`e3`/`r3`/`s3`/`u3` 在
   `data/ard/ffc_median_mode_gpa/feature_manifest.csv` 的 3400 个 source 中
   **一个都没有**；`hv3`/`hv4`/`hv5` 存在（284 / 265 / 49 个 source），
   对应官方表的 In-Home Activity Workbook。
2. **wave-5 各工具的 source 与建模列数**已实测，见 I3 的验证样本。
3. **相邻档差值的区间**已算出，见「为什么要有这一步」的表
   （家庭配对 bootstrap，B=10000，分母重算，先对每户 16 个损失取平均）。
4. **已知缺陷**：ridge 的 alpha 候选上限 10⁴ 在 `K_expanded ≥ 5776` 时被顶穿，
   导致独立 ridge 的误差随 N 上升（详见对话记录）。`super_learner` 内部的
   ridge 零件有同样问题且候选范围写死在引擎
   `model_registry.py:648`。本方案的三个臂 `K_expanded` 均在 9500 以上，
   **同样受影响**。因为四个臂用同一套设置，臂间比较不受系统性偏移影响；
   但绝对水平值偏高这一点必须在报告中写明。
