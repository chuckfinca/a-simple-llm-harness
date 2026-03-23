from __future__ import annotations

import subprocess
import tempfile
import uuid
from pathlib import Path

from llm_harness.types import SandboxResult

IMAGE_NAME = "llm-harness-sandbox"
TIMEOUT_SECONDS = 30
CONTAINER_PREFIX = "lh-sandbox-"
DOCKERFILE_DIR = Path(__file__).resolve().parent.parent.parent / "sandbox"

# Avoid re-checking/rebuilding the Docker image on every tool call
_image_ready = False


def ensure_sandbox_image() -> None:
    global _image_ready
    if _image_ready:
        return

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
