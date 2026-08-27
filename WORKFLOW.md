# GitHub Trending 项目雷达工作流 v2

## 目标

以 GitHub Trending 为唯一自动候选源，发现正在获得关注的项目，再通过“硬过滤 → 趋势分 → 静态质量分 → AI价值分”筛出值得学习研究或工程关注的项目。

本工作流是**信息收集工具**：不克隆、不安装、不执行候选仓库。

## 候选源

每天北京时间 09:00 采集 GitHub Trending：

- 时间范围：Today、This week、This month。
- 范围：Global、Python、TypeScript、JavaScript、Jupyter Notebook、Go、Rust。
- Spoken Language：Any。

每次采集保存：

- 完整采集时间和时区。
- 页面 URL、时间范围、语言与 Spoken Language。
- 原始页面顺序。
- `owner/repo`、简介、主要语言、总 Stars、总 Forks。
- 页面展示的 `stars today`、`stars this week` 或 `stars this month`。
- Built by 账号列表。
- 规范化页面快照 JSON 和 SHA-256。

GitHub Trending 的候选算法、精确统计边界和完整覆盖范围未公开，因此所有报告必须写明“Trending 候选池”，不得称为 GitHub 全站排行。

## 每日流程

```text
采集21个Trending页面（7个范围 × 3个周期）
  ↓
保存原始规范化页面快照与SHA-256
  ↓
按owner/repo合并、去重
  ↓
按知识库主题筛选AI、Agent、机器人、科研自动化、AI内容生产和开发者AI基础设施项目；保留原始候选总数与筛选理由
  ↓
GitHub API与README/关键源码补充静态证据
  ↓
写incoming/YYYY-MM-DD.json
  ↓
trending_engine.py ingest
  ↓
硬过滤 H：PASS/FAIL
  ↓
趋势分 T：页面周期Stars、排名变化、连续上榜
  ↓
静态质量分 Q
  ↓
AI价值分 V 与 L0-L4
  ↓
正式知识库、日报和淘汰记录
  ↓
根据固定Markdown模板生成项目卡与日报
  ↓
build_site.py生成离线HTML首页、日报和项目详情
  ↓
trending_engine.py validate
```

## 项目年龄标签

- `NEW_HOT`：仓库创建不超过 90 天。
- `REVIVED_HOT`：仓库创建超过 90 天，但进入当前 Trending 候选池。

两类项目分开展示，不混淆“新项目”和“老项目重新走红”。项目年龄不再作为硬过滤失败条件。

## Trending 数据边界

- `trending_period_stars` 是 GitHub 页面直接展示的周期指标。
- `rank_delta` 是本知识库相邻采集日的页面排名变化。
- 页面未展示的值必须写 `null`，不得写 0 冒充已知。
- Trending 数据与仓库 API 数据分开保存，不互相冒充。
- 若候选不在 Trending 页面，不进入自动筛选；人工指定项目可以另行评估，但不参与趋势榜。

## 确定性边界

- 自动任务负责页面采集、仓库证据阅读，以及 Q/V 各维度的证据化评分。
- `scripts/trending_engine.py` 负责去重、Trending 百分位、排名变化、T/F 总分、阈值、PASS/FAIL、等级和输出。
- 自动任务不得手工覆盖 T、F、最终状态或等级。
- Q/V 必须逐项打分，并附理由与 GitHub 证据链接；脚本校验分值上限和总和。

## 目录

```text
项目根目录
├── README.md
├── WORKFLOW.md
├── SCREENING_RULES.md
├── index.md
├── catalog.json
├── incoming/YYYY-MM-DD.json
├── trending/raw/YYYY-MM-DD/*.json
├── trending/snapshots/YYYY-MM-DD.json
├── evaluations/YYYY-MM-DD.json
├── daily/YYYY-MM-DD.md
├── repos/owner__repo.md
├── rejections/YYYY-MM-DD.json
├── scripts/trending_engine.py
├── scripts/build_site.py
├── scripts/validate_site.py
├── schemas/incoming.schema.json
├── DESIGN.md
├── site/index.html
├── site/daily/YYYY-MM-DD.html
├── site/repos/owner__repo.html
└── site/style.css
```

## 完成定义

1. 21 个页面均有成功或明确失败记录。
2. 原始页面快照、incoming 和 Trending snapshot JSON 可解析。
3. `owner/repo` 去重键唯一。
4. 页面周期 Stars、排名和页面 URL 可追溯。
5. 每个正式评估项目都有 H、T、Q、V、License 双轨与证据。
6. 日报区分 NEW_HOT 与 REVIVED_HOT。
7. 执行 `python scripts/trending_engine.py validate --root .` 成功。
8. 执行 `python scripts/build_site.py --root .` 生成HTML。
9. 执行 `python scripts/validate_site.py --root .`，确认固定章节、HTML数量和相对链接全部通过。

## 固定展示格式

- 每日日报只展示今日概览、NEW_HOT和REVIVED_HOT；每个项目必须有一句话介绍。
- 日报不展示淘汰原因、数据缺口或判断边界。
- 项目卡固定展示：一句话介绍、项目是做什么的、适合谁、使用方式、主要功能、为什么值得关注、主要优点、明确不足、AI价值判断、Trending表现与综合评分、项目链接。
- 核心源码阅读用于内部评分，不在读者页面展示调用链、文件/函数证据表或技术审计章节。
