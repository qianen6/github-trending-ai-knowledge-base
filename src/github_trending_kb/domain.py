from __future__ import annotations

SCHEMA_VERSION = 4
TREND_PASS = 40.0
QUALITY_PASS = 60
VALUE_PASS = 60
FINAL_PASS = 65.0
NEW_HOT_DAYS = 90
PERIOD_FEATURE_LIMIT = 5
PERIOD_ORDER = ("daily", "weekly", "monthly")
PERIOD_LABELS = {"daily": "日榜", "weekly": "周榜", "monthly": "月榜"}

PERIOD_WEIGHTS = {"weekly": 50, "daily": 20, "monthly": 15}
RANK_WEIGHT = 10
CROSS_PERIOD_WEIGHT = 5
VALID_PERIODS = set(PERIOD_WEIGHTS)
VALID_SCOPES = {"global", "python", "typescript", "javascript", "jupyter-notebook", "go", "rust"}

COMMON_HARD_GATES = (
    "canonical_original",
    "readme_clear",
    "substantive_artifact",
    "readme_code_consistent",
    "run_path_documented",
    "not_spam_or_coursework",
    "install_scripts_reasonable",
    "dependencies_available",
)

QUALITY_LIMITS = {
    "readme_source_consistency": 20,
    "implementation_completeness": 20,
    "install_usage_clarity": 15,
    "tests_ci_release": 20,
    "docs_examples_errors": 10,
    "architecture_maintenance": 10,
    "dependency_transparency": 5,
}

VALUE_LIMITS = {
    "problem_value": 20,
    "practical_improvement": 20,
    "use_frequency": 15,
    "workflow_completeness": 15,
    "interoperability": 10,
    "extensibility": 10,
    "compounding_value": 5,
    "cost_benefit": 5,
}

VALUE_LEVELS = {"P0", "P1", "P2", "P3", "P4"}

CARD_FIELDS = {
    "one_line", "what", "audience", "usage", "features", "why",
    "strengths", "limitations", "value"
}

CARD_SCALAR_FIELDS = ("one_line", "what", "usage", "why", "value")
CARD_LIST_FIELDS = ("audience", "features", "strengths", "limitations")
CARD_FORBIDDEN_PHRASES = {
    "features": (
        "提供与项目主张相对应的开源内容和使用文档",
        "包含明确的依赖或构建清单",
        "包含可定位的入口或核心实现文件",
        "仓库包含测试或CI相关内容",
        "README与当前根目录代码树可相互定位",
        "存在可定位的入口、源码目录或核心实现",
        "仓库包含测试或持续集成相关证据",
    ),
    "strengths": (
        "当前进入GitHub Trending候选池",
        "README提供了较清楚的使用路径",
        "README提供安装、运行或使用路径",
        "存在测试或持续集成证据",
        "测试或CI证据可定位",
    ),
}
CARD_FORBIDDEN_PATTERNS = {
    "one_line": (
        r"是一个.+项目[，,:].*主要使用.+实现",
    ),
    "what": (
        r"项目围绕[“\"].+[”\"].*(?:提供|包含).*(?:实现|文档|工作流)",
    ),
    "audience": (
        r"^需要相关开源(?:方案|工具)的开发者$",
        r"^评估技术(?:选型与工作流|方案)的团队$",
    ),
    "usage": (
        r"^(?:按照|先阅读)\s*README",
    ),
    "why": (
        r"^项目出现在.+(?:Stars|星标).+[。.]?$",
    ),
    "limitations": (
        r"^本知识库只做静态核验",
    ),
    "value": (
        r"^属于(?:可持续使用的生产型系统|较完整的工具或工作流|可复用的基础设施或生态型能力)",
    ),
}
