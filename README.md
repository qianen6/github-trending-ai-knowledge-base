# GitHub Trending 项目知识库

每天采集 GitHub Trending 日榜、周榜、月榜及主要语言榜，对全部去重候选进行静态评估，生成 Markdown Wiki 与离线 HTML 面板。

## 核心约束

- 候选只来自 GitHub Trending，不做主题预过滤。
- 当天、跨周期、跨语言和跨日期统一按 `owner/repo` 去重。
- License只记录名称、证据链接和中文作用域，不参与评分。
- 不克隆、不安装、不执行候选仓库。
- 一个新增项目只进入日榜、周榜或月榜中的一个面板。

## 文档入口

- [WORKFLOW.md](WORKFLOW.md)：采集、处理、输出和校验顺序。
- [SCREENING_RULES.md](SCREENING_RULES.md)：H/T/Q/V/F、License、去重和面板规则。
- [DESIGN.md](DESIGN.md)：HTML视觉与响应式规范。
- [index.md](index.md)：长期项目索引。
- `site/index.html`：离线知识站首页。

## 执行

```powershell
python scripts/trending_engine.py ingest --root . --input incoming/YYYY-MM-DD.json
python scripts/build_site.py --root .
python scripts/trending_engine.py validate --root .
python scripts/validate_site.py --root .
python -m unittest discover -s tests -p "test_*.py"
```

主要产物依次位于 `incoming/`、`evaluations/`、`repos/`、`daily/` 和 `site/`。

