# Roadmap

## Status Definitions

- Planned：范围和验收标准已明确
- In Progress：正在实施
- Blocked：存在明确阻塞项
- Review：实现完成，等待验证或审查
- Done：满足全部完成条件

## Research Program

本项目的总体目标不是完成一次 GPA demo，而是为每个研究结果构建“联合数据规模 × 观察波次 × 样本外预测表现”的曲面。联合数据规模由一系列配对的 `(N, K)` 档位组成，表示家庭数量与可用变量数量共同增长。主曲面描述整体数据资源扩展；固定 K、固定 N 和跨波次 matched-K 切片用于诊断曲面、区分 N/K 作用，并在外推可信时估计不可预测性上界。

研究定义、估计对象与 demo/完整研究的边界以 `README.md` 为准。实施顺序是：先用年龄 15 GPA 验证方法，再扩展到六个年龄 15 结果，最后评估年龄 22 的生命历程扩展。

## Current Task

### GPA 可预测性视野曲线 demo

- 状态：Planned
- 目标：以 GPA 验证基础研究方法，包括出生、1、3、5、9 岁五个严格嵌套的信息集，以及用于估计可比较不可预测性上界的固定-K学习曲线。该 demo 为完整研究的联合 N–K 规模曲面提供估计与诊断组件，但本身不承担完整研究范围。
- 详细设计：`plans/ffcws-gpa-horizon-demo.md`
- 相关架构：`ARCHITECTURE.md#2-business-invariants`、`ARCHITECTURE.md#4-dependency-rules`
- 依赖任务：无本仓库内前置任务；依赖外部已安装的 `aleatoric_nk_grid` 公开契约。
- 修改范围：
  - `project/src/ffcws_data_processor/`
  - `project/tests/`
  - `project/panels.landmark.yaml`
  - `project/analysis/`
- 非目标：
  - 不修改外部 N×K 引擎源码
  - 不扩展到 GPA 以外的 outcome
  - 不做 SES 分层、因果推断或 production 规模运行
  - 不比较三种插补策略，demo 固定 `median_mode`
- 验收标准：
  - [ ] 五个 landmark schema 严格嵌套且无越界 source
  - [ ] 未归类 source 被显式报告，不被猜测分配
  - [ ] panel 使用预定义外部测试集和约定的 N/K 网格
  - [ ] 渐近线估计、外推自检、bootstrap 区间与单调化均有测试
  - [ ] 产出数值表、诊断和方法说明
  - [ ] `TESTS.md` 中对应验证通过
- 风险：学习曲线尾部可能不足以支持可信外推；此时必须触发降级报告，不得强行给出结论。
- 阻塞项：开始实施前，需确认外部依赖可用并补齐项目依赖声明。

## Backlog

### Horizon demo 图与判读层

- 状态：Planned
- 目标：在 demo 数值产物上生成固定-K学习曲线、不可预测性曲线、`(t, N)` 沟通曲面和顺序翻转诊断。
- 详细设计：`plans/ffcws-horizon-figures.md`
- 依赖任务：GPA 可预测性视野曲线 demo 产生稳定输入契约。
- 非目标：不重新拟合模型，不在绘图脚本中复制统计估计逻辑。
- 验收标准：以详细设计的输入契约、视觉降级规则和自动化测试为准；实施时须同步提炼到 `TESTS.md`。

### 年龄 15 六结果联合规模曲面

- 状态：Planned
- 目标：在 GPA demo 通过后，正式定义联合 `(N, K)` 规模路径，并将波次信息集、诊断切片和不可预测性上界扩展到当前六个年龄 15 结果，为每个结果单独生成“联合数据规模 × 观察波次 × 预测表现”曲面与数值表。
- 依赖任务：GPA demo 与图形判读层完成；联合规模路径和输出契约稳定。
- 研究约束：不同结果使用适合其任务类型的样本外指标和归一化方法；不依据曲面绝对高度对不同结果作简单排名。
- 验收标准：另行编写实施方案，不从 GPA demo 隐式推断 outcome-specific 选择。

### 22 岁多结果生命历程扩展

- 状态：Planned
- 目标：在 demo 验证后，将方法扩展到 22 岁结果和六个观察时点。
- 背景资料：`plans/ffcws-temporal-predictability.md`
- 依赖任务：demo 与绘图层完成并经研究判断。
- 非目标：不得直接照搬该早期文档中已被 NK Grid 路线取代的技术栈与 CV 方案。

## Completed

### 跨工具 AI 指令入口

- 状态：Done
- 实际变更：新增 Codex 自动入口 `AGENTS.md` 和 Claude Code 入口 `CLAUDE.md`，两者统一指向 `.system/SYSTEM_PROMPT.md`。
- 验收结果：仓库级硬约束与可移植 SDD 方法论已分离，测试基线事实迁移到 `TESTS.md`，入口文件之间没有完整规则副本。
- 剩余问题：入口加载需在新 Codex/Claude Code 会话中生效；当前会话不会自动重建指令链。

### SDD 工作区边界迁移

- 状态：Done
- 实际变更：将原 `FFCWS/` 迁移为 `project/`，统一 `src/`、`tests/`、`config/` 入口，并建立 SDD 控制文档。
- 验收结果：根目录边界与旧路径审计通过；配置路径解析到 `project/data/` 和 `project/schema/`；Python 编译检查通过；现有 10 项测试在已安装外部依赖的环境中通过。
- 剩余问题：项目尚无版本化依赖清单，工作区尚未初始化 Git。
