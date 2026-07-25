"""Hierarchical Categorizer — auto-classifies facts and turns into categories.

Top-level: personal, work, social, technical
Sub-categories: personal.preferences, personal.health, personal.goals, etc.

Uses keyword matching for speed, with LLM fallback for ambiguous content.
"""

import re

from loguru import logger

from src.shared.config import get_yaml_config

# Hierarchical category definitions
CATEGORIES = {
    "personal.preferences": [
        "prefer",
        "favorite",
        "like",
        "love",
        "hate",
        "dislike",
        "rather",
        "instead",
        "always use",
        "dark mode",
        "light mode",
        "color",
        "theme",
        "font",
        "style",
        "aesthetic",
    ],
    "personal.health": [
        "allergy",
        "allergic",
        "medication",
        "medicine",
        "doctor",
        "health",
        "sick",
        "injury",
        "exercise",
        "workout",
        "sleep",
        "diet",
        "weight",
        "pain",
        "headache",
        "tired",
        "energy",
    ],
    "personal.goals": [
        "goal",
        "plan to",
        "want to",
        "going to",
        "aim",
        "target",
        "resolution",
        "ambition",
        "dream",
        "aspire",
        "milestone",
    ],
    "personal.routine": [
        "every day",
        "every morning",
        "every night",
        "routine",
        "habit",
        "schedule",
        "usually",
        "typically",
        "always do",
        "wake up",
        "go to bed",
        "commute",
    ],
    "social.friends": [
        "friend",
        "buddy",
        "pal",
        "hang out",
        "meet up",
        "get together",
        "party",
        "social",
        "invited",
    ],
    "social.family": [
        "mom",
        "dad",
        "mother",
        "father",
        "sister",
        "brother",
        "parent",
        "wife",
        "husband",
        "kid",
        "child",
        "family",
        "aunt",
        "uncle",
        "cousin",
        "grandma",
        "grandpa",
    ],
    "work.projects": [
        "project",
        "codebase",
        "repo",
        "feature",
        "sprint",
        "deploy",
        "release",
        "build",
        "architecture",
        "design",
        "implementation",
        "refactor",
        "module",
    ],
    "work.meetings": [
        "meeting",
        "standup",
        "sync",
        "call with",
        "interview",
        "presentation",
        "demo",
        "review",
    ],
    "work.tasks": [
        "task",
        "todo",
        "deadline",
        "due date",
        "priority",
        "assigned",
        "complete",
        "finish",
        "done",
    ],
    "technical.code": [
        "function",
        "class",
        "method",
        "variable",
        "import",
        "python",
        "javascript",
        "typescript",
        "kotlin",
        "rust",
        "bug",
        "error",
        "exception",
        "debug",
        "fix",
    ],
    "technical.tools": [
        "vscode",
        "git",
        "docker",
        "ollama",
        "chromadb",
        "pip",
        "npm",
        "gradle",
        "terminal",
        "shell",
        "api",
        "sdk",
        "library",
        "framework",
        "package",
    ],
    "technical.infrastructure": [
        "server",
        "database",
        "network",
        "port",
        "firewall",
        "dns",
        "ssl",
        "certificate",
        "deploy",
        "ci/cd",
        "monitoring",
        "logging",
        "backup",
        "storage",
    ],
}

# Compiled patterns for fast matching
_CATEGORY_PATTERNS: dict[str, list[re.Pattern]] = {}
for cat, keywords in CATEGORIES.items():
    _CATEGORY_PATTERNS[cat] = [re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in keywords]

# LLM classification prompt
_CLASSIFY_PROMPT = """Classify this text into exactly ONE category. Reply with ONLY the category name, nothing else.

Categories:
- personal.preferences (likes, dislikes, settings)
- personal.health (medical, fitness, sleep)
- personal.goals (ambitions, plans)
- personal.routine (daily habits, schedules)
- social.friends (friendships, social events)
- social.family (family members, family events)
- work.projects (code, repos, features)
- work.meetings (calls, presentations)
- work.tasks (todos, deadlines)
- technical.code (programming, bugs)
- technical.tools (software, dev tools)
- technical.infrastructure (servers, networking)
- general (if none of the above fit)

Text: {text}

Category:"""


def classify_fast(text: str) -> str:
    """Fast keyword-based classification. Returns best matching category or 'general'."""
    text_lower = text.lower()
    scores: dict[str, int] = {}

    for category, patterns in _CATEGORY_PATTERNS.items():
        count = sum(1 for p in patterns if p.search(text_lower))
        if count > 0:
            scores[category] = count

    if not scores:
        return "general"

    # Return category with most keyword matches
    return max(scores, key=lambda k: scores[k])


async def classify_with_llm(text: str) -> str:
    """LLM-based classification using qwen3:8b. Fallback for ambiguous content."""
    try:
        from src.brain.clients import call_ollama

        yaml_config = get_yaml_config()
        model = yaml_config.get("llm", {}).get("fast_model", "qwen3:8b")
        prompt = _CLASSIFY_PROMPT.format(text=text[:500])
        response = await call_ollama(prompt=prompt, model=model)
        # Strip <think> tags from thinking models (qwen3)
        import re as _re

        cleaned = _re.sub(r"<think>[\s\S]*?</think>\s*", "", response).strip()
        category = cleaned.lower().split("\n")[0].strip()

        # Validate response is a known category
        valid_categories = set(CATEGORIES.keys()) | {"general"}
        if category in valid_categories:
            return category

        # Try partial match
        for valid in valid_categories:
            if valid in category:
                return valid

        logger.debug(f"Categorizer: LLM returned unknown category '{category}', defaulting to 'general'")
        return "general"
    except Exception as e:
        logger.warning(f"Categorizer: LLM classification failed: {e}")
        return "general"


async def classify(text: str, use_llm_fallback: bool = True) -> str:
    """Classify text into hierarchical category.

    First tries fast keyword matching. Falls back to LLM if no strong match.
    """
    fast_result = classify_fast(text)

    if fast_result != "general":
        return fast_result

    if use_llm_fallback:
        return await classify_with_llm(text)

    return "general"
