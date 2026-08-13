# Test Strategy

## Quality Gates

行为性代码变更至少满足：

- [ ] Python 编译检查通过
- [ ] 相关单元与集成测试通过
- [ ] 新行为具有对应测试
- [ ] 缺陷修复具有能复现原问题的回归测试
- [ ] 数据契约变化具有 schema/manifest 契约测试
- [ ] 没有通过跳过、删除或放宽断言使测试通过
- [ ] 未使用真实测试样本决定训练期 schema

文档或目录调整至少满足：

- [ ] 所有记录的项目路径均位于 `project/`
- [ ] 根目录没有业务代码、测试、配置、构建脚本或依赖文件
- [ ] 文档中的标准命令能从 `project/` 运行，或明确标为尚未配置

## Test Levels

| 变更类型 | 最低测试要求 |
|---|---|
| 纯函数、波次解析或局部转换 | 单元测试 |
| 特征表示与 manifest 变化 | 单元测试 + schema/manifest 契约测试 |
| 配置、路径或数据写出变化 | 临时目录集成测试 |
| 外部引擎 API 契约变化 | 集成测试 + 最小 dry run |
| 完整 adapter 流程 | 合成数据端到端测试；真实数据仅由授权用户运行 |
| 缺陷修复 | 能复现原问题的回归测试 |
| 类型契约变化 | 类型检查；在工具落地前至少运行编译检查 |
| 仅文档或排版 | 路径/链接审计，不要求新增行为测试 |

## Standard Commands

所有命令从 `project/` 执行，使用仓库根目录的 `.venv`：

```sh
# 安装依赖（含固定到具体 commit 的外部 N×K 引擎）
../.venv/bin/python -m pip install -r requirements.txt

# 单元与集成测试（标准口径）
../.venv/bin/python -m pytest -q

# Python 编译检查
../.venv/bin/python -m compileall -q adapter.py src tests

# Panel 配置预检（需要外部引擎 CLI）
../.venv/bin/aleatoric-nk-grid-panels --manifest panels.yaml --dry-run

# 完整适配器（需要 project/data/private/ 中的授权数据）
../.venv/bin/python adapter.py
```

测试框架为 **pytest**。现有测试是 unittest 风格，pytest 可直接收集，两种口径计数一致；
新增测试一律用 pytest 写法——两份方案大量要求"参数化生成"，需要
`@pytest.mark.parametrize`。不再以 `python -m unittest discover` 作为标准命令。

当前未配置静态类型检查器、formatter、独立 E2E runner 或完整验证聚合命令。引入相应工具时，必须把配置和依赖放在 `project/` 并更新本节。

## Verification Baselines

基线事实维护在本节，不写入 AI 工具入口文件。

| 日期 | 代码版本 | 环境 | 命令 | 结果 |
|---|---|---|---|---|
| 2026-08-07 | 工作区未初始化 Git | 借用 Aleatoric 虚拟环境 | `python -m unittest discover -s tests` | 10 项通过（历史记录，口径已废弃） |
| 2026-08-07 | `main @ 891f652` | 本仓库 `.venv`，`requirements.txt` 固定引擎 `19890d3`，Python 3.14 / macOS arm64 | `../.venv/bin/python -m pytest -q` | **10 passed（37.7s 首跑 / 2.8s 复跑）** |
| 2026-08-12 | `main @ 0445803` | 本仓库 `.venv`，引擎 pin 升至 `6a9a139`（含逐行预测导出；ridge CV 改为解析 LOO），Python 3.14 / macOS arm64 | `../.venv/bin/python -m pytest -q` | **44 passed（24.0s）** |

`891f652` 是 Horizon demo 与图层两份方案的开工基线。

引擎 pin 从 `19890d3` 升到 `6a9a139` 后测试数不变（44 passed）——本仓库测试覆盖的是
adapter 与学习曲线模块，不依赖 ridge 的数值实现。但**引擎输出的数值结果已变**，
升级前的 pilot 结果已归档至 `project/data/archive/pilot-engine-19890d3/`。

新工作包开工前若计划指定了目标提交或分支，应在该版本上实跑标准命令并追加记录；不得沿用其他仓库或其他提交的测试计数。升级 `requirements.txt` 中固定的引擎 commit 后必须重跑并追加新行——引擎行为变化会改变数值结果。

## Current Coverage

- `tests/test_strategies.py`：三种表示、缺失值、未知类别、训练池稳定性、manifest 类型和 outcome-specific 类别覆盖。
- `tests/test_ffcws_adapter.py`：合成输入上的 adapter 端到端输出、内容确定性、schema 可加载性和输入验证。

## Horizon Demo 验证要求

实施 `ROADMAP.md#gpa-可预测性视野曲线-demo` 时，至少覆盖：

- 波次标签纯函数对 1–5 波及不可归类 source 的处理。
- 五档 manifest、feature universe 和 schema 的严格嵌套性与无越界列。
- 同一路线内所有 landmark 复用同一套训练/测试划分和同一 ARD 表；Challenge 路线用官方划分，ICPSR 路线用自建划分。
- 学习曲线拟合参数约束、失败路径和合成数据恢复能力。
- 尾部删点外推自检与不可信时的结构化诊断。
- 按家庭 ID 聚类的 bootstrap 可复现性与区间合法性。
- 原始估计与单调化估计同时保留，单调化仅作单向收紧。
- 不同 landmark 的归一化分母一致。

详细数值阈值和产出字段以 `plans/ffcws-gpa-horizon-demo.md` 为设计附件；一旦实施导致标准命令或测试矩阵变化，应同步更新本文件。

## Test Conventions

- 测试名称描述行为和预期结果。
- 测试独立、可重复执行且不依赖执行顺序。
- 文件写入使用临时目录；测试结束后不在 `project/` 留生成产物。
- 时间、随机数和 bootstrap 必须使用显式种子。
- 外部服务或引擎使用公开 API、受控替身或隔离环境。
- 不仅验证实现细节，还要验证训练/测试隔离和研究设计不变量。
- 不得用私有真实数据作为测试套件的必要条件。

## Requirement Traceability

| 任务 | 验收条件 | 测试文件 | 测试层级 |
|---|---|---|---|
| 现有 adapter | 三种表示遵守共享 schema 与缺失值契约 | `tests/test_strategies.py` | Unit / Contract |
| 现有 adapter | 合成数据端到端产物确定且可被引擎读取 | `tests/test_ffcws_adapter.py` | Integration |
| GPA horizon demo | 五档信息集严格嵌套 | 待实施于 `tests/` | Unit / Contract |
| GPA horizon demo | 渐近线、自检、区间和单调化正确 | 待实施于 `tests/` | Unit / Integration |
