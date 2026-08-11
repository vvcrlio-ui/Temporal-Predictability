---
status: ready-for-codex
---

# horizon demo 的图与判读层

> **研究层级说明（2026-08-07）**：本文件只定义 GPA demo 的图与判读层。
> 其中的 `(t, N)` 曲面是固定 K 设计的诊断图，不是完整研究最终的联合
> `(N, K)` 规模曲面。项目级研究目标及二者关系见根目录 `README.md`。

批次：**依赖 `ffcws-gpa-horizon-demo`**（该方案的 A/B/C 提供本方案的全部输入）。

**本方案取代 `ffcws-gpa-horizon-demo` 的 §D。** 原 §D 只指定了一张 Û(t) 图；
A（波次切分）、B（panel 配置）、C（`learning_curve.py`）仍完全以该方案为准，
本方案不修改其中任何一条。

**目标分支：`codex/ffcws-gpa-horizon-demo`**（与被依赖方案同一分支，不另起新分支）。

> **仓库归属说明**：本方案与 `ffcws-gpa-horizon-demo.md` 同属本仓库
> （`vvcrlio-ui/Temporal-Predictability`）。`aleatoric_nk_grid` 引擎是
> **外部 pip 依赖**，由 `project/requirements.txt` 固定到
> `vvcrlio-ui/Aleatoric_Luck@19890d3` 的 `NK_Grid` 子目录，**其源码不在本仓库内**。
> 本文档下文若出现引擎模块名，指的都是该已安装的包，不是本仓库目录。

基线：以被依赖方案（`ffcws-gpa-horizon-demo.md`）实际实施时记入
`TESTS.md#verification-baselines` 的基线为准；本方案与其共用分支，不单独重跑基线，
但交付前必须复跑一次标准命令并追加记录。

## 为什么要有这一步

原 §D 那张 Û(t) 图是**结论**，但这个 demo 的全部说服力在于一件结论图上看不见的事：

> 五档的变量数差约十倍，训练行数上限却相同。变量多的那档离收敛更远，
> 它在满 N 处的误差里掺着"人不够学不动"。直接比五档的满 N 误差，
> 比的是谁离收敛更远。

这句话在 `ffcws-gpa-horizon-demo` §"为什么不能直接用最大 N 处的误差当答案"里已经论证过，
但**没有要求把它画出来**。只给结论图的话，读者没有任何理由相信外推那一步是必要的，
也没有办法判断外推可不可信。

本方案要求把"为什么必须外推"和"外推可不可信"都变成图上可见的东西。

## 目标

1. 三张图：学习曲线（判读用）、Û(t)（结论）、(t, N) 曲面（沟通用）。
2. 一份图数一致的数值表。
3. 一个**顺序翻转检查**，把"必须外推"变成可报告的证据（而不是论证）。
4. 一个**安全阀**：外推自检失败时，图必须自动降级，不得输出看起来正常的结果。

## 范围

**In scope**

- `project/figures/` 下的脚本：只读引擎输出 CSV 与 `learning_curve.py` 的输出，
  产出图与表。
- 上述三张图 + 一份 CSV + `reports/ffcws-gpa-horizon-demo.md` 的图注与判读部分。
- 输入过滤与聚合口径（必须与 `learning_curve.py` 一致，见"输入契约"）。
- 顺序翻转检查。
- 外推不可信时的视觉降级规则。
- 数据变换层的单元测试（不测像素，见"测试要求"）。

**Out of scope**

- **不改引擎**：`aleatoric_nk_grid` 是外部 pip 依赖，不得以任何方式就地编辑
  （包括改动其安装目录、或修改 `Aleatoric_Luck` 本机 checkout）。
- **不改** `ffcws-gpa-horizon-demo` 的 A/B/C：不动 adapter 的波次切分、
  不动 panel 配置、**不动 `learning_curve.py` 的拟合逻辑**。
  若发现拟合层缺了本方案需要的输出字段，作为待澄清问题提出，不要自行加。
- 不做交互式图、不做网页。
- 不做 SES 分层图（那是 demo 之后的事）。
- 不做 GPA 以外的结果。
- **不把绘图逻辑推进外部引擎包。**

## 🔒 通用引擎约束在本方案中的落点

绘图脚本全部位于 `project/figures/`，**允许**出现 `wave`、`landmark`、波次数字——
它们是 FFCWS 的数据集事实，本来就该留在本项目内。

作为交换，硬约束是：`project/requirements.txt` 里固定的引擎版本不得改动，
`Aleatoric_Luck` 本机 checkout 不得出现任何未提交修改。本方案不新增、
不修改引擎侧任何文件。

## 输入契约

### 来源一：引擎输出 CSV

`project/outputs/nk_grid_*.csv`。实测列名（引擎 `19890d3`）中本方案消费这些：

`dataset, model, seed, draw, N, K, r2_test, rmse, n_test_total,
status, constant_prediction, underdetermined, converged`

**不得假设存在其他列。** 需要 MSE 时由 `rmse ** 2` 得到，不要去找 `mse` 列。

### 来源二：`learning_curve.py` 的输出

按 `ffcws-gpa-horizon-demo` §C，每个 `(dataset, model, K)` 组合应有：
渐近线点估计、bootstrap 区间、C2 自检的 `predicted` / `observed` / 相对偏差、
所用函数形式（幂律 / 指数）、以及 C4 单调化前后的值。

**实际字段名以该模块交付时为准。** 本方案的脚本必须通过一个显式的列名映射表
读取，映射表放在 `project/figures/config.yaml`，不得把字段名散落在绘图代码里。

### 必须在脚本里完成的过滤与聚合（不是手工）

1. **过滤不在本层实现。** 调用 `project/analysis/` 的公开入口（见
   `ffcws-gpa-horizon-demo.md` §C0），由它剔除 `status != "ok"` 以及
   `constant_prediction` / `underdetermined` 为真的行，并返回被排除的行数与占比。
   图层把该占比填进 `excluded_cell_ratio` 与图注。
2. **禁止在图层复制一份过滤逻辑**；若入口缺少所需参数，作为待澄清问题提出。
3. 对每个 `(dataset, model, K, N)`，取跨 `seed` × `draw` 的**中位数**作为该点的观测值。
   这必须与 `learning_curve.py` §C1 的口径完全一致——**若不一致，图和拟合会对不上，
   属于必须阻断的错误**，作为待澄清问题记入 `reports/ffcws-gpa-horizon-demo.md`。
4. 归一化口径：`ffcws-gpa-horizon-demo` §C5 要求 `Û = ε̂²∞ / Var(Y_test)`。
   注意引擎的 `r2_test` 用的是**训练集均值零模型**
   （`aleatoric_nk_grid.evaluation.r2_against_training_mean`），
   与 `Var(Y_test)` 不是同一个分母。
   **两条路都要算，并在 CSV 中各占一列**：
   - `u_from_asymptote` = `ε̂²∞ / Var(Y_test)`（主口径，对齐 van de Rijt）
   - `u_from_r2` = 由 `1 − r2_test` 拟合得到的渐近线（对照口径）
   两者的差必须出现在报告里。差异显著时说明训练/测试均值偏移不可忽略，
   须在图注声明用的是哪一个。

## 图 1：学习曲线（主图，用于判读）

**五个小面板**，一档一个，共享坐标轴。不要五条线挤一张——真实数据要画 bootstrap
带，五条带叠在一起会糊。

每个面板：

- x = `N`（对数刻度）
- y = MSE（`rmse ** 2`）
- 内容：
  - 各模型的观测点（淡色，细）
  - **包络**（每个 N 上取各模型最小值）：实线，强调
  - 对包络的拟合曲线
  - 渐近线：水平虚线 + bootstrap 区间带
  - **最后一个实测点到渐近线的落差**：必须用一段带数值标注的引线画出来，
    这是本图存在的理由
  - C2 自检的 `predicted` 与 `observed` 两个点必须画在图上（不同标记），
    并标注相对偏差

面板标题写观察年龄（0/1/3/5/9 岁），不写内部波次编号。

## 图 2：Û(t)（结论图，原 §D 图 1）

- x = 观察年龄 0/1/3/5/9，y = `Û(t)`
- 实线 = 全部 K（主结果）；三条虚线 = 三个跨档匹配的 K
- **单调化前后都要画**：单调化后为实心点连线，原始估计为空心点。
  违反单调的档位必须在图上可辨认（不只在 CSV 里）
- bootstrap 区间带
- 图注必须写明：这些数是**上界**；不可与其他结果变量比较
- **图注必须写明区间的性质**：`split_mode` 为 `external_test` 时训练/测试切分与
  家庭构成是固定的（引擎在该模式下对所有 seed 复用同一份切分），
  bootstrap 重抽的是蒙特卡洛重复而非家庭。因此区间表示的是
  **蒙特卡洛误差**，不是对总体的抽样不确定性，会低估后者。
  这句话必须出现在图 1、图 2 的图注里，不得省略。

## 图 3：(t, N) 曲面（沟通用）

- 两个轴为观察年龄与 `N`，高度为 MSE 或 `Û`（在配置里选，图注写明选了哪个）
- 用包络（各模型最小值），不是单一模型
- **不插值**。网格就是 5 × `len(n_grid)`，有棱有角是诚实的。
  若确实插值，图注必须写明方法
- 必须把 `N → ∞` 的渐近线画成一条独立的棱（与曲面分离，视觉上明确"这不是观测到的"）
- 图注必须写：**本图不含不确定性，仅供沟通，判读以图 1 为准**

## 顺序翻转检查（本方案新增的实质内容）

在**最小 N** 与**最大 N** 两处，分别把五档按误差排序。

- 两处排序**不同** → 输出翻转对照表，作为"必须外推"的直接证据。
- 两处排序**相同** → 同样输出该表，并在报告中写明：外推的必要性弱于预期，
  结论对外推方法的依赖较小。

**两种结果都必须报告。** 不允许只在有翻转时才写这一节。

输出 `project/outputs/figures/rank_flip.csv`：
`landmark, rank_at_min_n, rank_at_max_n, mse_at_min_n, mse_at_max_n, flipped`

## 外推不可信时的视觉降级（安全阀）

`ffcws-gpa-horizon-demo` §C2 要求做外推自检，并规定"偏差大就说明函数形式不对，
渐近线不能用，此时必须在报告里明说"。本方案把这条从**人的自觉**变成**代码强制**：

当某档的 C2 相对偏差超过阈值（`project/figures/config.yaml` 的
`extrapolation_max_rel_dev`，默认 `0.20`）时：

1. 图 1、图 2 中该档的渐近线标记改为**空心 + 灰色**，区间带改为斜线填充；
2. 图注自动追加一行，列出所有失信的档位及其偏差数值；
3. 输出 CSV 中该行 `extrapolation_trusted = false`；
4. 若**全部五档**都失信，脚本以非零退出码结束，并打印"渐近线整体不可用"。

**禁止在自检失败时产出外观正常的图。** 这一条是本方案的验收核心。

## 产出

```
project/figures/
  config.yaml                 列名映射、阈值、口径选择
  transform.py                纯函数层：CSV → 绘图用数值（可测）
  plot_learning_curves.py     图 1
  plot_u_curve.py             图 2
  plot_surface.py             图 3
  make_all.py                 入口
  tests/test_transform.py
project/outputs/figures/
  fig1_learning_curves.(png|svg)
  fig2_u_curve.(png|svg)
  fig3_surface.(png|svg)
  figure_data.csv             三张图用到的全部数值
  rank_flip.csv
reports/ffcws-gpa-horizon-demo.md   仓库根目录，追加「图与判读」一节
```

`reports/` 位于仓库根目录，与 `plans/` 平级，纳入版本控制：它是研究交付物与
判读记录，不是运行期产物，因此不受「业务文件必须位于 `project/`」的约束
（见 `ARCHITECTURE.md#3-module-boundaries`）。运行期产物一律写入
`project/outputs/`，该目录被 `.gitignore` 排除。

`figure_data.csv` 至少含：
`landmark, landmark_age, model_or_envelope, K_arm, N, mse_median, n_cells,
asymptote, asymptote_ci_lo, asymptote_ci_hi, u_from_asymptote, u_from_r2,
form, c2_predicted, c2_observed, c2_rel_dev, extrapolation_trusted,
monotonized, excluded_cell_ratio`

## 验收标准

1. 外部引擎未被改动：`project/requirements.txt` 中固定的引擎版本与开工前一致，
   且 `Aleatoric_Luck` 本机 checkout 的 `git status` 干净（报告中给出输出作为证据）。
2. 在 `project/` 中运行 `python figures/make_all.py --config figures/config.yaml`
   在**合成输入**上端到端跑通，退出码 0，"产出"一节列出的全部文件生成且非空。
3. 三张图中的每一个数值，都能在 `figure_data.csv` 中找到同值的一行（抽查即可，
   但必须有一个测试断言图 2 的点全部来自该 CSV，不是脚本内二次计算）。
4. 引擎输出中 `status != "ok"`、`constant_prediction`、`underdetermined` 的行
   全部被排除；其占比出现在 `figure_data.csv` 的 `excluded_cell_ratio`
   与图注中。
5. 聚合口径与 `learning_curve.py` 一致：存在一个测试，用同一份合成输入分别过
   `transform.py` 与 `learning_curve.py` 的聚合入口，断言逐点相等。
   若 `learning_curve.py` 未暴露可调用的聚合入口，作为待澄清问题记入报告，
   **不要自己在 figures 侧复制一份实现**。
6. `u_from_asymptote` 与 `u_from_r2` 两列都存在且都非空；两者的差在报告中给出。
7. `rank_flip.csv` 存在，五档齐全，`flipped` 列在两种情况下都被正确填写。
8. 降级规则可验证：构造一份 C2 偏差超阈值的合成输入，断言
   （a）该档 `extrapolation_trusted` 为 `false`；
   （b）图注文本中出现该档；
   （c）全部失信时退出码非零。
9. 图 2 中单调化前后的值都被绘制，且违反单调的档位在图上可辨认。
10. 图 3 的图注文本中包含"不含不确定性"与"判读以图 1 为准"两项声明。
11. 图 1 中每个面板都标出了最后一个实测点到渐近线的落差数值。
12. 所有图的横轴标注为孩子年龄（0/1/3/5/9 岁），不出现内部波次编号。
13. 在 `project/` 中运行 `python -m pytest -q` 通过，计数不低于
    `TESTS.md#verification-baselines` 中被依赖方案交付时记录的基线，
    加上本方案新增的测试数。

## 测试要求

**不测像素。** 把"从 CSV 到画图用的数值"全部抽进 `transform.py` 的纯函数，测那一层；
绘图脚本只做一次冒烟。

1. **过滤规则**：合成 CSV 含 `status` 各种取值、`constant_prediction`、
   `underdetermined`，断言剩下的行集合正确、`excluded_cell_ratio` 数值正确。
2. **聚合口径**：验收标准 5。
3. **两种归一化**：构造训练均值与测试均值明显不同的合成数据，
   断言 `u_from_asymptote` 与 `u_from_r2` 不相等且都按定义算对。
4. **翻转检测**：参数化构造"有翻转"与"无翻转"两组输入，断言 `flipped` 正确；
   含并列名次的退化情形要有明确行为（不得静默）。
5. **降级触发**：参数化阈值与偏差，断言边界处（恰好等于阈值）的行为确定且有记录。
6. **全失信退出**：断言退出码非零且有明确信息。
7. **退化输入**：某档只有一个 N 值、某档全部 cell 被过滤掉、渐近线字段为 NaN——
   应给出明确错误或有记录的跳过，**不得静默出图**。
8. **冒烟**：合成输入跑 `make_all.py`，断言三个图文件存在且字节数大于零。

测试的合成输入**全部参数化生成**，不得依赖真实 FFCWS 的行数、列数或波次数量
（图 1 的面板数应由输入里出现的档位数决定，不写死 5）。

## 留给人工决定的（不要自己猜）

1. **图 3 的高度用 MSE 还是 Û** —— 配置项已留，默认值作为待澄清问题提出。
2. **`extrapolation_max_rel_dev` 的 0.20** 是拍的，等图 1 出来后按实际偏差分布调。
3. **图 2 中五档的区间若严重重叠**，是否改为只出图 3 —— 等真实区间宽度出来再定。
4. 图的最终配色与出版尺寸。

以上四项在真实数据跑出来之前都不要定死；开发期用合成输入自测即可。
