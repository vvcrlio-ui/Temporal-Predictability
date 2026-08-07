# Project Context Map

## Project Summary

- 项目名称：Temporal FFCWS / Fragile Families Challenge application
- 核心目标：评估从出生至 9 岁的信息对 15 岁结果的可预测性，并研究预测表现随样本量（N）、预测变量数（K）和信息截止波次的变化。
- 当前阶段：数据适配器已存在；GPA horizon demo 与绘图层已完成设计、等待实施。
- 主要技术栈：Python、pandas、NumPy、PyYAML，以及外部安装的 `aleatoric_nk_grid`。
- 默认开发分支：当前工作区尚未初始化 Git，未定义默认分支。

## Workspace Layout

- SDD 文档根目录：`.`
- Codex 自动入口：`./AGENTS.md`
- Claude Code 自动入口：`./CLAUDE.md`
- 跨平台 SDD 方法论：`./.system/SYSTEM_PROMPT.md`
- 实际项目目录：`./project/`
- 源代码目录：`./project/src/`
- 测试目录：`./project/tests/`
- 项目命令执行目录：`./project/`

## Current Focus

- 当前任务：GPA 可预测性视野曲线 demo
- 当前状态：Planned
- 任务详情：参见 `ROADMAP.md#gpa-可预测性视野曲线-demo` 与 `plans/ffcws-gpa-horizon-demo.md`
- 相关架构：参见 `ARCHITECTURE.md#3-module-boundaries`、`ARCHITECTURE.md#4-dependency-rules` 和 `ARCHITECTURE.md#5-data-and-api-contracts`
- 相关测试：参见 `TESTS.md#horizon-demo-验证要求`
- 后续任务：绘图与判读层，参见 `plans/ffcws-horizon-figures.md`

## System Map

| 模块 | 职责 | 入口 | 依赖限制 |
|---|---|---|---|
| Adapter CLI | 解析配置并启动数据准备 | `project/adapter.py` | 只从 `project/src/` 导入项目包 |
| Data processor | 构建共享 schema、三种特征表示与 outcome-specific ARD | `project/src/ffcws_data_processor/pipeline.py` | 可依赖公开的 `aleatoric_nk_grid` API；不得修改外部引擎 |
| Configuration | 定义输入、输出、缺失码和 schema 筛选规则 | `project/config/ffc.yaml` | 路径相对配置文件解析 |
| Analysis schemas | 保存可版本化的引擎输入契约 | `project/schema/` | 不包含私有原始数据或生成的 ARD 表 |
| Panel manifest | 定义 N×K 分析面板和模型参数 | `project/panels.yaml` | 只引用 `project/` 内配置与产物 |

## Documentation Index

| 文档 | 内容 | 何时更新 |
|---|---|---|
| `AGENTS.md` | AI 工具共用的仓库硬约束与 Codex 自动入口 | 工作流入口、优先级或硬约束变化 |
| `CLAUDE.md` | Claude Code 的轻量入口，指向共用规范 | Claude Code 加载入口变化 |
| `.system/SYSTEM_PROMPT.md` | 跨平台 SDD 方法论 | SDD 方法本身变化 |
| `ARCHITECTURE.md` | 架构边界、业务不变量和技术决策 | 架构或公共契约变化 |
| `ROADMAP.md` | 当前任务、范围、依赖和验收状态 | 任务范围或状态变化 |
| `TESTS.md` | 测试策略、质量门槛和验证命令 | 测试体系或标准命令变化 |
| `LESSONS.md` | 跨任务可复用的工程经验 | 产生新的通用行动规则 |
| `plans/ffcws-gpa-horizon-demo.md` | 当前 demo 的详细研究与实现设计 | demo 技术设计变化 |
| `plans/ffcws-horizon-figures.md` | demo 绘图与判读层设计 | 图形输入契约或验收标准变化 |
| `plans/ffcws-temporal-predictability.md` | 已被 NK Grid 路线取代的早期长期设计 | 仅补充历史说明，不作为当前实现依据 |

## Standard Commands

以下命令均从 `project/` 执行：

- 安装依赖：尚无版本化依赖清单；不得猜测命令
- 运行适配器：`python adapter.py`
- 类型检查：尚未配置
- 单元与集成测试：`python -m unittest discover -s tests`
- 编译检查：`python -m compileall -q adapter.py src tests`
- Panel 配置预检：`aleatoric-nk-grid-panels --manifest panels.yaml --dry-run`
- 构建：不适用，当前为 Python 分析项目

## Known Constraints

- `aleatoric_nk_grid` 是外部安装依赖，当前工作区没有版本化依赖清单。
- 完整适配器运行需要用户提供的 FFCWS 私有数据，文件位于 `project/data/private/`。
- 当前工作区没有 Git 元数据，无法用版本控制命令核验迁移差异。
