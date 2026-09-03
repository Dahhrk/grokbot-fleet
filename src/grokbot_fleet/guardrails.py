"""Pre-flight guardrails for every write that hits the job inbox."""

from __future__ import annotations

import re

_SECRET_RE = re.compile(
    r"(ghp_[A-Za-z0-9]{36}"
    r"|sk-[A-Za-z0-9]{32,}"
    r"|xoxb-"
    r"|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"
    r"|Bearer [A-Za-z0-9\-_.]{20,})",
)

_PUSH_MAIN_PHRASES = frozenset({
    "push to main",
    "push to master",
    "git push origin main",
    "git push origin master",
    "force push",
    "--force",
})


def _mentions_push_main(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _PUSH_MAIN_PHRASES)


def _mentions_destructive_prod(text: str) -> bool:
    lower = text.lower()
    return "drop " in lower and "production" in lower or "delete production" in lower


def _missing_fork_for_upstream(text: str) -> bool:
    lower = text.lower()
    return "upstream" in lower and "fork" not in lower


def _contains_secret(text: str) -> bool:
    return bool(_SECRET_RE.search(text))


_RAILS: list[tuple[str, str, callable]] = [
    (
        "no-push-main",
        "Blocked: never push directly to main/master.",
        lambda t: _mentions_push_main(t),
    ),
    (
        "no-destructive-prod",
        "Blocked: destructive production action detected.",
        lambda t: _mentions_destructive_prod(t),
    ),
    (
        "fork-before-upstream",
        "Blocked: fork to your account first, then PR to upstream.",
        lambda t: _missing_fork_for_upstream(t),
    ),
    (
        "no-secrets-in-prompt",
        "Blocked: description contains what looks like a secret or token.",
        lambda t: _contains_secret(t),
    ),
]


def run_guardrails(action: str, payload: dict) -> str | None:
    """Return a rejection message if any guardrail trips, else None."""
    text = str(payload)
    for rail_id, message, check in _RAILS:
        if check(text):
            return f"[{rail_id}] {message}"
    return None
