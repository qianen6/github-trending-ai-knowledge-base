# 中文 README 本地化规范

只有实际出现在前端日榜、周榜或月榜中的项目需要中文 README。中文 README 必须直接采用官方 README：官方 README 已以中文为主时原样复制；官方 README 为英文时完整翻译为中文。它不是项目卡片的扩写，也不是摘要。

## 产物

```text
readmes/manifest.json
readmes/owner__repo.zh-CN.md
```

需要汉化的集合是所有历史日报中日榜、周榜、月榜项目的并集。详情页在“中文 README”章节中内嵌本地化全文；未进入任何前端榜单的目录项目不生成中文 README。

## 文件格式

```markdown
---
full_name: owner/repo
source_url: https://github.com/owner/repo/blob/main/README.md
source_sha256: 原始README的SHA-256
language: zh-CN
mode: faithful-translation
---

# 中文 README｜项目名

## 项目简介
...
```

`mode` 为 `faithful-translation` 时正文是英文 README 的完整中文翻译；为 `source-copy` 时正文必须直接复制以中文为主的官方 README。

## 翻译规则

1. 英文 README 按原文顺序逐段完整翻译，不总结、不重组、不压缩、不省略实质内容。
2. 项目名、API、协议名、参数名和必要技术术语可以保留原文。
3. 代码块、命令、环境变量、文件路径、URL、版本号和配置键保持原样。
4. 徽章、头像和纯装饰图片可以省略；其他章节、表格、列表、示例与说明保留。
5. 不新增原 README 未声明的功能、性能、平台、许可证或安全结论。
6. 官方 README 已以中文为主时，不调用翻译，正文直接复制官方内容。
7. 译文必须以中文为主，禁止保留大段未翻译英文或“待翻译”占位符。

## 更新与复用

- 以原 README 内容的 SHA-256 判断是否可复用。
- `source_sha256` 未变化时可复用现有中文 README。
- 原 README 变化时必须重新生成译文、更新译文 SHA-256 和 `manifest.json`。
- 新进入前端榜单的项目在建站前必须完成本地化；未展示项目不生成译文。

## 校验命令

```powershell
python scripts/readme_translations.py validate --root .
```

只有输出 `README VALIDATE PASS` 后才允许执行 `build_site.py`。相对链接仅在渲染详情页时转换为 GitHub 绝对链接，存储的中文 README 保持官方原文或直译内容。`validate_site.py` 会再次检查译文数量、哈希、中文正文以及详情页内嵌章节。

## Codex 可复用提示词

```text
请把给定的官方英文 README 完整、忠实地翻译成中文 Markdown。

要求：
1. 按原文顺序逐段翻译，不总结、重组、压缩或省略实质内容。
2. 不添加原文没有的功能或结论。
3. 保留代码块、命令、参数、环境变量、路径、URL、版本号和技术名称。
4. 保留原链接；相对链接由前端渲染阶段转换。
5. 可删除徽章、头像和纯装饰内容；代码示例与主要章节不得省略。
6. 正文以自然中文为主，不保留大段英文，不输出翻译说明或免责声明。
7. 输出完整 Markdown，并使用指定 frontmatter；不要代码围栏包裹整个结果。
```
