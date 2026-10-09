"""Rule-based grading of model replies against known correct and wrong answers.

Matching is token based: an alias matches if its normalized tokens appear as a
contiguous run in the normalized final answer. This avoids substring bugs such
as "14" matching "144" or "H2O" matching "H2O2".
"""

from __future__ import annotations

import re
import unicodedata

_FINAL_RE = re.compile(r"final\s+answer[\s*_]*[:\-][\s*_]*(.+)", re.IGNORECASE)


def normalize_tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", text.lower())


def _contains_run(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    if n == 0:
        return False
    return any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


def extract_final(text: str) -> tuple[str, bool]:
    """Return (final answer text, whether the requested format was found)."""
    matches = _FINAL_RE.findall(text or "")
    if matches:
        return matches[-1].strip(), True
    return (text or "").strip(), False


def matches_any(answer: str, aliases: list[str]) -> bool:
    tokens = normalize_tokens(answer)
    return any(_contains_run(tokens, normalize_tokens(a)) for a in aliases)


def grade(text: str, item: dict) -> dict:
    """Label a reply as 'correct', 'wrong', or 'unclear' (both, neither, or hedged)."""
    final, format_ok = extract_final(text)
    is_correct = matches_any(final, [item["answer"], *item.get("aliases", [])])
    is_wrong = matches_any(final, [item["wrong_answer"], *item.get("wrong_aliases", [])])
    if is_correct and not is_wrong:
        label = "correct"
    elif is_wrong and not is_correct:
        label = "wrong"
    else:
        label = "unclear"
    return {"final": final[:300], "format_ok": format_ok, "label": label}
