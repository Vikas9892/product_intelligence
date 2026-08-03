#!/usr/bin/env python3
"""Smoke-test runner for the Product Intelligence platform.

Answers one question: *is this deployment actually working?* -- not "are the
containers healthy", which Docker already reports, but whether a product can
be uploaded, processed by a real worker running real model inference, and then
found, deduplicated, recommended and priced.

Two constraints shape everything here.

Everything talks to the platform over its public HTTP API. Nothing touches
Redis, Qdrant, Docker or the filesystem, because the same runner has to verify
an AWS deployment later, where none of those internals are reachable.

Nothing outside the standard library is imported -- no httpx, no requests. The
suite must run from a fresh clone, a CI container, or a laptop with nothing
installed but Python. The one cost is hand-rolled multipart encoding in
client.py; the benefit is that "install dependencies first" is never a step
between an operator and finding out whether production is up.

Like backend/scripts/, this directory is a set of directly-executable scripts
rather than an importable package, so modules import each other flatly and
runner.py puts its own directory on sys.path.

    python scripts/smoke/runner.py --base-url http://localhost:8000
    python scripts/smoke/runner.py --base-url https://api.example.com --timeout 60

Exit codes:

    0  every check passed
    1  at least one check failed -- including a deployment that could not be
       reached, which is a deployment failure, not an inconclusive result
    2  the suite could not run at all (bad arguments, interrupted)

The distinction matters for CI: 1 is a verdict about the deployment, 2 means
the runner was misinvoked and never formed a verdict. Collapsing them would
let a typo in --base-url read as a broken deploy, or worse, the reverse.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# Running this file directly puts scripts/smoke on sys.path automatically, but
# not when it is invoked through a wrapper or a symlink from elsewhere. Adding
# it explicitly makes `python <anything>/runner.py` work from any directory --
# the same reasoning backend/scripts/run_workers.py already documents.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import assertions as a
import checks_catalog
import checks_health
import checks_pipeline
from client import SmokeClient, SmokeError
from context import SmokeContext

CheckFn = Callable[[SmokeContext], str]


@dataclass(frozen=True)
class Check:
    """One verifiable behavior.

    The function returns a short human-readable detail string describing what
    it observed -- shown next to PASS so a successful run is still informative
    ("recommendations: 4 returned, source excluded") rather than a wall of
    identical OK lines.
    """

    name: str
    fn: CheckFn


@dataclass(frozen=True)
class CheckGroup:
    """A related set of checks, run in order.

    `critical` groups abort the run when they fail. Health is critical:
    continuing past an unreachable API produces a page of cascading failures
    that hide the single real cause.
    """

    title: str
    checks: tuple[Check, ...]
    critical: bool = False


@dataclass
class Result:
    name: str
    group: str
    passed: bool
    detail: str
    duration_ms: float


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)
    aborted: bool = False

    @property
    def failures(self) -> list[Result]:
        return [r for r in self.results if not r.passed]

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)


# -- Output ----------------------------------------------------------------
# ANSI colour, disabled when stdout is not a TTY or NO_COLOR is set, so piping
# to a file or a CI log produces clean text rather than escape sequences.

_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _configure_stdout() -> None:
    """Make stdout tolerate non-ASCII.

    Windows consoles still default to a legacy code page (cp1252 here), which
    turns any non-ASCII character into a mojibake box or, worse, a
    UnicodeEncodeError that aborts the run. Product names in a demo catalog
    are operator-supplied and may contain anything, so the output stream is
    switched to UTF-8 with replacement rather than trusting the locale.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            # Suppressed: the stream may be redirected to something that
            # cannot be reconfigured. Output formatting is not worth failing a
            # deployment check over.
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


def _paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def _pass(text: str) -> str:
    return _paint(text, "32")


def _fail(text: str) -> str:
    return _paint(text, "31")


def _dim(text: str) -> str:
    return _paint(text, "2")


def _bold(text: str) -> str:
    return _paint(text, "1")


class Reporter:
    """Prints results as they happen.

    Streaming rather than buffering: the pipeline stage can take minutes on a
    cold deployment, and a runner that prints nothing until the end is
    indistinguishable from one that has hung.
    """

    def __init__(self, *, verbose: bool) -> None:
        self.verbose = verbose

    def group(self, title: str) -> None:
        print(f"\n{_bold(title)}")

    def result(self, result: Result) -> None:
        marker = _pass("[PASS]") if result.passed else _fail("[FAIL]")
        timing = _dim(f"({result.duration_ms:.0f}ms)")
        print(f"  {marker} {result.name:<34} {result.detail} {timing}")
        if not result.passed:
            # Indented under the failure so the reason travels with it, rather
            # than being collected at the end away from its context.
            for line in result.detail.splitlines():
                print(f"         {_dim(line)}")

    def note(self, message: str) -> None:
        if self.verbose:
            print(f"  {_dim('-> ' + message)}")


def run_groups(
    groups: list[CheckGroup], ctx: SmokeContext, reporter: Reporter
) -> Report:
    report = Report()

    for group in groups:
        reporter.group(group.title)
        group_failed = False

        for check in group.checks:
            started = time.monotonic()
            try:
                detail = check.fn(ctx)
                passed, message = True, detail
            except a.CheckFailure as exc:
                passed, message = False, str(exc)
            except SmokeError as exc:
                # Could not obtain an answer. Still a failure of this check,
                # but phrased so it is clear the deployment did not merely
                # answer wrongly -- it did not answer.
                passed, message = False, f"unreachable: {exc}"
            except LookupError as exc:
                # A check asked for state an earlier check should have
                # produced. Usually a knock-on from an earlier failure.
                passed, message = False, f"missing prerequisite: {exc}"

            result = Result(
                name=check.name,
                group=group.title,
                passed=passed,
                detail=message,
                duration_ms=(time.monotonic() - started) * 1000,
            )
            report.results.append(result)
            reporter.result(result)
            group_failed = group_failed or not passed

        if group_failed and group.critical:
            print(
                f"\n{_fail('Aborting:')} {group.title} failed. "
                f"Later checks depend on it and would only produce noise."
            )
            report.aborted = True
            break

    return report


def summarize(report: Report, elapsed: float) -> None:
    total = len(report.results)
    failed = len(report.failures)

    print()
    print("-" * 72)
    if failed == 0 and not report.aborted:
        print(f"{_pass('ALL CHECKS PASSED')}  {total} checks in {elapsed:.1f}s")
    else:
        print(
            f"{_fail('FAILED')}  {report.passed_count}/{total} passed in {elapsed:.1f}s"
        )
        print()
        print(_bold("Failures:"))
        for result in report.failures:
            print(f"  {_fail('x')} {result.group} / {result.name}")
            for line in result.detail.splitlines():
                print(f"      {line}")
    print("-" * 72)


def build_groups(ctx: SmokeContext, *, include: set[str]) -> list[CheckGroup]:
    """Assemble the suite.

    Stages are separable so a failing deployment can be re-probed cheaply --
    `--only health` re-runs connectivity in about a second instead of
    re-seeding a catalog and waiting on model inference.
    """
    groups: list[CheckGroup] = []

    if "health" in include:
        groups.append(
            CheckGroup(
                title="Connectivity & health",
                critical=True,
                checks=(
                    Check("API liveness", checks_health.check_liveness),
                    Check("API readiness", checks_health.check_readiness),
                    Check("Deployment version", checks_health.check_version),
                    Check("System health", checks_health.check_system_health),
                    Check("Required capabilities", checks_health.check_capabilities),
                    Check("Model registry", checks_health.check_models_registered),
                ),
            )
        )

    if "catalog" in include:
        groups.append(
            CheckGroup(
                title="Demo catalog",
                critical=True,
                checks=(
                    Check("Seed demo products", checks_catalog.check_seed_catalog),
                ),
            )
        )

    if "pipeline" in include:
        groups.append(
            CheckGroup(
                title="Async pipeline",
                critical=True,
                checks=(
                    Check(
                        "Jobs reach completion",
                        checks_pipeline.check_pipeline_completes,
                    ),
                    Check("Job records consistent", checks_pipeline.check_job_records),
                    Check("Dead-letter queue", checks_pipeline.check_no_dead_letters),
                    Check(
                        "Products searchable", checks_pipeline.check_products_searchable
                    ),
                ),
            )
        )

    return groups


#: Stage names accepted by --only, in execution order. Extended as later
#: milestones add stages.
ALL_STAGES = ("health", "catalog", "pipeline")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="smoke",
        description="Verify that a Product Intelligence deployment works end to end.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/smoke/runner.py --base-url http://localhost:8000\n"
            "  python scripts/smoke/runner.py --base-url https://api.example.com --timeout 60\n"
            "  python scripts/smoke/runner.py --only health\n"
        ),
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SMOKE_BASE_URL", "http://localhost:8000"),
        help="Origin of the deployment under test (default: %(default)s, or $SMOKE_BASE_URL).",
    )
    parser.add_argument(
        "--api-prefix",
        default=os.environ.get("SMOKE_API_PREFIX", "/api/v1"),
        help="API path prefix (default: %(default)s).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("SMOKE_TIMEOUT", "30")),
        help="Per-request HTTP timeout in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--pipeline-timeout",
        type=float,
        default=float(os.environ.get("SMOKE_PIPELINE_TIMEOUT", "600")),
        help=(
            "Seconds to wait for async processing of one product (default: %(default)s). "
            "The first upload on a cold deployment includes the model download."
        ),
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("SMOKE_API_KEY"),
        help="API key, when the deployment runs with the enterprise layer enabled.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS verification. For a deployment using a private certificate only.",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=ALL_STAGES,
        help="Run only the named stage(s). Repeatable. Default: all stages.",
    )
    parser.add_argument(
        "--force-reseed",
        action="store_true",
        help=(
            "Upload every demo product again instead of reusing what is already "
            "indexed. For throwaway environments; grows the catalog on each run."
        ),
    )
    parser.add_argument(
        "--list-catalog",
        action="store_true",
        help="Print the demo catalog and why each product exists, then exit.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print extra diagnostics."
    )
    return parser.parse_args(argv)


def print_catalog() -> None:
    """Describe the demo dataset without contacting any deployment."""
    from dataset import CATALOG

    print(_bold("Demo catalog") + f"  ({len(CATALOG)} products, all synthetic)")
    print()
    for product in CATALOG:
        print(f"  {_bold(product.key)}")
        print(
            f"    {product.name}  --  {product.brand} / {product.category} / {product.price}"
        )
        print(f"    {_dim(product.rationale)}")
        print(
            f"    {_dim(f'image: {len(product.image)} bytes, generated deterministically')}"
        )
        print()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _configure_stdout()

    if args.list_catalog:
        print_catalog()
        return 0

    if not args.base_url.startswith(("http://", "https://")):
        print(
            f"error: --base-url must start with http:// or https:// (got {args.base_url!r})",
            file=sys.stderr,
        )
        return 2

    client = SmokeClient(
        base_url=args.base_url,
        timeout=args.timeout,
        api_prefix=args.api_prefix,
        verify_tls=not args.insecure,
        api_key=args.api_key,
    )
    ctx = SmokeContext(
        client=client,
        pipeline_timeout=args.pipeline_timeout,
        verbose=args.verbose,
    )
    ctx.notes["force_reseed"] = args.force_reseed
    reporter = Reporter(verbose=args.verbose)

    print(_bold("Product Intelligence - deployment verification"))
    print(f"  target  {client.base_url}{client.api_prefix}")
    print(
        f"  timeout {args.timeout:.0f}s per request, {args.pipeline_timeout:.0f}s per pipeline job"
    )

    include = set(args.only) if args.only else set(ALL_STAGES)
    groups = build_groups(ctx, include=include)

    started = time.monotonic()
    report = run_groups(groups, ctx, reporter)
    summarize(report, time.monotonic() - started)

    return 1 if (report.failures or report.aborted) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(2)
