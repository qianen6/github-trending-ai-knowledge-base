# Codex 每日自动任务提示词

建议计划：每天 `09:00`，时区 `Asia/Shanghai`，工作目录为本仓库根目录。

```text
在当前项目根目录执行每日 GitHub Trending AI 知识库更新。开始前读取 README.md、WORKFLOW.md、SCREENING_RULES.md、DESIGN.md 和 schemas/incoming.schema.json，并严格遵守固定格式。

采集 Today / This week / This month × Global / Python / TypeScript / JavaScript / Jupyter Notebook / Go / Rust，共 21 个官方 GitHub Trending 页面，Spoken Language=Any。候选只能来自 Trending。保存页面 URL、原始排名、周期 Stars、Built by、采集时间和 SHA-256；缺失值写 null，失败页显式记录。

按 owner/repo 去重，只选择 AI、Agent、机器人与具身智能、科研自动化、AI 内容生产、AI 安全、模型推理与路由、Agent 记忆及开发者 AI 基础设施进入四层评分，并记录原始候选数和主题候选数。

对每个主题候选读取仓库元数据、README、实际 LICENSE/COPYING/NOTICE、模型/数据/资产许可、代表性入口、核心流程、测试或 CI。GitHub API 的 NOASSERTION 不能直接视为没有许可证。禁止克隆、安装、导入或执行候选仓库。

每个候选必须填写 hard_filter、license、quality、ai_value，以及 card 的 one_line、what、audience、usage、features、why、strengths、limitations、ai。卡片使用普通人可以理解的中文。源码证据用于内部 Q/V 评分和准确性核验，但不在读者页面展示调用链或文件/函数证据表。

原子写入 incoming/YYYY-MM-DD.json 后执行：

python scripts/trending_engine.py ingest --root . --input incoming/YYYY-MM-DD.json
python scripts/build_site.py --root .
python scripts/trending_engine.py validate --root .
python scripts/validate_site.py --root .
python -m unittest discover -s tests -p "test_*.py"

每日 Markdown 只展示今日概览、NEW_HOT 和 REVIVED_HOT；每个正式收录项目必须有一句话介绍。不展示淘汰原因、数据缺口或判断边界。同步生成 site/index.html、site/daily/YYYY-MM-DD.html 和 site/repos/owner__repo.html；HTML 必须无框架、无 CDN、无需服务器、使用相对链接并可离线打开。

最终报告页面成功/失败、原始候选、主题候选、正式收录、NEW_HOT 与 REVIVED_HOT 前五，以及 Markdown/HTML 路径。声明候选来自 GitHub Trending，不代表 GitHub 全站排名。
```

