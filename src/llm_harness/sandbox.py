from __future__ import annotations

import json
import subprocess
import tempfile
import uuid
from pathlib import Path

IMAGE_NAME = "llm-harness-sandbox"
TIMEOUT_SECONDS = 30
MAX_OUTPUT_CHARS = 4000
CONTAINER_PREFIX = "lh-sandbox-"
DOCKERFILE_DIR = Path(__file__).resolve().parent.parent.parent / "sandbox"

_image_ready = False


def ensure_sandbox_image() -> None:
    global _image_ready  # noqa: PLW0603
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
    command: list[str],
    *,
    timeout: int = TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    container_name = f"{CONTAINER_PREFIX}{uuid.uuid4().hex[:12]}"
    volume_args = []
    for src, dest in volumes:
        volume_args += ["-v", f"{src}:{dest}:ro"]

    try:
        return subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                f"--name={container_name}",
                "--cap-drop=ALL",
                "--network=none",
                "--memory=512m",
                "--pids-limit=100",
                "--read-only",
                "--tmpfs=/tmp:size=64m",
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


def run_python(code: str, *, timeout: int = TIMEOUT_SECONDS) -> str:
    ensure_sandbox_image()
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "script.py"
        script_path.write_text(code)

        try:
            result = _docker_run(
                volumes=[(str(script_path), "/home/sandbox/script.py")],
                command=["python", "/home/sandbox/script.py"],
                timeout=timeout,
            )
            return json.dumps(
                {
                    "stdout": _truncate(result.stdout),
                    "stderr": _truncate(result.stderr),
                    "exit_code": result.returncode,
                    "timed_out": False,
                }
            )
        except subprocess.TimeoutExpired:
            return json.dumps(
                {
                    "stdout": "",
                    "stderr": "Execution timed out.",
                    "exit_code": -1,
                    "timed_out": True,
                }
            )


def run_file_tool(fn: str, args: dict, workspace: Path) -> str:
    ensure_sandbox_image()
    files_module = Path(__file__).parent / "files.py"
    command_json = json.dumps({"fn": fn, **args})

    try:
        result = _docker_run(
            volumes=[
                (str(files_module), "/home/sandbox/files.py"),
                (str(workspace), "/workspace"),
            ],
            command=["python", "/home/sandbox/files.py", command_json],
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return json.dumps({"error": _truncate(result.stderr)})
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "File operation timed out."})


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    half = MAX_OUTPUT_CHARS // 2
    omitted = len(text) - MAX_OUTPUT_CHARS
    return (
        text[:half] + f"\n\n... ({omitted} characters omitted) ...\n\n" + text[-half:]
    )
