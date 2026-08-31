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

### 推荐：让 Codex 安装并创建每日任务

先克隆仓库，然后在 **Codex 桌面应用**中打开下载后的仓库目录：

```powershell
git clone https://github.com/qianen6/github-trending-ai-knowledge-base.git
cd github-trending-ai-knowledge-base
```

只需向 Codex 发送一次：

```text
安装这个仓库并创建每日任务
```

Codex 会按照 [`CODEX_SETUP.md`](CODEX_SETUP.md) 运行安装脚本，创建独立的 `workspace/` 运行目录，并调用 Codex 自动任务工具，为**下载者自己的仓库路径**创建或更新每天 `09:00 Asia/Shanghai` 的 `ACTIVE` 任务。以后无需每天粘贴提示词。

### 仅手工安装本地依赖

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

安装脚本会创建 `.venv`、以可编辑包安装 `src/github_trending_kb`、初始化 `workspace/`、生成空站点，并运行全部验证和测试。完成后可直接打开：

```text
workspace/site/index.html
```

## 每日自动运行

1. 首次下载后，在 Codex 中发送一次 `安装这个仓库并创建每日任务`。
2. Codex 读取 [`.codex/daily-task.json`](.codex/daily-task.json)，创建或更新与当前下载路径绑定的每日任务。
3. 每天到点后，确定性采集Module先保存21页原始HTML、哈希与证据缓存；Codex再完成静态核验、卡片生成和README汉化。
4. DailyEdition固定榜单和README覆盖集合，整次发布通过事务manifest后生成站点；打开 `workspace/site/index.html` 查看结果。

所有高风险中间写入都先落到 `workspace/proof/run-YYYY-MM-DD/` 草稿；卡片、README和站点关卡通过后才写入正式产物。

## 固定验证顺序

当 `workspace/incoming/YYYY-MM-DD.json` 和前端 README 已由代理生成后，确定性阶段按以下顺序运行：

```powershell
$dataRoot = "workspace"
python scripts/trending_engine.py validate-cards --root . --input "$dataRoot/proof/run-YYYY-MM-DD/incoming.candidate.json"
python scripts/trending_engine.py ingest --root . --input "$dataRoot/incoming/YYYY-MM-DD.json"
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
- [`CODEX_SETUP.md`](CODEX_SETUP.md)：Codex 本地安装与每日任务注册契约。
- [`.codex/daily-task.json`](.codex/daily-task.json)：可移植的每日任务参数。
- [`WORKFLOW.md`](WORKFLOW.md)：每日顺序、产物链和完成条件。
- [`SCREENING_RULES.md`](SCREENING_RULES.md)：H/T/Q/V/F、License、去重和榜单规则。
- [`CARD_CONTENT_SPEC.md`](CARD_CONTENT_SPEC.md)：中文项目卡片规范。
- [`README_TRANSLATION_SPEC.md`](README_TRANSLATION_SPEC.md)：中文 README 直译/复用规范。
- [`DESIGN.md`](DESIGN.md)：离线站点视觉、媒体与响应式规则。
- [`schemas/incoming.schema.json`](schemas/incoming.schema.json)：输入字段契约。

## 目录结构

```text
src/github_trending_kb/  可导入的核心Module
scripts/                 CLI Adapter
schemas/                 输入契约
tests/                   自动测试
workspace/               唯一运行数据根目录（默认不提交）
  incoming/              每日原子输入
  evaluations/           全部候选评分
  rejections/            淘汰记录
  repos/                 中文项目卡片
  readmes/               前端项目中文README
  daily/                 DailyEdition与日报
  trending/              原始页面、证据和历史快照
  site/                  离线HTML站点
  proof/                 草稿与回滚证明
```


## 数据与发布边界

GitHub 没有公开完整 Trending 算法。本项目保存和分析的是官方 Trending 页面中可见的候选集合，不代表 GitHub 全站排名，也不声称项目已经安装运行或适合生产采用。

本仓库默认不包含历史运行数据。若要分享自己的每日知识库，可以选择发布 `workspace/incoming/`、`workspace/evaluations/`、`workspace/repos/`、`workspace/readmes/`、`workspace/daily/`、`workspace/site/` 和 `workspace/trending/snapshots/`；原始页面、证据缓存和密钥应留在本地。
