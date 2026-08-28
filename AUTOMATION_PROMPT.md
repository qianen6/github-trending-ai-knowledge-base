# Codex 每日自动任务提示词

建议计划：每天 `09:00`，时区 `Asia/Shanghai`，工作目录为仓库根目录。

```text
执行每日GitHub Trending知识库更新。先读取README.md、WORKFLOW.md、SCREENING_RULES.md、DESIGN.md和schemas/incoming.schema.json；这些文件分别是入口、执行、规则、视觉和字段的唯一来源。

不可变约束：
1. 采集Today/This week/This month × Global/Python/TypeScript/JavaScript/Jupyter Notebook/Go/Rust共21页，Spoken Language=Any。
2. 候选只来自Trending，不做主题预过滤；按full_name去重，并保证raw_candidate_count等于evaluated_candidate_count。
3. 已收录项目只更新，不重复新增卡片或面板。
4. License只填写name、scope_zh、evidence_urls，不参与评分、门槛或合规判断。
5. 禁止克隆、安装、导入或执行候选仓库；证据深度遵守WORKFLOW。
6. 不手工覆盖T、F、等级或最终状态。

原子写入schema_version=4的incoming/YYYY-MM-DD.json后依次执行：
python scripts/trending_engine.py ingest --root . --input incoming/YYYY-MM-DD.json
python scripts/build_site.py --root .
python scripts/trending_engine.py validate --root .
python scripts/validate_site.py --root .
python -m unittest discover -s tests -p "test_*.py"

日报与首页按日榜、周榜、月榜展示，每栏最多5个且全局不重复。项目详情包含中文License作用域。最终报告页面采集状态、去重/评估/通过/新增/累计数量、三个榜单前五和Markdown/HTML路径，并声明候选来自Trending而非GitHub全站排名。
```
