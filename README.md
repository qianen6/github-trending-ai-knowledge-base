# GitHub Trending 项目知识库

[![Validate workflow](https://github.com/qianen6/github-trending-ai-knowledge-base/actions/workflows/validate.yml/badge.svg)](https://github.com/qianen6/github-trending-ai-knowledge-base/actions/workflows/validate.yml)

一个由 Codex 驱动的 GitHub Trending 每日研究工作流：采集21个官方榜单页面，对全部去重候选做静态核验和四层评分，生成中文项目卡片、日/周/月精选榜、前端项目详情以及忠实汉化的官方 README。

仓库只发布工作流、规则、脚本、测试和空白目录，不捆绑作者机器上的历史榜单、仓库证据或示例结果。克隆后可以从空数据状态开始运行。

## 能得到什么

- `Today / This week / This month × Global / Python / TypeScript / JavaScript / Jupyter Notebook / Go / Rust` 共21页。
- 按 `owner/repo` 全局去重的 Trending 候选池，不冒充 GitHub 全站排名。
- H/T/Q/V/F 静态评分、中文 License 作用域和淘汰记录。
- 每个候选独立撰写的中文功能、优点、使用方式与限制。
- 日榜、周榜、月榜各最多5个项目，全局不重复。
- 仅对前端实际展示项目提供中文 README：中文原文直接采用，英文原文完整忠实翻译。
- 可直接用 `file://` 打开的静态 HTML 知识站，支持 README 图片、视频、表格、代码块和原生HTML。

## 30秒安装

要求：Python 3.11+，推荐 Python 3.12。

### Windows PowerShell

```powershell
git clone https://github.com/qianen6/github-trending-ai-knowledge-base.git
cd github-trending-ai-knowledge-base
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

### macOS / Linux

```bash
git clone https://github.com/qianen6/github-trending-ai-knowledge-base.git
cd github-trending-ai-knowledge-base
chmod +x setup.sh
./setup.sh
```

安装脚本会创建 `.venv`、安装依赖、初始化空目录、生成空站点，并运行全部验证和测试。完成后可直接打开：

```text
site/index.html
```

## 最简单的每日使用方式

1. 在 Codex 中打开仓库目录。
2. 将 [`AUTOMATION_PROMPT.md`](AUTOMATION_PROMPT.md) 中的提示词交给 Codex，或者创建每天 `09:00 Asia/Shanghai` 的自动任务。
3. Codex 会读取根目录 [`AGENTS.md`](AGENTS.md)，完成采集、静态核验、卡片生成、README汉化、建站和验证。
4. 完成后打开 `site/index.html`。

所有高风险中间写入都先落到 `proof/run-YYYY-MM-DD/` 草稿；卡片、README和站点关卡通过后才写入正式产物。

## 固定验证顺序

当 `incoming/YYYY-MM-DD.json` 和前端 README 已由代理生成后，确定性阶段按以下顺序运行：

```powershell
python scripts/trending_engine.py validate-cards --root . --input proof/run-YYYY-MM-DD/incoming.candidate.json
python scripts/trending_engine.py ingest --root . --input incoming/YYYY-MM-DD.json
python scripts/readme_translations.py validate --root .
python scripts/build_site.py --root .
python scripts/trending_engine.py validate --root .
python scripts/validate_site.py --root .
python -m unittest discover -s tests -p "test_*.py"
```

## 核心规则

- 候选只来自 GitHub Trending，不做主题预过滤。
- 去重后每个候选都必须进入评估，`raw_candidate_count == evaluated_candidate_count`。
- 禁止克隆、安装、导入或执行候选仓库。
- License 只记录名称、证据链接和中文作用域，不参与评分或门槛。
- 项目功能回答“用户能用它做什么”；项目优点回答“项目本身好在哪里”。
- 测试、CI、依赖和源码入口只进入质量证据，不能冒充功能或优点。
- 英文 README 必须完整翻译，不摘要；中文 README 直接采用官方内容。
- README原生HTML经过白名单清洗后渲染，脚本、iframe、表单和内联样式不会进入站点。

## 文档入口

- [`AGENTS.md`](AGENTS.md)：Codex 强制执行契约。
- [`WORKFLOW.md`](WORKFLOW.md)：每日顺序、产物链和完成条件。
- [`SCREENING_RULES.md`](SCREENING_RULES.md)：H/T/Q/V/F、License、去重和榜单规则。
- [`CARD_CONTENT_SPEC.md`](CARD_CONTENT_SPEC.md)：中文项目卡片规范。
- [`README_TRANSLATION_SPEC.md`](README_TRANSLATION_SPEC.md)：中文 README 直译/复用规范。
- [`DESIGN.md`](DESIGN.md)：离线站点视觉、媒体与响应式规则。
- [`schemas/incoming.schema.json`](schemas/incoming.schema.json)：输入字段契约。

## 目录结构

```text
incoming/       每日原子输入
evaluations/    全部候选评分
rejections/     淘汰记录
repos/          中文项目卡片
readmes/        前端项目中文README
daily/          每日日报
trending/       规范化页面与历史快照
site/           离线HTML站点
proof/          本地抓取、草稿和回滚证明（默认不提交）
```

## 数据与发布边界

GitHub 没有公开完整 Trending 算法。本项目保存和分析的是官方 Trending 页面中可见的候选集合，不代表 GitHub 全站排名，也不声称项目已经安装运行或适合生产采用。

本仓库默认不包含历史运行数据。若要分享自己的每日知识库，可以选择提交 `incoming/`、`evaluations/`、`repos/`、`readmes/`、`daily/`、`site/` 和 `trending/snapshots/`；原始页面、证据缓存和密钥应留在本地。
