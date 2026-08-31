from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from scripts.bootstrap import validate_codex_daily_task


ROOT = Path(__file__).resolve().parents[1]


class CodexDailyTaskTests(unittest.TestCase):
    def test_portable_contract_is_valid(self) -> None:
        validate_codex_daily_task(ROOT)

    def test_contract_binds_prompt_and_downloaded_project_root(self) -> None:
        contract = json.loads((ROOT / ".codex" / "daily-task.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["project_root"], ".")
        self.assertEqual(contract["prompt_file"], "AUTOMATION_PROMPT.md")
        self.assertEqual(contract["status"], "ACTIVE")
        self.assertEqual(
            contract["schedule"],
            {"frequency": "daily", "time": "09:00", "timezone": "Asia/Shanghai"},
        )

    def test_prompt_contains_complete_daily_workflow(self) -> None:
        prompt_doc = (ROOT / "AUTOMATION_PROMPT.md").read_text(encoding="utf-8")
        match = re.search(r"```text\s*\n(.*?)\n```", prompt_doc, re.DOTALL)
        self.assertIsNotNone(match)
        prompt = match.group(1)
        self.assertIn("共21页", prompt)
        self.assertIn("validate-cards", prompt)
        self.assertIn("README validator", prompt)
        self.assertIn("单元测试", prompt)

    def test_codex_is_required_to_create_not_just_describe_task(self) -> None:
        setup_doc = (ROOT / "CODEX_SETUP.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for text in (setup_doc, agents):
            self.assertIn("automation_update", text)
            self.assertIn("ACTIVE", text)
        self.assertIn("安装这个仓库并创建每日任务", setup_doc)
        self.assertIn("安装这个仓库并创建每日任务", readme)
        self.assertIn("下载者自己的仓库路径", readme)


if __name__ == "__main__":
    unittest.main()
