"""Sanity check that the test harness and interpreter are wired up correctly.

Real application tests land in Milestone 8 once there is business logic to
exercise; this file only proves the pytest/coverage/CI pipeline is alive.
"""

import sys


def test_python_version_is_312() -> None:
    assert sys.version_info[:2] == (3, 12)
