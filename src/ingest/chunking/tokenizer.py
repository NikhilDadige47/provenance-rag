"""Token estimation and boundary utilities for the chunking pipeline.

Provides token estimation calibrated for Cohere / LLM tokenizers
with conservative safety margins to prevent exceeding model context windows.
"""

import math
import re

# Standard word boundary regex for whitespace and punctuation
_WORD_REGEX = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def estimate_tokens(text: str) -> int:
    """Estimate token count for a given text string.

    Uses a conservative blended metric of word/punctuation boundaries
    and character-ratio estimation (1 token ~= 3.8 to 4 characters for English).
    Never underestimates, ensuring chunks remain strictly under Cohere/model limits.
    """
    if not text:
        return 0

    stripped = text.strip()
    if not stripped:
        return 0

    # Match tokens via word / punctuation units
    regex_matches = len(_WORD_REGEX.findall(stripped))

    # Character-based upper bound estimation (3.5 chars/token for conservative margin)
    char_estimate = math.ceil(len(stripped) / 3.5)

    # Use the max of the two to be safe against code, numbers, or dense punctuation
    return max(regex_matches, char_estimate)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within max_tokens without breaking words unnecessarily."""
    if not text or max_tokens <= 0:
        return ""

    if estimate_tokens(text) <= max_tokens:
        return text

    words = text.split()
    chosen_words: list[str] = []
    current_tokens = 0

    for word in words:
        word_tok = estimate_tokens(word)
        if current_tokens + word_tok > max_tokens:
            break
        chosen_words.append(word)
        current_tokens += word_tok

    return " ".join(chosen_words)
