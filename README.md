# GitHub Trending AI 知识库

一个轻量、可审计的 GitHub Trending AI 项目雷达：每天采集 21 个 Trending 页面，经过硬过滤、趋势分、静态质量分和 AI 价值分四层筛选，最终生成 Markdown Wiki 与可离线浏览的 HTML 知识站。

> 候选来自 GitHub Trending，不代表 GitHub 全站完整排名。

## 它每天做什么

```text
21 个 Trending 页面
  → owner/repo 去重
  → AI 主题过滤
  → H：硬过滤（PASS / FAIL）
  → T：Trending 趋势分
  → Q：静态质量分
  → V：AI 价值分与 L0-L4 分层
  → Markdown 项目卡与日报
  → 离线 HTML 首页、日报和详情页
```

采集矩阵：

- 周期：Today、This week、This month。
- 范围：Global、Python、TypeScript、JavaScript、Jupyter Notebook、Go、Rust。
- Spoken Language：Any。

## 初始状态

仓库不附带任何日报、候选仓库、评分或项目详情示例数据。克隆后运行首次每日任务，系统会从空知识库开始生成规范化快照、Markdown 和 HTML。

首次采集前也可以打开 `site/index.html`，它会显示等待采集的空状态页面。

## 设计原则

- Trending 是唯一自动候选池，不另建全站仓库池。
- 不克隆、不安装、不导入、不执行候选仓库。
- 质量判断基于 README、许可证、源码、测试、CI 与发布信息的静态阅读。
- GitHub API 的 `NOASSERTION` 不等于没有许可证，必须读取实际许可证文件。
- License 分为学习科研和工程落地两条判断轨道。
- 项目年龄只用于区分 `NEW_HOT` 与 `REVIVED_HOT`，不直接淘汰项目。
- 页面缺失值写 `null`，不使用 0 冒充已知数据。

完整规则见：

- [工作流](WORKFLOW.md)
- [四层筛选规则](SCREENING_RULES.md)
- [Codex 每日自动任务提示词](AUTOMATION_PROMPT.md)

## 目录

```text
├─ incoming/                 每日采集和源码证据批次
├─ trending/raw/             页面级规范化快照
├─ trending/snapshots/       按仓库合并后的快照
├─ evaluations/              H/T/Q/V 与最终评分
├─ daily/                    Markdown 日报
├─ repos/                    Markdown 项目卡
├─ rejections/               内部淘汰记录
├─ site/                     离线 HTML 知识站
├─ scripts/                  评分、渲染与校验脚本
├─ schemas/                  输入 Schema
└─ tests/                    确定性评分测试
```

为保持轻量，Git 不跟踪浏览器原始 HTML、回滚归档、本地证明文件、缓存和凭据。每日任务生成的规范化 JSON 快照、日报与项目卡可以正常提交。

## 本地运行

要求：Python 3.11+，核心脚本只使用标准库。

```powershell
python scripts/trending_engine.py ingest --root . --input incoming/YYYY-MM-DD.json
python scripts/build_site.py --root .
python scripts/trending_engine.py validate --root .
python scripts/validate_site.py --root .
python -m unittest discover -s tests -p "test_*.py"
```

`incoming/YYYY-MM-DD.json` 的页面采集、主题选择和源码证据阅读由每日 Codex 自动任务完成；确定性脚本负责校验、计算分数和生成内容，避免人工覆盖 T、F、等级或最终状态。

## 每日自动运行

1. 在 Codex 中为本仓库创建每天运行一次的本地自动任务。
2. 使用 [AUTOMATION_PROMPT.md](AUTOMATION_PROMPT.md) 中的完整提示词。
3. 将自动任务工作目录设置为本仓库根目录。
4. 推荐时间：每天 `09:00`，时区 `Asia/Shanghai`。

## 输出

- `site/index.html`：知识库首页。
- `site/daily/YYYY-MM-DD.html`：每日 HTML 日报。
- `site/repos/owner__repo.html`：项目详情。
- `daily/YYYY-MM-DD.md`：Markdown 日报。
- `repos/owner__repo.md`：Markdown Wiki 项目卡。

## 数据边界

Trending 的候选算法和覆盖范围并未完全公开。本项目保存页面原始排名、周期 Stars、来源 URL、采集时间和 SHA-256，但不会把 Trending 榜单描述成全站精确净增审计。
