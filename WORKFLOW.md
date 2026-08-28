# GitHub Trending 项目雷达工作流 v4

本文件只定义每日执行顺序和产物。评分、License与去重语义以 [SCREENING_RULES.md](SCREENING_RULES.md) 为准，展示样式以 [DESIGN.md](DESIGN.md) 为准，输入字段以 `schemas/incoming.schema.json` 为准。

## 输入

每天采集21个官方Trending页面：

- Today、This week、This month。
- Global、Python、TypeScript、JavaScript、Jupyter Notebook、Go、Rust。
- Spoken Language：Any。

每页保留URL、采集时间、状态、SHA-256、原始排名、仓库信息、周期Stars和Built by。GitHub未公开完整Trending算法，因此所有输出均称为Trending候选池，不称为全站排名。

## 每日执行

```text
采集21个页面并保存原始HTML
→ 生成页面级规范化JSON
→ 按full_name合并全部appearances
→ 读取catalog，复用已收录项目的稳定证据
→ 对未收录项目做静态源码核验
→ 写入schema_version=4的incoming批次
→ ingest计算H/T/Q/V/F并更新长期目录
→ build_site生成Markdown对应的离线HTML
→ engine/site/unit tests校验
```

静态核验读取元数据、README、代码树、入口、核心流程和代表性测试或配置；License读取实际许可证文件。禁止克隆、安装、导入或执行候选仓库。

## 执行命令

```powershell
python scripts/trending_engine.py ingest --root . --input incoming/YYYY-MM-DD.json
python scripts/build_site.py --root .
python scripts/trending_engine.py validate --root .
python scripts/validate_site.py --root .
python -m unittest discover -s tests -p "test_*.py"
```

## 产物链

```text
trending/html + trending/raw
→ trending/snapshots
→ incoming
→ evaluations + rejections
→ catalog + repos + daily
→ site
```

## 完成条件

1. 21个页面均有成功或明确失败记录。
2. 去重后的全部候选都有评估对象。
3. `full_name`在目录和三个面板中均不重复。
4. 每个项目都有证据、评分和中文License作用域。
5. Markdown与HTML链接完整。
6. ingest、build、两个validator和单元测试全部通过。

日报只呈现今日概览以及日榜、周榜、月榜精选；淘汰原因保存在 `rejections/`，不在读者页面展示。

