"""Assertions for the smoke suite.

Every assertion raises `CheckFailure` carrying enough context to diagnose the
problem from the output alone. That matters more here than in unit tests: a
smoke run may be the only evidence available about a deployment nobody can
attach a debugger to. "Expected 200, got 502" is not actionable; "GET
https://api.example.com/health returned HTTP 502, body: <html>..." is.

These are plain functions rather than `assert` statements on purpose --
`python -O` strips `assert`, which would silently turn the whole suite into a
no-op that reports success.
"""

from __future__ import annotations

from typing import Any

from client import Response


class CheckFailure(AssertionError):
    """A check ran and its expectation did not hold.

    Distinct from `SmokeError`, which means no answer could be obtained at all.
    """


def fail(message: str) -> None:
    """Fail unconditionally. For branches a check has decided are invalid."""
    raise CheckFailure(message)


def require(condition: bool, message: str) -> None:
    """Fail with `message` unless `condition` holds."""
    if not condition:
        raise CheckFailure(message)


# -- HTTP ------------------------------------------------------------------


def status_is(response: Response, expected: int) -> None:
    if response.status != expected:
        raise CheckFailure(
            f"{response.method} {response.url} returned HTTP {response.status}, "
            f"expected {expected}. Body: {_snippet(response)}"
        )


def status_in(response: Response, expected: tuple[int, ...]) -> None:
    """Accept any of several statuses.

    Used where more than one response is legitimately correct -- for example a
    disabled optional feature may be either 404 (routes never registered) or
    403 (registered but gated), and both are correct behavior.
    """
    if response.status not in expected:
        allowed = ", ".join(str(s) for s in expected)
        raise CheckFailure(
            f"{response.method} {response.url} returned HTTP {response.status}, "
            f"expected one of {allowed}. Body: {_snippet(response)}"
        )


def has_header(response: Response, name: str) -> str:
    value = response.header(name)
    if value is None:
        present = ", ".join(sorted(response.headers)) or "<none>"
        raise CheckFailure(
            f"{response.method} {response.url} is missing the {name!r} header. Present: {present}"
        )
    return value


# -- JSON shape -------------------------------------------------------------


def is_object(payload: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CheckFailure(
            f"{context}: expected a JSON object, got {type(payload).__name__}"
        )
    return payload


def is_list(payload: Any, *, context: str) -> list[Any]:
    if not isinstance(payload, list):
        raise CheckFailure(
            f"{context}: expected a JSON array, got {type(payload).__name__}"
        )
    return payload


def has_keys(payload: dict[str, Any], keys: tuple[str, ...], *, context: str) -> None:
    """Require every key in `keys`.

    Presence only -- values may legitimately be null. Several responses use
    null to mean a real state (a disabled cross-encoder returns
    `cross_encoder_score: null`), so requiring non-null would fail on correct
    behavior.
    """
    missing = [k for k in keys if k not in payload]
    if missing:
        raise CheckFailure(
            f"{context}: missing key(s) {', '.join(missing)}. Present: {', '.join(sorted(payload)) or '<none>'}"
        )


def get_path(payload: Any, path: str, *, context: str) -> Any:
    """Read a dotted path, failing with the exact segment that was missing.

    A bare KeyError deep inside a nested response says nothing about where in
    the structure the problem was.
    """
    current = payload
    walked: list[str] = []
    for segment in path.split("."):
        if not isinstance(current, dict):
            location = ".".join(walked) or "<root>"
            raise CheckFailure(
                f"{context}: expected an object at {location} while reading {path!r}, "
                f"got {type(current).__name__}"
            )
        if segment not in current:
            raise CheckFailure(
                f"{context}: {path!r} is missing at segment {segment!r}. "
                f"Available there: {', '.join(sorted(current)) or '<none>'}"
            )
        current = current[segment]
        walked.append(segment)
    return current


# -- Numeric ----------------------------------------------------------------


def in_range(
    value: Any, low: float, high: float, *, context: str, inclusive: bool = True
) -> float:
    """Require a numeric value within bounds.

    `bool` is excluded explicitly because `isinstance(True, int)` is true in
    Python, and a boolean where a score belongs is a real defect that would
    otherwise slip through as "0 <= True <= 1".
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CheckFailure(
            f"{context}: expected a number, got {value!r} ({type(value).__name__})"
        )
    numeric = float(value)
    ok = low <= numeric <= high if inclusive else low < numeric < high
    if not ok:
        bounds = f"[{low}, {high}]" if inclusive else f"({low}, {high})"
        raise CheckFailure(f"{context}: {numeric} is outside {bounds}")
    return numeric


def at_least(value: Any, minimum: float, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CheckFailure(
            f"{context}: expected a number, got {value!r} ({type(value).__name__})"
        )
    if float(value) < minimum:
        raise CheckFailure(
            f"{context}: {value} is below the required minimum of {minimum}"
        )
    return float(value)


def ranks_above(
    ordered_ids: list[str], expected_first: str, expected_after: str, *, context: str
) -> None:
    """Require one item to rank ahead of another in a result list.

    This is the shape most AI assertions take. Comparing *relative order*
    rather than absolute scores keeps the suite meaningful without pinning it
    to float values that legitimately drift when a model or weight changes --
    and without reimplementing the backend's scoring to predict them.
    """
    if expected_first not in ordered_ids:
        raise CheckFailure(
            f"{context}: expected {expected_first} to appear in the results, but it is absent. "
            f"Ranking was: {ordered_ids or '<empty>'}"
        )
    if expected_after not in ordered_ids:
        # Not a failure: the weaker match being absent entirely is a stronger
        # result than it merely ranking lower, which is what was being asserted.
        return
    first = ordered_ids.index(expected_first)
    after = ordered_ids.index(expected_after)
    if first >= after:
        raise CheckFailure(
            f"{context}: expected {expected_first} to rank above {expected_after}, "
            f"but they placed {first + 1} and {after + 1}. Ranking was: {ordered_ids}"
        )


# -- Error envelope ---------------------------------------------------------


def is_error_envelope(
    response: Response, *, expected_code: str | None = None
) -> dict[str, Any]:
    """Require the platform's standard error shape.

    Every handled error returns `{"success": false, "error": {"code",
    "message", "details"}}`. The frontend depends on that shape, so a
    deployment that returns a bare string or a raw framework error is broken
    for clients even when the status code looks right.
    """
    context = f"{response.method} {response.url} error body"
    payload = is_object(response.json(), context=context)
    has_keys(payload, ("success", "error"), context=context)
    require(
        payload["success"] is False,
        f"{context}: expected success=false, got {payload['success']!r}",
    )

    error = is_object(payload["error"], context=f"{context}.error")
    has_keys(error, ("code", "message", "details"), context=f"{context}.error")

    if expected_code is not None and error["code"] != expected_code:
        raise CheckFailure(
            f"{context}: expected error code {expected_code!r}, got {error['code']!r} "
            f"(message: {error['message']!r})"
        )
    return error


def _snippet(response: Response, limit: int = 300) -> str:
    text = response.text.strip()
    if not text:
        return "<empty>"
    return text[:limit] + ("..." if len(text) > limit else "")
