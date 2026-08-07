---
status: ready-for-codex
---

# GPA 可预测性视野曲线（demo）：按波次嵌套的信息集 + 学习曲线渐近线

> **研究层级说明（2026-08-07）**：本文件只定义第一阶段的 GPA 方法 demo，
> 不是整个项目的研究目标。完整研究将为每个结果构建“联合数据规模（N 与 K
> 联动）× 观察波次 × 样本外预测表现”曲面，并以本 demo 验证的固定-K学习曲线
> 作为诊断和渐近上界估计工具。总体研究定义见根目录 `README.md`。

批次：**独立**。不依赖 `pilot-run` / `parallelism-utilization`（那两份方案属于
Aleatoric_Luck 仓库，与本仓库无关）。

> **仓库归属说明(2026-08-07)**：本方案原写于 `Aleatoric_Luck` 仓库，现独立到
> `vvcrlio-ui/Temporal-Predictability`。**引擎源码不在本仓库内**：
> `aleatoric_nk_grid` 由 `project/requirements.txt` 固定到
> `vvcrlio-ui/Aleatoric_Luck@19890d3` 的 `NK_Grid` 子目录，作为普通 pip 依赖安装。
> 本文档下文若出现引擎模块名，指的都是该已安装的包，**不是本仓库的目录**。
> 凡涉及"改引擎"的边界，一律理解为"不得改动固定的引擎 commit，也不得就地编辑
> 已安装的包或 `Aleatoric_Luck` 本机 checkout"。

基线：`main @ 891f652` — `../.venv/bin/python -m pytest -q` → **10 passed**
（已记入 `TESTS.md#verification-baselines`，无需重跑）。若开工时 `main` 已推进，
在新版本上实跑一次并追加记录。

## 为什么要有这一步

van de Rijt et al. (2026, *Annual Review of Sociology* 52:319–339) 第 6 页定义了

$$\text{Unpredictability}(t,s) = \frac{\mathbb{E}[\mathrm{Var}(Y_s \mid H_{\le t})]}{\mathrm{Var}(Y_s)}$$

**这个量有两个下标，但那篇文章只在 $(t,s)=(9,15)$ 一个点上取过值**——因为
Salganik et al. (2020) 的锦标赛只提供了那一个上界。

本方案把 $t$ 变起来：固定 $s=15$（GPA），让 $t$ 取 FFCWS 的五个采集波次
（出生、1、3、5、9 岁），每个 $t$ 只用截至该波可得的变量，估计一条曲线而不是一个点。

**这是一次 demo，产出是一张图**，用于对外沟通。不是完整研究。

### 为什么不能直接用最大 N 处的误差当答案

因为五个信息集的**变量数差约 10 倍**（实测见下表），而训练行数在五档里都是同一个
上限。变量多的那档离收敛更远，其误差里掺进了更多"样本不够学不动"的成分。
直接比较五档在最大 N 处的误差，比的是"五档各自离收敛有多远"，不是"五个信息集
谁更能预测"。

**外推到学习曲线的渐近线，就是把这部分剥掉，使五个数可比。** 这是本方案里
唯一的新代码，也是唯一的风险点。

## 目标

1. 让 FFCWS adapter 能按采集波次产出**严格嵌套**的五套 schema（不改引擎）。
2. 在这五套 schema 上跑外部 N×K 引擎，得到每档的 (N, K) 误差网格。
3. 新增一个 **article-agnostic** 的学习曲线渐近线估计模块，把网格化成五个
   带区间的标量。
4. 产出一张图 + 一份数值表 + 一份方法说明。

## 范围

**In scope**

- FFCWS adapter：从 manifest 的 `source_column` 确定性导出波次标签，
  按波次产出五套嵌套 schema + feature universe。
- `project/panels.landmark.yaml`：五个 landmark × GPA 的 panel 配置。
- 本仓库新增模块 `project/analysis/learning_curve.py`：从引擎输出的 (N, error) 拟合
  带渐近项的曲线，输出渐近线点估计 + bootstrap 区间 + 外推自检。
- 绘图与数值表脚本（放 `project/figures/`，不进引擎）——**详见 `plans/ffcws-horizon-figures.md`，本方案 §D 已被其取代**。

**Out of scope**

- **不做**按 SES 分层（那是 demo 之后的事）。
- **不做** GPA 以外的五个结果。
- **不做**跨数据集、跨国。
- **不做**因果事件研究的下界。
- **不做**三套插补策略的比较：本 demo 固定 `median_mode` 一套。
- **不动引擎的抽样、切分、预处理、模型逻辑**。
- **不编辑引擎源码**——它作为固定 commit 的 pip 依赖安装，不在本仓库内
  （见上方仓库归属说明）。`learning_curve.py` 落在本仓库 `project/analysis/` 下
  （见 §C 开头的路径变更），是纯新增的下游分析层，只通过公开 API
  （`canonical_feature_universe()` 等）与 CSV 输出与引擎交互，不 import 其
  内部私有符号。

## 🔒 通用引擎约束在本方案中的落点

- **波次是 FFCWS 的数据集事实，必须全部留在本仓库 `project/src/ffcws_data_processor/`。**
  这条约束现在由仓库边界自动保证——引擎根本不在本仓库里，不存在"不小心
  写进引擎"的可能。引擎看到的只是"五份不同的 schema"，与它看到
  "五个不同的数据集"没有区别。
- **`learning_curve.py` 必须是通用的**：输入是"一列 N、一列误差、可选的分组列"，
  对任意来源的网格都成立。不得引用 FFCWS 的列数、行数、波次数量。
  测试矩阵参数化生成。

## 技术方案

### A. 波次划分（`project/src/ffcws_data_processor/`）

#### A1. 波次标签的导出规则

在 `ffcws_data_processor` 下新增一个纯函数，输入是 `feature_manifest.csv` 的
`source_column` 列，输出 `{source_column: wave_label}`。

规则：取 source 名里**字母前缀之后的第一个数字**作为波次编号。
FFCWS 的命名约定里该数字即采集波次（`m1`=出生母亲问卷，`m2`=1 岁，`hv3`=3 岁入户，
`cm1`=出生构造变量，`p5`/`k5`/`t5`=9 岁）。

映射：`1→出生`、`2→1 岁`、`3→3 岁`、`4→5 岁`、`5→9 岁`。

**取不到数字的 source 一律排除，并写进 `unassigned_sources.csv`。**
不得猜测归属，不得默认丢进某一波。

**必须按采集波次归类，而不是按变量内容所指的时期。** 波次 5 收集的回溯性问题
（问的是更早发生的事）仍然归 9 岁档——因为在 3 岁那个观察位点上，
研究者确实拿不到它。这个方向是保守的，不要"优化"。

> **验证样本（不是实现目标）**：当前 `ffc_median_mode_gpa` 的 11432 个建模列
> 按此规则应得到 1158 / 1709 / 2909 / 2733 / 2917 列，6 列取不到数字。
> 这五个数用作回归检查，**不得写成常量或断言的期望值**——
> 测试应断言"五档严格嵌套且无越界列"，而不是断言具体数字。

#### A2. 产出五套嵌套 schema

landmark $t \in \{0,1,3,5,9\}$，第 $t$ 档的 predictor 集合 =
所有采集波次 $\le t$ 的 source 所对应的建模列。

对每档产出：
- 一份 feature universe JSON（用引擎的 `canonical_feature_universe()` 生成，不手写）
- 一份 schema JSON，`dataset` 命名为 `ffc_median_mode_gpa_lm{t}`
- 一份该档的 `feature_manifest.csv`

ARD 表本身**不复制**：五档共用同一份 `data.parquet` / `test.parquet`，
只有 `predictor_columns` 不同。

保持 `split_mode: external_test`，沿用 FFC 官方切分，不要自建切分。

### B. Panel 配置（`project/panels.landmark.yaml`）

新建文件，不改动现有 `panels.yaml`。

五个 panel，各指向 A2 产出的一套 schema，`outcome: gpa`。

**显式网格**（引擎已支持 `n_grid` / `k_grid`，见 `nk_grid.py:1612,1618`；
若 panel 层尚未透传，本方案包含透传）：

- `n_grid`：从下界到该 outcome 的可用训练行数上限，对数间隔，
  **末端加密**（最后三个点必须落在上限的 40% / 70% / 100%），
  否则看不出尾部平没平。
- `k_grid`：**两组**，都在同一个 panel 里跑：
  - `K = 全部可用`（该档的实际信息集，主结果）
  - 三个**跨档共同的** K 值（必须 ≤ 最小档的 source 数），用于在
    变量数被匹配的条件下比较五档。

**模型**：`ridge, lasso, random_forest, extra_trees, xgboost, lightgbm, super_learner`。

**排除 `ols`**：K > N 时欠定，实测在 dev 网格上表现为 N 增大而误差反增
（K=100 时 N=10→100 的 RMSE 由 0.671 升到 0.871）。
`shallow_neural_network` 可保留但预期不进入包络。

`preset` 用 `medium` 起步；`production` 需要另行评估算力，不在本方案内。

### C. 渐近线估计（`project/analysis/learning_curve.py`，本仓库内新增）

> 原方案把这个模块放在引擎包内部；现在引擎是外部依赖，模块改放本仓库
> 自己的 `project/analysis/` 下。功能不变——它本来就只读 `(N, error)` 数值，
> 不依赖引擎内部实现，搬家不影响 C1–C5 的任何逻辑。

#### C1. 拟合

对每个 (dataset, model, K) 组合，把各 N 上跨 seed/draw 的误差**中位数**
作为该 N 的观测点，拟合

$$\text{err}(N) = \varepsilon^2_\infty + a \cdot N^{-b}, \qquad a>0,\ b>0,\ \varepsilon^2_\infty \ge 0$$

参数由配置传入，**不得硬编码**：

- 误差列名（默认 `rmse`，须支持传 `mse` / `1-r2` 等）
- 是否先平方（RMSE → MSE 后再拟合；渐近线定义在方差尺度上）
- 备选函数形式：至少同时提供**幂律**与**指数** `ε²∞ + a·exp(-bN)`，
  两者都拟合并都输出，供比较

**同时输出"包络"**：在每个 N 上取各模型误差的逐点最小值，对这条包络
再拟一次。包络的渐近线是该档最紧的上界估计。

#### C2. 外推自检（**必做，是本方案的验收核心**）

只用 $N \le N_{\text{cut}}$ 的点拟合（$N_{\text{cut}}$ 由配置给出，默认取
可用 N 的中位数），然后**预测最大 N 处的误差**，与实测值比较。

输出 `predicted`、`observed`、相对偏差。

**这是判断外推可不可信的唯一证据。** 偏差大就说明函数形式不对，
渐近线不能用——此时必须在报告里明说，不得只报渐近线。

#### C3. 区间

对 seed 做 bootstrap（重抽 seed，不是重抽 cell），每次重跑 C1，
输出渐近线的分位数区间。bootstrap 次数可配。

#### C4. 单调化

同一 outcome 下，五档的渐近线按 $t$ 递增必须**不上升**
（信息集嵌套 ⟹ 条件方差不增）。

输出**两份**：原始估计 + 保序回归（isotonic）之后的估计。
**不要只输出单调化之后的**——原始值里的违反是诊断信息。

#### C5. 归一化

最终报告的量是 $\hat U(t) = \hat\varepsilon^2_\infty(t) / \widehat{\mathrm{Var}}(Y_{\text{test}})$，
与 van de Rijt 的定义一致。方差从测试集实测，不从训练集。

### D. 产出（`project/`，不进引擎）

> ⚠️ **本节已被 `plans/ffcws-horizon-figures.md` 取代，不要按本节实现。**
> 那份方案接管全部图与判读层（学习曲线图、Û(t) 图、(t,N) 曲面、顺序翻转检查、
> 外推失信时的降级),并沿用同一分支 `codex/ffcws-gpa-horizon-demo`。
> 本节以下三条保留作为背景,验收以那份方案的验收标准为准。

1. **一张图**：横轴观察年龄 $t\in\{0,1,3,5,9\}$，纵轴 $\hat U(t)$，
   带 bootstrap 区间；主结果（全部 K）为实线，匹配 K 的三条为虚线。
2. **一份 CSV**：五档 × {原始, 单调化} × {幂律, 指数} × {全部K, 三个匹配K}
   的点估计与区间，外加 C2 的自检数值。
3. **一份方法说明** `reports/ffcws-gpa-horizon-demo.md`，含：
   实际用的 N/K 网格、模型集合、被排除的 source 数、C2 自检结果、
   以及**尾部平没平的判断**。

## 验收标准

逐条可核查：

1. 外部引擎未被改动：`project/requirements.txt` 中固定的引擎 commit 与开工前一致，
   且 `Aleatoric_Luck` 本机 checkout 的 `git status` 干净（报告里给出输出作为证据）。
   若 panel 层 `n_grid`/`k_grid` 透传确需修改引擎代码，须作为待澄清问题单列，
   说明为何通用、以及这属于跨仓库改动、需要另行确认——**不得在本工作包内擅自进行**。
2. 五套 schema 的 predictor 集合**严格嵌套**：
   $P_0 \subsetneq P_1 \subsetneq P_3 \subsetneq P_5 \subsetneq P_9$。
3. **无越界**：第 $t$ 档的 predictor 中，采集波次 $> t$ 的列数为 **0**。
4. 未分配 source 全部落在 `unassigned_sources.csv`，且不出现在任何一档里。
5. 五档全部跑完，输出 CSV 中每个 (landmark, model, K) 组合的 `status` 为 `ok`
   的比例被记录（允许有失败 cell，但必须报告比例）。
6. C2 的外推自检对**每一档**都有 predicted / observed / 相对偏差三个数。
7. 五档的 $\hat U(t)$ 在单调化前后都被输出；违反单调的档位被显式列出。
8. **外部一致性检查**：$\hat U(9)$ 必须不大于 FFC 已发表的 GPA 最佳模型
   在测试集上的 $1-R^2$（约 0.8）。超出即为算错，必须阻断并报告。
9. 图和 CSV 存在，且 CSV 中的数与图一致。

## 测试要求

`learning_curve.py` 的测试**全部参数化生成**，不得依赖 FFCWS 的任何形状：

1. **能还原已知渐近线**：构造 $\text{err}(N)=c + aN^{-b}$ 的无噪点，
   拟合应还原 $c$（相对误差在给定容差内）。多组 $(c,a,b)$ 参数化。
2. **加噪后区间覆盖**：加已知方差的噪声，bootstrap 区间应以名义覆盖率
   覆盖真值（允许统计容差，用固定 seed）。
3. **函数形式错配可被 C2 发现**：用指数曲线生成数据、用幂律拟合，
   C2 的相对偏差应显著大于形式匹配时。
4. **保序回归**：给一条违反单调的输入，断言输出单调不增，且原始值被保留。
5. **退化输入**：点数少于参数个数、误差全相同、含 NaN——应给出明确错误
   或有记录的跳过，不得静默返回。

adapter 侧：

6. 波次导出函数：参数化构造若干 source 名（含取不到数字的），
   断言映射正确、未分配集合正确。
7. 嵌套性与无越界：用**合成 manifest**（不是真实 FFCWS）断言验收标准 2、3。
8. 真实 FFCWS 只作为一条回归检查出现：断言嵌套与无越界成立，
   **不断言具体列数**。

测试用 pytest 写法（参数化一律用 `@pytest.mark.parametrize`）。从 `project/` 跑
`../.venv/bin/python -m pytest -q`，通过数不低于基线 10 加本方案新增的测试数；
标准命令见 `TESTS.md#standard-commands`。

## 留给人工决定的（不要自己猜）

- `n_grid` / `k_grid` 的具体取值：作为待澄清问题提出（见下），等确认后再跑正式网格。
  开发期用小网格自测即可。

> **待澄清问题写在哪**：本仓库的 `AGENTS.md#response-contract` 没有"待澄清问题"
> 这一项（第 5 项是「文档更新建议区块」，语义不同）。本方案约定：实施中遇到的
> 歧义、二选一和方案与代码现状不符之处，一律写入
> `reports/ffcws-gpa-horizon-demo.md` 的「待澄清问题」小节，并在最终回复的
> 「风险或限制」一节点名。**不得自行猜测后默默实现。**
- `preset` 与算力预算。
