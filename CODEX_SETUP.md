# 用 Codex 一键安装并创建每日任务

克隆仓库后，在 **Codex 桌面应用**中打开仓库目录，只发送这一句话：

```text
安装这个仓库并创建每日任务
```

Codex 必须在同一次任务中完成本地安装和每日任务注册；用户不需要复制 `AUTOMATION_PROMPT.md` 中的长提示词。

## Codex 执行契约

当用户发送上面的安装请求或含义相同的请求时，Codex 必须实际执行以下步骤，不能只返回操作说明：

1. 读取 `AGENTS.md`、`.codex/daily-task.json`、`AUTOMATION_PROMPT.md` 和当前操作系统对应的安装脚本。
2. 在仓库根目录运行 `setup.ps1`（Windows）或 `setup.sh`（macOS/Linux），并确认 bootstrap、validators 与单元测试通过。
3. 搜索并调用 Codex 应用的 `automation_update` 工具；调用前用 `list_projects` 取得当前仓库的绝对项目 ID。
4. 检查现有 Codex 自动任务。若 `dedupe_key`、任务名、项目目录或提示词指向本仓库，则更新该任务，不再创建重复任务。
5. 从 `AUTOMATION_PROMPT.md` 提取第一个 `text` 代码块的完整正文作为任务提示词。
6. 按 `.codex/daily-task.json` 创建或更新本地 cron 自动任务：每天 `09:00`、时区 `Asia/Shanghai`、状态 `ACTIVE`、执行环境 `local`、目标和工作目录均为当前仓库根目录。
7. 使用当前 Codex 可用模型；推理强度至少为 `high`。如果更新已有任务，保留用户未要求改变的模型设置。
8. 创建后立即读取任务状态，核对任务 ID、`ACTIVE` 状态、每日计划、项目 ID、工作目录和提示词一致性。

## 完成条件

只有同时满足以下条件才算安装完成：

- 本地安装脚本输出 `SETUP PASS`；
- `.codex/daily-task.json` 通过 bootstrap 校验；
- Codex 自动任务已经创建或更新，而不是仅生成一段建议；
- 自动任务状态为 `ACTIVE`；
- 自动任务绑定下载者自己的仓库绝对路径；
- 自动任务提示词与 `AUTOMATION_PROMPT.md` 的首个 `text` 代码块一致；
- Codex 回报任务名称、运行时间、项目目录和验证结果。

完成一次注册后，Codex 会每天自动启动知识库更新；无需每天再次发送安装命令。
