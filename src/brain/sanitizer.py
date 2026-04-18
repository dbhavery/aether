"""Response sanitizer — strips banned phrases from all LLM output.

Two-pass: sentence-level stripping first, then line-level cleanup.
Runs on EVERY LLM response before sending to user.
"""

import re

from loguru import logger

# === BANNED PHRASES ===
# These are phrases that make Aether sound like a corporate assistant.
# Two categories: exact matches (full sentence removal) and substring patterns.

# Full sentences containing these → remove entire sentence
_SENTENCE_BANS = [
    # Service questions
    "how can i help",
    "how can i assist",
    "how may i help",
    "how may i assist",
    "is there anything else",
    "anything else i can",
    "anything else you need",
    "anything else you'd like",
    "what can i do for you",
    "what else can i",
    "what would you like me to",
    "want me to check",
    "want me to look",
    "would you like me to",
    "shall i help",
    "shall i assist",
    "do you need anything",
    "do you need help",
    "do you want me to",
    "need anything else",
    "let me know if you need",
    "let me know if there's anything",
    "let me know how i can",
    "feel free to ask",
    "feel free to reach out",
    "don't hesitate to ask",
    "don't hesitate to reach out",
    "i'm here to help",
    "i'm here for you",
    "i'm always here",
    "i'm happy to help",
    "happy to assist",
    "happy to help",
    "glad to help",
    "glad to assist",
    "glad i could help",
    "hope that helps",
    "hope this helps",
    "hope i was helpful",
    "at your service",
    "what's on your mind",
    "what brings you here",
    "how are you doing today",
    # Compliment starters
    "great question",
    "that's a great question",
    "that's a really good question",
    "that's an excellent question",
    "that's a wonderful question",
    "interesting question",
    "that's a really interesting",
    "good thinking",
    "great thinking",
    "excellent point",
    "that's a great point",
    # Over-eager openings
    "absolutely",
    "of course",
    "certainly",
    "sure thing",
    "no problem at all",
    # Formal closings
    "best regards",
    "warm regards",
    "kind regards",
    "sincerely",
    "yours truly",
]

# Line-level: if line starts with or contains these → remove entire line
_LINE_BANS = [
    re.compile(r"^\s*(?:is there anything else|anything else)\s*[?!.]?\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:let me know if|feel free to|don't hesitate)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:i'm here to help|i'm happy to|happy to help)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:hope (?:that|this|i) help)", re.IGNORECASE),
    re.compile(r"^\s*(?:what can i do for you|how can i help)\s*[?!.]?\s*$", re.IGNORECASE),
]

# Set of banned phrases for exact-match lookup (after sentence normalization).
# Substring matching was too aggressive: "How can I assist you today?" would be
# stripped because it contained the banned fragment "how can i assist", even
# though the full sentence is a perfectly normal response. We now strip a
# sentence only when its substantive content equals a banned phrase verbatim
# (case-insensitive, with surrounding whitespace and trailing punctuation
# removed). Tone shaping for longer responses belongs in the system prompt.
_SENTENCE_BAN_SET: frozenset[str] = frozenset(_SENTENCE_BANS)
_TRAILING_SENTENCE_PUNCT = "?!.,;:"


def _normalize_sentence(sentence: str) -> str:
    """Lowercase, trim whitespace, strip trailing punctuation."""
    return sentence.lower().strip().rstrip(_TRAILING_SENTENCE_PUNCT).strip()


def sanitize_response(text: str) -> str:
    """Remove banned phrases from LLM response.

    Pass 1: Sentence-level — remove a sentence only if its substantive content
            (lowercased, trimmed, trailing punctuation removed) equals a banned
            phrase verbatim. This preserves multi-sentence responses where a
            banned fragment merely appears as part of a longer sentence.
    Pass 2: Line-level — remove entire lines matching line ban patterns.
    Pass 3: Clean up artifacts (double spaces, orphan punctuation, blank lines).
    """
    if not text or not text.strip():
        return text

    original_len = len(text)

    # Pass 1: Sentence-level stripping
    # Split into sentences (preserving newlines for structure)
    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        # Split line into sentences
        sentences = re.split(r"(?<=[.!?])\s+", line)
        kept_sentences = []
        for sentence in sentences:
            normalized = _normalize_sentence(sentence)
            if normalized and normalized in _SENTENCE_BAN_SET:
                continue
            kept_sentences.append(sentence)

        cleaned_lines.append(" ".join(kept_sentences))

    text = "\n".join(cleaned_lines)

    # Pass 2: Line-level cleanup
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        is_banned = False
        for pattern in _LINE_BANS:
            if pattern.search(line):
                is_banned = True
                break
        if not is_banned:
            cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # Pass 3: Cleanup artifacts
    text = re.sub(r" {2,}", " ", text)  # Double spaces
    text = re.sub(r"\n{3,}", "\n\n", text)  # Triple+ newlines
    text = text.strip()

    # Log if we stripped anything
    stripped = original_len - len(text)
    if stripped > 0:
        logger.debug(f"Sanitizer: stripped {stripped} chars from response")

    return text
