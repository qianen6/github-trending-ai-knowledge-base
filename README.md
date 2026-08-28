# GitHub Trending 项目知识库

一个基于 GitHub Trending 的通用项目发现与长期知识库工具。每天采集日榜、周榜、月榜及主要语言榜，对全部去重候选执行四层筛选，再生成 Markdown Wiki 与可离线浏览的 HTML 面板。

## 当前原则

- 候选只来自 GitHub Trending，不代表 GitHub 全站排名。
- 不进行 AI、行业或用途主题预过滤。
- 不克隆、不安装、不执行候选仓库。
- License只记录名称、证据链接和中文作用域说明，不参与筛选或评分。
- 当天、跨周期、跨语言、跨日期统一按 `owner/repo` 去重。
- 已经收录的项目只更新信息，不重复创建项目卡或占用新增展示位。
- 展示面板分为日榜、周榜、月榜；一个项目只进入相对表现最强的一个面板。

## 四层筛选

```text
H 硬过滤
→ T Trending趋势分
→ Q 静态质量分
→ V 项目价值分
→ F 综合分
```

完整规则：

- [工作流](WORKFLOW.md)
- [四层筛选规则](SCREENING_RULES.md)
- [项目索引](index.md)

## 数据入口

- `incoming/`：每日页面与仓库证据批次。
- `trending/raw/`：页面级规范化快照。
- `trending/snapshots/`：按仓库合并后的快照。
- `evaluations/`：H/T/Q/V评分与PASS/FAIL。
- `daily/`：Markdown日报。
- `repos/`：长期项目卡，同一仓库只有一张。
- `rejections/`：内部淘汰记录。
- `site/`：离线HTML知识站。

## 执行

```powershell
python scripts/trending_engine.py ingest --root . --input incoming/YYYY-MM-DD.json
python scripts/build_site.py --root .
python scripts/trending_engine.py validate --root .
python scripts/validate_site.py --root .
python -m unittest discover -s tests -p "test_*.py"
```

打开 `site/index.html` 即可查看日榜、周榜和月榜面板。
