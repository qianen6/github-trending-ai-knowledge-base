# GitHub Trending 项目雷达工作流 v3

## 目标

以 GitHub Trending 为唯一自动候选源，不进行 AI 或其他主题预过滤。对全部去重候选执行“硬过滤 → 趋势分 → 静态质量分 → 项目价值分”，筛出值得长期关注的项目，并以 Markdown Wiki 与离线 HTML 保存。

本工作流只做信息收集和静态源码核验：不克隆、不安装、不导入、不执行候选仓库。

## 候选源

每天采集：

- 周期：Today、This week、This month。
- 范围：Global、Python、TypeScript、JavaScript、Jupyter Notebook、Go、Rust。
- Spoken Language：Any。

共 21 个官方 Trending 页面。

每页保存：

- 页面 URL、采集时间、时区、状态和 SHA-256。
- 原始页面排名。
- `owner/repo`、简介、主要语言、总 Stars、总 Forks。
- 页面展示的 `stars today`、`stars this week` 或 `stars this month`。
- Built by 账号。

GitHub Trending 的完整算法与覆盖范围未公开，因此报告只能称为 Trending 候选池，不能称为 GitHub 全站排名。

## 去重规则

1. 当天按规范化 `owner/repo` 去重。
2. 同一项目出现在多个语言榜或多个周期时，只保留一份仓库主体，全部 appearances 作为证据保存。
3. 日榜、周榜、月榜面板使用同一全局已选集合，任何项目只出现一次。
4. 跨日期按 `catalog.json` 中的 `full_name` 去重；已收录项目只更新 `last_evaluated` 和分数，不新建第二张项目卡，也不再次进入新增面板。

## 每日流程

```text
采集21个Trending页面
  → 保存原始HTML与页面级规范化JSON
  → 按owner/repo全局去重
  → 全部去重候选进入评估，不做主题筛选
  → 读取元数据、README、代码树、入口、核心流程、测试或CI
  → 写incoming/YYYY-MM-DD.json（schema_version=3）
  → 硬过滤H
  → 趋势分T
  → 静态质量分Q
  → 项目价值分V与P0-P4
  → 最终分F与PASS/FAIL
  → 长期目录按full_name去重更新
  → 按最强周期分配到日榜/周榜/月榜面板
  → 生成Markdown与离线HTML
  → 完整校验
```

## 证据要求

- 硬过滤至少读取元数据、README、代码树和明确运行路径。
- 进入质量和价值判断的项目必须达到 E2 源码核验：入口、核心流程、代表性测试或配置。
- License只读取仓库实际许可证文件，用中文说明其作用域；不评分、不设门槛，也不生成科研/工程双轨结论。
- Q/V 必须逐项评分，附理由与 GitHub 证据 URL。
- 自动任务不得手工覆盖 T、F、最终状态或等级。

## 项目年龄

- `NEW_HOT`：仓库创建不超过 90 天。
- `REVIVED_HOT`：仓库创建超过 90 天。

年龄标签保留为内部元数据，不再作为日报主分栏；读者面板只按日榜、周榜、月榜呈现。

## Trending 数据边界

- 周期 Stars 使用 GitHub 页面直接展示值。
- 同一周期跨语言榜取最大值。
- 页面未展示的值写 `null`。
- 历史排名变化来自本知识库相邻快照。
- 日榜、周榜、月榜归属取三个周期中相对百分位最高者；同分优先日榜，其次周榜，再次月榜。

## 目录

```text
项目根目录
├── README.md
├── WORKFLOW.md
├── SCREENING_RULES.md
├── DESIGN.md
├── catalog.json
├── index.md
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
├── site/index.html
├── site/daily/YYYY-MM-DD.html
├── site/repos/owner__repo.html
└── site/style.css
```

## 执行顺序

```powershell
python scripts/trending_engine.py ingest --root . --input incoming/YYYY-MM-DD.json
python scripts/build_site.py --root .
python scripts/trending_engine.py validate --root .
python scripts/validate_site.py --root .
python -m unittest discover -s tests -p "test_*.py"
```

## 完成定义

1. 21个页面都有成功或明确失败记录。
2. 去重后的全部 Trending 仓库都有 repository 评估对象，没有主题过滤缺口。
3. 当天、跨周期、跨语言和跨日期均以 `full_name` 去重。
4. 每个候选都有 H、T、Q、V、License中文作用域与证据。
5. 正式项目卡不重复创建。
6. 日榜、周榜、月榜面板之间没有重复仓库，每栏最多5个。
7. Markdown与HTML相对链接完整。
8. ingest、build、engine validate、site validate和单元测试全部通过。

## 固定展示格式

- 日报只展示今日概览、日榜精选、周榜精选和月榜精选。
- 每个项目必须有一句话介绍。
- 日报不展示淘汰原因、数据缺口或判断边界。
- 项目卡展示：一句话介绍、项目是做什么的、适合谁、使用方式、主要功能、为什么值得关注、主要优点、明确不足、License作用域、项目价值判断、Trending表现与综合评分、项目链接。
