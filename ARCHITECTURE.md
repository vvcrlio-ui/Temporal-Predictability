# Architecture

## 1. System Goals

本项目为生命历程可预测性研究构建可复现、无测试集泄漏的 FFCWS 分析系统。长期研究目标是针对每个结果变量估计“联合数据规模（N 与 K 联动）× 观察波次 × 样本外预测表现”的曲面，并以固定条件的诊断切片和经验证的学习曲线渐近线估计不可预测性上界。年龄 15 的 GPA 分析只是第一阶段的方法 demo，不是系统的最终研究目标。完整研究定义见 `README.md`。

当前已实现的系统范围主要是年龄 15 结果的数据适配层：生成可供外部 N×K 引擎读取的分析输入和契约。波次信息集、联合规模路径、渐近线分析与图形层按 `ROADMAP.md` 分阶段加入。首要质量属性是研究设计正确性、确定性、可追溯性和对外部引擎的低耦合。

## 2. Business Invariants

- 必须保留 FFCWS 预定义的训练集与测试集；不得自行重分割真实数据。
- 预测变量资格、类别状态、流行率筛选和其他依赖观测值的决策只能使用预定义训练样本。
- 测试集中未在对应 outcome 的有效训练行出现的类别必须视为未知，不得反向改变训练 schema。
- 缺失 outcome 的行在 ARD 中保留，并在验证或拟合时按 outcome 单独处理。
- 同一原始分类变量生成的 one-hot 列必须作为一个原子 source 进入或离开 K 维度。
- 联合数据规模轴上的每个档位必须显式记录对应的 `(N, K)`；不得把联动轴误标为单独的 N 效应或 K 效应。
- 联合 N–K 路径用于描述数据资源整体扩展；若要解释 N、K 的独立作用或估计固定信息集的渐近误差，必须保留固定 K、固定 N 或 matched-K 诊断切片。
- 原始私有数据和生成的 ARD 表不得写入版本化 schema 文件。
- 所有运行所需业务文件必须位于 `project/`；项目运行不得读取根目录 SDD 文档或 `reports/`。

## 3. Module Boundaries

| 模块 | 职责 | 可以依赖 | 禁止依赖 |
|---|---|---|---|
| `project/adapter.py` | CLI 入口与默认配置定位 | `ffcws_data_processor.pipeline` | 根目录 SDD 文档、外部 checkout 的私有模块 |
| `project/src/ffcws_data_processor/common` | IO、schema、manifest 与基础验证 | 标准库、pandas、PyYAML | 研究图形层、根目录控制文档 |
| `project/src/ffcws_data_processor/strategies` | 三种 FFCWS 特征表示 | `common` 的公开对象 | 引擎内部实现、测试集驱动的 schema 决策 |
| `project/src/ffcws_data_processor/contract.py` | 生成外部引擎 schema 与 feature universe | `common`、公开的 `aleatoric_nk_grid` API | 外部引擎私有符号 |
| `project/src/ffcws_data_processor/pipeline.py` | 编排读取、编码、验证和产物写出 | 上述项目模块、公开的引擎验证 API | 绘图与下游结论逻辑 |
| `project/analysis` | 学习曲线拟合、渐近线估计、外推自检与单调化 | 标准库、NumPy、SciPy、pandas | 引擎内部实现、FFCWS 专属的波次语义与列名 |
| `project/figures` | 从数值产物生成研究图与判读表 | `project/analysis` 的公开输出、pandas、matplotlib | 重新拟合模型、复制 `analysis` 的统计估计逻辑 |
| `project/tests` | 单元、契约和集成验证 | 项目公开接口、测试依赖 | 私有真实数据的强制依赖 |
| `project/schema` | 可版本化的分析契约 | `project/data/ard` 的相对路径 | 嵌入原始或私有数据 |
| `reports/`（仓库根目录） | 研究交付物、方法说明与判读记录 | 无代码依赖 | 被 `project/` 运行时代码导入或读取 |

`project/analysis` 必须保持 article-agnostic：输入是"一列 N、一列误差、可选分组列"，
对任意来源的网格都成立，不得引用 FFCWS 的列数、行数或档位数量。FFCWS 特有的波次
语义只允许出现在 `project/src/ffcws_data_processor/` 与 `project/figures/`。

`reports/` 是本仓库唯一位于 `project/` 之外的非控制文档目录。它保存研究交付物而非
运行期产物，因此不受 §2 中"所有运行所需业务文件必须位于 `project/`"的约束——该约束
针对的是运行时依赖。运行期生成的图、表和日志一律写入 `project/outputs/`（已被
`.gitignore` 排除）。

## 4. Dependency Rules

- 项目命令的工作目录必须是 `project/`，源码导入根为 `project/src/`。
- 依赖方向为 `adapter.py → pipeline → strategies/contract/common`；`common` 不得反向导入编排层。
- FFCWS 特有的波次、变量和 outcome 规则必须留在本项目，不得写入外部通用 N×K 引擎。
- 与外部引擎交互只能使用其公开 API 或 CSV/JSON/YAML 文件契约。
- 配置路径必须相对配置文件位置解析，不得依赖调用者的当前目录推断数据位置。
- 源码、测试、配置、脚本和依赖声明不得放在 `project/` 之外。

## 5. Data and API Contracts

- 适配器配置版本为 `ffcws-adapter-v1`，并要求 `split_mode: external_test` 与 `feature_universe_mode: train_pool_screened`。
- 输入主键默认为 `challengeID`；背景、训练和测试表中的 ID 必须唯一，训练与测试 ID 必须互斥。
- 缺失码固定为 `-9` 至 `-1`；配置若与代码契约不一致，适配器必须失败。
- 当前 outcome 集合为 `gpa`、`grit`、`materialHardship`、`eviction`、`layoff` 和 `jobTraining`。
- 当前**启用**的表示策略只有 `median_mode`。`median_missing_indicator` 与
  `tree_ordinal` 的实现保留在 `strategies/` 下但未启用，属于 `README.md`
  研究问题 5（表示稳健性）的后续材料；重新启用只需把它们加回
  `config/ffc.yaml` 的 `strategies` 并重跑 adapter，不改代码。未启用时
  `schema/` 下不应存在其对应的契约文件。
- 输出 schema、feature universe、manifest 和 provenance 必须确定性生成，并使用相对路径连接生成数据。
- 对 schema 或 manifest 的破坏性契约变更必须更新版本号并提供迁移说明。

## 6. Error Handling

- 配置缺失、契约版本不兼容、ID 重复或交叉、未知策略和超阈值未知类别必须抛出带上下文的错误。
- 不得静默跳过无法归类的数据、失败的验证或缺失的必需输入。
- 写出产物前后应保持可诊断信息，包括 outcome、source、计数、阈值和路径。
- 因缺少私有数据无法运行时，应明确列出缺失路径，不得生成看似成功的空产物。

## 7. Security Boundaries

- `project/data/private/` 只存放用户提供且受数据使用协议约束的文件。
- 日志、异常、测试 fixture 和版本化 JSON 不得包含个体级私有记录。
- 测试默认使用合成数据或临时目录；不得要求真实 FFCWS 数据。
- 不得将本机外部依赖 checkout 当作本工作区的一部分进行修改。

## 8. Architecture Decisions

### ADR-001：单一项目工作区

- 状态：Accepted
- 背景：原业务目录名为 `FFCWS/`，根目录缺少文档与代码边界。
- 决策：业务代码及运行资产统一位于 `project/`；根目录只保留 SDD 控制文档、AI 配置和支持性规范。
- 后果：所有项目命令从 `project/` 执行，代码不得依赖根目录文档。
- 替代方案：在根目录混放代码和控制文档；因边界不清而拒绝。

### ADR-002：外部 N×K 引擎

- 状态：Accepted
- 背景：通用 `aleatoric_nk_grid` 引擎由另一个仓库提供。
- 决策：本项目只通过公开 Python API 与文件契约消费该引擎，不复制或修改引擎源码。
  依赖声明为 `project/requirements.txt` 中固定到具体 commit 的 Git 依赖
  （`vvcrlio-ui/Aleatoric_Luck@19890d3`，`subdirectory=NK_Grid`）。
- 后果：升级引擎必须显式改动该 commit 并重跑
  `TESTS.md#verification-baselines`，因为引擎行为变化会改变数值结果。
  不得使用可变引用（分支名、`main`）以免结果不可复现。
- 替代方案：将引擎代码复制进本仓库；因重复维护和边界混乱而拒绝。
  指向本机路径的可编辑安装；因不可移植、不可复现而拒绝。

### ADR-003：训练样本决定特征契约

- 状态：Accepted
- 背景：使用测试样本决定变量或类别会造成评估泄漏。
- 决策：所有数据驱动的 schema 决策只使用预定义训练样本，测试集仅用于最终评估与未知类别检查。
- 后果：测试集独有类别会被映射为缺失，且必须有 QA 记录。
- 替代方案：合并训练和测试数据学习编码；因泄漏而拒绝。

### ADR-004：跨工具 SDD 指令入口

- 状态：Accepted
- 背景：Codex 与 Claude Code 的自动指令发现入口不同，普通方法论文档不能保证自动加载。
- 决策：`AGENTS.md` 保存仓库级硬约束并作为 Codex 入口；`CLAUDE.md` 只作为 Claude Code 入口；两者统一指向 `.system/SYSTEM_PROMPT.md` 的可移植 SDD 方法论。
- 后果：入口文件保持精简，不在多个文件完整复制工作流；方法论变化只在 `SYSTEM_PROMPT.md` 维护。
- 替代方案：在每个工具入口复制完整规范；因规则漂移风险而拒绝。
