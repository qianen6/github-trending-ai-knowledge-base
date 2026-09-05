# GitHub Trending 项目雷达工作流 v4

本文件只定义每日执行顺序和产物。评分、License与去重语义以 [SCREENING_RULES.md](SCREENING_RULES.md) 为准，逐项目中文介绍以 [CARD_CONTENT_SPEC.md](CARD_CONTENT_SPEC.md) 为准，中文README以 [README_TRANSLATION_SPEC.md](README_TRANSLATION_SPEC.md) 为准，展示样式以 [DESIGN.md](DESIGN.md) 为准，输入字段以 `schemas/incoming.schema.json` 为准。

## 输入

每天采集21个官方Trending页面：

- Today、This week、This month。
- Global、Python、TypeScript、JavaScript、Jupyter Notebook、Go、Rust。
- Spoken Language：Any。

每页保留URL、采集时间、状态、SHA-256、原始排名、仓库信息、周期Stars和Built by。GitHub未公开完整Trending算法，因此所有输出均称为Trending候选池，不称为全站排名。

全部运行数据统一放在 `workspace/`；所有脚本通过 `WorkspaceLayout` 解析这一数据根目录，项目根目录只保留源码、规则、文档、schema、测试和安装入口。

## 每日执行

```text
collect_trending通过固定矩阵采集21个页面并保存原始HTML、SHA-256、缓存与失败记录
→ 可选读取GitHub API并保存README、License、根代码树等证据索引
→ 生成页面级规范化JSON
→ 按full_name合并全部appearances
→ 读取catalog，复用已收录项目的稳定证据
→ 对未收录项目做静态源码核验
→ 对每个候选单独提取项目问题、输入、处理、输出、功能、优势和限制
→ 按CARD_CONTENT_SPEC生成中文card，不复用类别模板或旧卡片套话
→ 写入workspace/proof/run-YYYY-MM-DD/incoming.candidate.json草稿
→ validate-cards执行逐仓库中文语义检查与批次反模板检查
→ 通过后原子写入schema_version=4的incoming正式批次
→ ingest计算H/T/Q/V/F并更新长期目录
→ 生成结构化daily/YYYY-MM-DD.json（DailyEdition），固定日/周/月榜与前端展示并集
→ 在.kb-state/staging暂存整次运行，整体验证后提交；失败恢复旧文件
→ 计算前端日榜、周榜、月榜项目并集，仅为这些项目获取官方README
→ 中文README原样复制；英文README按原文顺序完整翻译为中文
→ 写入readmes/manifest.json与readmes/owner__repo.zh-CN.md
→ readme_translations validate校验数量、来源哈希、译文哈希与中文正文
→ build_site从DailyEdition生成Markdown对应的离线HTML
→ engine/site/unit tests校验
```

静态核验读取元数据、README、代码树、入口、核心流程和代表性测试或配置；License读取实际许可证文件。禁止克隆、安装、导入或执行候选仓库。

## 中文项目卡片关卡

项目卡片的解释性文案必须使用中文，项目名以及 GIS、Jupyter、WebAssembly 等必要技术名词可以保留原文，但不得把英文仓库简介原样包在中文套话中。

- `一句话介绍`：直接说明项目是什么以及能解决什么问题，不以编程语言或仓库类别代替产品说明。
- `项目是做什么的`：用中文解释目标问题、核心工作方式和主要输出。
- `主要功能`：只写用户实际能够完成的任务或项目提供的领域能力，例如可视化、分析、转换、部署、协作或自动化；不得写 README、依赖清单、源码入口、测试或 CI 等仓库核验证据。
- `主要优点`：只写项目相对其他方案或传统流程的实际优势，例如跨平台、隐私、性能、易用性、生态兼容或部署成本；不得把进入 Trending、README 清楚、存在测试或 CI 当成项目优点。
- `明确不足`：写使用项目时真实存在的能力边界、资源要求或适用条件；“本知识库没有运行项目”属于判断边界，不是项目自身不足。

README、依赖、入口、测试和 CI 证据只进入 `quality.rationale` 与 `evidence_urls`，Trending 排名和 Stars 只进入趋势说明与评分字段。

复用已收录项目的稳定证据不等于复用旧卡片套话；每次生成 `incoming` 时都必须重新检查 `card` 字段。旧卡片若仍把仓库核验证据写成功能或优点，必须先按项目 README 的真实能力重写，不能直接复制到新批次。确定性脚本不得根据编程语言、类别、目录结构、测试或 CI 自动拼接功能和优点。

采集实现位于 `src/github_trending_kb/collector.py`。远程GitHub与保存的HTML夹具是两个Adapter；页面解析、缓存、重试、限流响应和哈希验证集中在同一Module。语义卡片仍由Codex依据证据逐项目撰写。

采集命令只有在21页和所请求证据均成功时输出 `COLLECT PASS`；存在失败时输出 `COLLECT PARTIAL` 并返回非零状态。重跑会复用已保存HTML和稳定证据，只补失败部分。

整个批次必须同时满足：每个字段通过中文与禁用套话检查；不同仓库不得复用完全相同的 `features` 或 `strengths`；功能与优点各至少两条。任一仓库失败时，整批停留在运行目录的草稿状态，不得覆盖正式 `incoming`、目录或站点。

## 执行命令

```powershell
python -m pip install -r requirements.txt
python -m pip install --no-deps -e .
$dataRoot = "workspace"
python scripts/collect_trending.py --root . --date YYYY-MM-DD --evidence
python scripts/trending_engine.py validate-cards --root . --input "$dataRoot/proof/run-YYYY-MM-DD/incoming.candidate.json"
python scripts/trending_engine.py ingest --root . --input "$dataRoot/incoming/YYYY-MM-DD.json"
python scripts/readme_translations.py validate --root .
python scripts/build_site.py --root .
python scripts/trending_engine.py validate --root .
python scripts/validate_site.py --root .
python -m unittest discover -s tests -p "test_*.py"
```

## 产物链

```text
workspace/trending/html + workspace/trending/evidence + workspace/proof/run-YYYY-MM-DD/collection.json
→ workspace/trending/snapshots
→ workspace/proof/run-YYYY-MM-DD/incoming.candidate.json
→ validate-cards
→ workspace/incoming
→ workspace/evaluations + workspace/rejections
→ workspace/catalog + workspace/repos + workspace/daily
→ workspace/daily/YYYY-MM-DD.json DailyEdition
→ workspace/.kb-state/commits/YYYY-MM-DD.json publication manifest
→ workspace/readmes/manifest.json + workspace/readmes/*.zh-CN.md
→ readme_translations validate
→ site
```

## 完成条件

1. 21个页面均有成功或明确失败记录。
2. 去重后的全部候选都有评估对象。
3. `full_name`在目录和三个面板中均不重复。
4. 每个项目都有证据、评分和中文License作用域。
5. 每个项目卡片均按 `CARD_CONTENT_SPEC.md` 单独撰写，功能和优点各至少两条，且批次内没有重复模板。
6. `validate-cards` 输出 `CARD VALIDATE PASS` 后才生成正式incoming。
7. 所有前端榜单项目都有来源哈希匹配的中文README，并在详情页内完整显示；未展示项目不要求汉化。
8. Markdown与HTML链接完整。
9. ingest、README validator、build、两个validator和单元测试全部通过。
10. 当日DailyEdition通过验证，且最新publication manifest中的文件哈希全部匹配。

日报只呈现今日概览以及日榜、周榜、月榜精选；淘汰原因保存在 `rejections/`，不在读者页面展示。

## v5.1：可靠发布、全库目录与可恢复运行

- `workspace/site/catalog.html` 提供全部收录项目的静态目录、关键词/分类/语言筛选；关闭 JavaScript 后仍可进入全部项目。
- 项目详情提供章节跳转、最后评估时间和评分说明；新增目录不扩大中文 README 的必需覆盖集合。
- 官方 README 原文按内容哈希保存在 `workspace/readmes/sources/<sha256>.md`，manifest 的 `source_artifact` 指向它。校验真实原文、source-copy 正文、译文代码块及标题结构，而非仅比较两个自报哈希。
- build 入口自行执行 README 与暂存站点校验，失败保留旧站；内容哈希缓存复用未变的渲染片段，`--no-cache` 可做全量对照。
- 采集复用检查文件、SHA-256、JSON 及有效期；默认官方仓库证据最多跨 1 天复用，`--evidence-max-age-days 0` 禁止跨日复用。错误 HTML 不再冒充空榜，合法空榜仍支持。
- 发布恢复使用匹配的 transaction_id 判断清理或回滚；系统文件锁阻止活动写入被另一进程误恢复。

### 推荐的整批发布入口

卡片验收通过、正式 incoming 原子落盘后：

```powershell
python scripts/run_daily.py prepare --root . --input workspace/incoming/YYYY-MM-DD.json
```

输出的 `staging_root` 是本次隔离项目根目录；ingest 已在那里生成 DailyEdition。根据该目录中的榜单并集准备中文 README，并把匹配原文保存至其 `workspace/readmes/sources/`。原文快照也可通过：

```powershell
python scripts/readme_translations.py bind-sources --root STAGING_ROOT --source-dir STAGING_ROOT/workspace/proof/sources
python scripts/readme_translations.py validate --root STAGING_ROOT
python scripts/run_daily.py publish --root . --input workspace/incoming/YYYY-MM-DD.json
python -m unittest discover -s tests -p "test_*.py"
```

`prepare` 不覆盖正式目录或站点；`publish` 复用已准备且指纹一致的暂存数据，完成 README、build、engine、site 关卡后，把数据、译文与站点纳入同一 publication manifest。发布期间正式数据发生变化会中止晋升。若在正式工作区准备译文，可显式传 `--readmes-dir workspace/readmes`，避免误用旧的暂存译文。

已有数据仅需重新验证与建站时：

```powershell
python scripts/run_daily.py verify --root .
python scripts/run_daily.py verify --root . --no-resume
```

阶段输入和输出哈希相同才复用通过结果；失败状态、耗时及缓存结果记录于 `workspace/.kb-state/runs/`。网络采集、语义卡片撰写和翻译仍按证据逐项目完成，不由该命令推测生成。

### 旧演练副本归档

```powershell
# 默认只列计划；日期之前的 run-YYYY-MM-DD/rollback-test 才进入候选。
python scripts/manage_proof.py archive --root . --before YYYY-MM-DD
python scripts/manage_proof.py archive --root . --before YYYY-MM-DD --apply

# 恢复到一个尚不存在的工作区子目录。
python scripts/manage_proof.py restore --root . --archive workspace/proof/run-DATE/rollback-test.zip --target workspace/proof/restored-DATE
```

归档先检查活动 manifest 引用，再压缩并逐文件验证 SHA-256；确认源文件在压缩期间未变化后才移除演练目录。原始 sources、采集证据、日报、正式数据和截止日后的演练副本保留。ZIP 与同目录 `rollback-test.archive.json` 必须一起保存。磁盘收益以实际输出 `saved_bytes` 为准。

