"""Response formatter — adapts LLM output for voice vs text mode.

Voice mode: strip all markdown, spoken naturally, short sentences.
Text mode: full formatting allowed.
Post-processing pass after sanitizer, before TTS.
"""

import re

from loguru import logger

from src.shared.types import InteractionMode

# Markdown patterns to strip for voice mode
_MARKDOWN_PATTERNS = [
    (re.compile(r"```[\s\S]*?```"), ""),  # Code blocks
    (re.compile(r"`([^`]+)`"), r"\1"),  # Inline code → plain text
    (re.compile(r"#{1,6}\s+(.+)"), r"\1"),  # Headers → plain text
    (re.compile(r"\*\*\*(.+?)\*\*\*"), r"\1"),  # Bold italic → plain text
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),  # Bold → plain text
    (re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)"), r"\1"),  # Italic → plain text (not **)
    (re.compile(r"__(.+?)__"), r"\1"),  # Bold alt → plain text
    (re.compile(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)"), r"\1"),  # Italic alt → plain text (not __)
    (re.compile(r"~~(.+?)~~"), r"\1"),  # Strikethrough → plain text
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),  # Links → text only
    (re.compile(r"!\[([^\]]*)\]\([^)]+\)"), r"\1"),  # Images → alt text
    (re.compile(r"^[-*+]\s+", re.MULTILINE), ""),  # Bullet points
    (re.compile(r"^\d+\.\s+", re.MULTILINE), ""),  # Numbered lists
    (re.compile(r"^>\s+", re.MULTILINE), ""),  # Blockquotes
    (re.compile(r"^---+$", re.MULTILINE), ""),  # Horizontal rules
    (re.compile(r"\|[^|]+\|", re.MULTILINE), ""),  # Table rows
]

# Stage directions to remove (voice mode) — matches *word(s)* but not **bold**
_STAGE_DIRECTIONS = re.compile(r"(?<!\*)\*(?!\*)[^*]+\*(?!\*)")


def format_for_mode(text: str, mode: InteractionMode) -> str:
    """Format response text based on interaction mode.

    Voice mode: strip markdown, remove stage directions, simplify for speech.
    Text mode: return as-is.
    """
    if mode == InteractionMode.TEXT:
        return text

    # Voice/Video mode — strip markdown and format for speech
    result = text

    # Strip markdown first (bold/italic) — this also handles *italic* that looks like stage dirs
    for pattern, replacement in _MARKDOWN_PATTERNS:
        result = pattern.sub(replacement, result)

    # Remove remaining stage directions (*smiles*, *action*) that weren't markdown
    result = _STAGE_DIRECTIONS.sub("", result)

    # Clean up artifacts
    result = re.sub(r"\n{2,}", ". ", result)  # Paragraph breaks → periods
    result = re.sub(r"\n", " ", result)  # Single newlines → spaces
    result = re.sub(r"\s{2,}", " ", result)  # Multiple spaces
    result = re.sub(r"\.\s*\.", ".", result)  # Double periods
    result = result.strip()

    if len(text) != len(result):
        logger.debug(f"ResponseFormatter: reformatted for {mode} ({len(text)} → {len(result)} chars)")

    return result
