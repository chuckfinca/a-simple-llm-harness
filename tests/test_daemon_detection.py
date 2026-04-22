"""Daemon-detection logic for the Docker sandbox.

Mocks subprocess so these tests run without Docker present.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from llm_harness import sandbox


def _completed(returncode: int, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=""
    )


class TestDaemonReachable:
    def test_reachable_when_docker_info_succeeds(self) -> None:
        with patch.object(
            sandbox.subprocess, "run", return_value=_completed(0, "27.3.1\n")
        ):
            assert sandbox._daemon_reachable() is True

    def test_unreachable_on_nonzero_exit(self) -> None:
        with patch.object(sandbox.subprocess, "run", return_value=_completed(1)):
            assert sandbox._daemon_reachable() is False

    def test_unreachable_on_empty_stdout(self) -> None:
        with patch.object(
            sandbox.subprocess, "run", return_value=_completed(0, "   \n")
        ):
            assert sandbox._daemon_reachable() is False

    def test_unreachable_on_timeout(self) -> None:
        with patch.object(
            sandbox.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=5),
        ):
            assert sandbox._daemon_reachable() is False

    def test_unreachable_when_docker_cli_missing(self) -> None:
        with patch.object(
            sandbox.subprocess, "run", side_effect=FileNotFoundError()
        ):
            assert sandbox._daemon_reachable() is False


class TestEnsureDockerDaemon:
    def test_no_op_when_already_reachable(self) -> None:
        with patch.object(sandbox, "_daemon_reachable", return_value=True):
            sandbox.ensure_docker_daemon()  # should not raise

    def test_raises_when_unreachable_and_no_macos_app(self) -> None:
        with (
            patch.object(sandbox, "_daemon_reachable", return_value=False),
            patch.object(sandbox, "_try_launch_docker_macos", return_value=False),
            pytest.raises(RuntimeError, match="not reachable"),
        ):
            sandbox.ensure_docker_daemon()

    def test_succeeds_after_launch_when_daemon_comes_up(self) -> None:
        # First poll: still down. Second poll: up.
        states = iter([False, False, True])
        with (
            patch.object(sandbox, "_daemon_reachable", side_effect=lambda: next(states)),
            patch.object(sandbox, "_try_launch_docker_macos", return_value=True),
            patch.object(sandbox.time, "sleep"),
        ):
            sandbox.ensure_docker_daemon()  # should not raise

    def test_raises_when_daemon_never_comes_up(self) -> None:
        with (
            patch.object(sandbox, "_daemon_reachable", return_value=False),
            patch.object(sandbox, "_try_launch_docker_macos", return_value=True),
            patch.object(sandbox.time, "sleep"),
            patch.object(
                sandbox.time,
                "monotonic",
                side_effect=[0.0, 0.0, sandbox.DAEMON_WAIT_SECONDS + 1],
            ),
            pytest.raises(RuntimeError, match="did not become reachable"),
        ):
            sandbox.ensure_docker_daemon()
