from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from llm_harness.types import SandboxResult

IMAGE_NAME = "llm-harness-sandbox"
TIMEOUT_SECONDS = 30
CONTAINER_PREFIX = "lh-sandbox-"
# Bundled inside the package (not a sibling of the repo root) so the
# Docker build context ships with every install — a consumer installing
# `llm_harness` as a regular dependency (atelier's `path = "../harness"`)
# only gets what's under src/llm_harness/; a path climbing out to the
# repo root worked only when running from the harness repo's own
# checkout and silently broke for every other consumer.
DOCKERFILE_DIR = Path(__file__).resolve().parent / "docker"

DAEMON_WAIT_SECONDS = 90
DAEMON_POLL_INTERVAL = 2
MACOS_DOCKER_APP = Path("/Applications/Docker.app")

# Avoid re-checking/rebuilding the Docker image on every tool call
_image_ready = False


def _daemon_reachable() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def _try_launch_docker_macos() -> bool:
    """Best-effort start of Docker Desktop on macOS. False if unavailable."""
    if sys.platform != "darwin" or not MACOS_DOCKER_APP.exists():
        return False
    print(f"Docker daemon not reachable; launching {MACOS_DOCKER_APP.name}...")
    subprocess.run(["open", "-a", "Docker"], check=False, timeout=10)
    return True


def ensure_docker_daemon() -> None:
    """Block until the Docker daemon answers, launching Docker Desktop on
    macOS if needed. Raises RuntimeError on any other platform / runtime
    where we can't auto-launch and the daemon is down."""
    if _daemon_reachable():
        return
    if not _try_launch_docker_macos():
        raise RuntimeError(
            "Docker daemon is not reachable. Start Docker Desktop, Colima, "
            "OrbStack, or whichever runtime you use, then retry."
        )
    deadline = time.monotonic() + DAEMON_WAIT_SECONDS
    while time.monotonic() < deadline:
        if _daemon_reachable():
            return
        time.sleep(DAEMON_POLL_INTERVAL)
    raise RuntimeError(
        f"Docker daemon did not become reachable within {DAEMON_WAIT_SECONDS}s "
        f"after launching Docker Desktop."
    )


def ensure_sandbox_image() -> None:
    global _image_ready
    if _image_ready:
        return

    ensure_docker_daemon()

    result = subprocess.run(
        ["docker", "images", "-q", IMAGE_NAME],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.stdout.strip():
        _image_ready = True
        return

    print(f"Building sandbox image ({IMAGE_NAME})...")
    subprocess.run(
        ["docker", "build", "-t", IMAGE_NAME, str(DOCKERFILE_DIR)],
        check=True,
        timeout=300,
    )
    _image_ready = True


def _docker_run(
    volumes: list[tuple[str, str]],
    writable_volumes: list[tuple[str, str]],
    command: list[str],
    *,
    timeout: int = TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    container_name = f"{CONTAINER_PREFIX}{uuid.uuid4().hex[:12]}"
    volume_args = []
    for src, dest in volumes:
        volume_args += ["-v", f"{src}:{dest}:ro"]
    for src, dest in writable_volumes:
        volume_args += ["-v", f"{src}:{dest}"]

    try:
        return subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                f"--name={container_name}",
                # Minimal attack surface: no capabilities, no network, read-only fs
                "--cap-drop=ALL",
                "--network=none",
                "--read-only",
                "--tmpfs=/tmp:size=64m",
                "--memory=512m",
                "--pids-limit=100",
                *volume_args,
                IMAGE_NAME,
                *command,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        subprocess.run(
            ["docker", "kill", container_name],
            capture_output=True,
            timeout=5,
        )
        raise


def run_python(
    code: str,
    *,
    workspace: Path | None = None,
    scratch_dir: Path | None = None,
    timeout: int = TIMEOUT_SECONDS,
) -> SandboxResult:
    ensure_sandbox_image()

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "script.py"
        script_path.write_text(code)

        volumes: list[tuple[str, str]] = [
            (str(script_path), "/home/sandbox/script.py"),
        ]
        if workspace is not None:
            volumes.append((str(workspace), "/workspace"))

        writable_volumes: list[tuple[str, str]] = []
        if scratch_dir is not None:
            writable_volumes.append((str(scratch_dir), "/scratchpad"))

        try:
            result = _docker_run(
                volumes=volumes,
                writable_volumes=writable_volumes,
                command=["python", "/home/sandbox/script.py"],
                timeout=timeout,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": "Execution timed out.",
                "exit_code": -1,
                "timed_out": True,
            }
