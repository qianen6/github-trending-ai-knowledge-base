# Codex 每日自动任务提示词

建议计划：每天 `09:00`，时区 `Asia/Shanghai`，工作目录为本仓库根目录。

```text
在当前项目根目录执行每日 GitHub Trending 项目知识库更新。开始前读取 README.md、WORKFLOW.md、SCREENING_RULES.md、DESIGN.md 和 schemas/incoming.schema.json，严格遵守 schema_version=3。

采集 Today / This week / This month × Global / Python / TypeScript / JavaScript / Jupyter Notebook / Go / Rust，共21个官方 Trending 页面，Spoken Language=Any。候选只能来自 Trending。保存原始HTML、页面URL、排名、周期Stars、Built by、采集时间、状态和SHA-256；缺失值写null，失败页显式记录。

按规范化 owner/repo（full_name）全局去重。不要执行AI、行业、用途或其他主题过滤：全部去重仓库都必须进入 candidate_pool 和 repositories；raw_candidate_count必须等于evaluated_candidate_count。

License不参与本工作流：不读取或判断LICENSE/COPYING/NOTICE，不生成科研/工程双轨，也不写license字段或风险标签。

读取catalog.json完成跨日期去重。已经正式收录的full_name只更新趋势和最后评估时间，不重复新增项目卡，也不再次占用日报新增展示位。对未收录项目执行硬过滤、质量分和项目价值分；硬过滤通过项目至少读取入口、核心流程和代表性测试或配置。禁止克隆、安装、导入或执行候选仓库。

incoming中每个repository填写hard_filter、quality、value、evidence_urls，以及card的one_line、what、audience、usage、features、why、strengths、limitations、value。value使用P0-P4项目层级。Q/V逐项评分并附GitHub证据，脚本负责T、F、等级和最终PASS/FAIL。

原子写入 incoming/YYYY-MM-DD.json 后依次执行：

python scripts/trending_engine.py ingest --root . --input incoming/YYYY-MM-DD.json
python scripts/build_site.py --root .
python scripts/trending_engine.py validate --root .
python scripts/validate_site.py --root .
python -m unittest discover -s tests -p "test_*.py"

日报与HTML首页固定分为日榜精选、周榜精选、月榜精选。每个正式通过且尚未收录的项目只进入其相对百分位最强的一个周期；同分按日、周、月顺序归属。每栏最多5个，按F降序，三个面板之间不得重复。

每日Markdown不展示淘汰原因、数据缺口、判断边界、NEW_HOT或REVIVED_HOT分栏。HTML必须无框架、无CDN、无需服务器、使用相对链接并可离线打开。

最终报告页面成功/失败、原始去重候选、完整评估候选、通过筛选、新增收录、累计项目、三个榜单的展示数量与前五，以及Markdown/HTML路径。声明候选来自GitHub Trending，不代表GitHub全站排名。
```
