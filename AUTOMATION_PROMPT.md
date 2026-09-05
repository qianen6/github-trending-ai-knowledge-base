# Codex 每日自动任务提示词

建议计划：每天 `09:00`，时区 `Asia/Shanghai`，工作目录为仓库根目录。

首次安装时，在 Codex 桌面应用中打开仓库并发送 `安装这个仓库并创建每日任务`。Codex 会按照 [`CODEX_SETUP.md`](CODEX_SETUP.md) 读取本文件并实际注册任务，不需要手工复制下面的长提示词。

将下面整段提示词交给 Codex；仓库根目录的 `AGENTS.md` 会提供同一套强制约束。

```text
执行今天的 GitHub Trending 项目知识库更新。

开始前依次读取 AGENTS.md、README.md、WORKFLOW.md、SCREENING_RULES.md、CARD_CONTENT_SPEC.md、README_TRANSLATION_SPEC.md、DESIGN.md 和 schemas/incoming.schema.json，并以这些文件为唯一执行契约。

必须完成：
1. 先运行 `python scripts/collect_trending.py --root . --date YYYY-MM-DD --evidence`，确定性采集 Today/This week/This month × Global/Python/TypeScript/JavaScript/Jupyter Notebook/Go/Rust 共21页，Spoken Language=Any；读取 `workspace/proof/run-YYYY-MM-DD/collection.json`，保留页面哈希、缓存和明确失败记录。若输出 `COLLECT PARTIAL`，只重试失败页面或证据，不得用猜测补齐。
2. 候选仅来自 Trending；按 full_name 去重，raw_candidate_count 必须等于 evaluated_candidate_count。
3. 静态核验每个候选的元数据、README、License、代码树和代表性源码/测试/配置；不克隆、不安装、不导入、不执行候选仓库。
4. 为每个候选单独生成中文 card；功能写用户能做什么，优点写项目自身优势，禁止测试/CI/README/Trending套话和跨项目复用模板。
5. 先写 `workspace/proof/run-YYYY-MM-DD/incoming.candidate.json`，执行 validate-cards；通过后才原子写入 `workspace/incoming/YYYY-MM-DD.json` ，然后用 `python scripts/run_daily.py prepare --root . --input workspace/incoming/YYYY-MM-DD.json` 在返回的 staging_root 内 ingest。
6. 暂存目录内的 ingest必须生成结构化DailyEdition和publication manifest。前端日榜/周榜/月榜及其项目并集以DailyEdition为唯一事实；只为这些项目准备中文 README：中文官方README原样复制，英文官方README完整忠实翻译，不摘要、不重组、不省略实质内容。
7. 在 staging_root 内准备译文和按 source_sha256 命名的官方 raw 快照，更新 source_artifact 并执行 README validator；用 `python scripts/run_daily.py publish --root . --input workspace/incoming/YYYY-MM-DD.json` 统一校验并发布。失败只补对应暂存阶段，不覆盖正式站点；项目详情必须正确渲染Markdown、原生HTML、图片、视频、表格、代码块和折叠区块。
8. 严格按 WORKFLOW.md 的命令顺序完成 build、engine validate、site validate 和单元测试，并核对最新publication manifest哈希。

最终用中文报告21页采集状态、页面记录数、去重/评估/通过/淘汰/新增/累计数量、日/周/月榜前五、README汉化数量、验证结果、Markdown/HTML路径，并注明候选来自GitHub Trending而非GitHub全站排名。
```
