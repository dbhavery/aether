"""False wake-up context evaluator.

After wake word fires, listen for 3 seconds of context.
Only activate if the speech is addressed to Aether.
If the user says 'Aether' in conversation with someone else, stay silent.
"""

import re

from loguru import logger

CONTEXT_LISTEN_SECONDS = 3.0

# Phrases that indicate The user is talking TO Aether
ACTIVATION_PHRASES = [
    "you",
    "can you",
    "please",
    "hey",
    "what",
    "how",
    "tell me",
    "i need",
    "help",
    "do you",
    "are you",
    "could you",
    "would you",
    "will you",
]

# Phrases that indicate The user is talking ABOUT Aether to someone else
THIRD_PARTY_INDICATORS = [
    "she",
    "her",
    # "it" removed: too common a pronoun, blocks valid commands like "fix it", "look it up"
    "the app",
    "that thing",
    "the assistant",
    "my assistant",
    "this ai",
]


def evaluate_wake_context(transcript: str) -> bool:
    """Return True if Aether should activate, False if this was a false wake-up.

    Called after wake word detected, with the transcript of what followed.
    """
    transcript_lower = transcript.lower().strip()

    # Empty or very short -> likely false wake-up
    if len(transcript_lower) < 5:
        logger.debug("WakeContext: too short, likely false wake-up")
        return False

    # Activation phrases FIRST — if The user starts with a direct address, always activate
    for phrase in ACTIVATION_PHRASES:
        if transcript_lower.startswith(phrase):
            logger.info(f"WakeContext: activation phrase '{phrase}' — activating")
            return True

    # Third-party indicators — only reject if no activation phrase matched
    for indicator in THIRD_PARTY_INDICATORS:
        # Use word boundary matching to avoid false positives ("her" matching "here")
        if re.search(rf"\b{re.escape(indicator)}\b", transcript_lower):
            logger.info(f"WakeContext: third-party indicator '{indicator}' — staying silent")
            return False

    # Default: activate (better to respond than miss a real command)
    return True
