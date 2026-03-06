from __future__ import annotations

import json

from llm_harness.sandbox import MAX_OUTPUT_CHARS, run_python


class TestSandboxIsolation:
    def test_network_blocked(self) -> None:
        code = (
            "import urllib.request\n"
            "try:\n"
            "    urllib.request.urlopen('http://1.1.1.1', timeout=2)\n"
            "    print('CONNECTED')\n"
            "except Exception as e:\n"
            "    print('BLOCKED', type(e).__name__)\n"
        )
        result = json.loads(run_python(code))
        assert "BLOCKED" in result["stdout"]
        assert "CONNECTED" not in result["stdout"]

    def test_cannot_read_host_filesystem(self) -> None:
        code = (
            "import os\n"
            "try:\n"
            "    contents = os.listdir('/Users')\n"
            "    print('VISIBLE', contents)\n"
            "except Exception as e:\n"
            "    print('DENIED', type(e).__name__)\n"
        )
        result = json.loads(run_python(code))
        assert "DENIED" in result["stdout"] or result["stdout"].strip() == "VISIBLE []"

    def test_filesystem_is_read_only(self) -> None:
        code = (
            "try:\n"
            "    open('/home/sandbox/test.txt', 'w').write('hack')\n"
            "    print('WRITABLE')\n"
            "except Exception as e:\n"
            "    print('READ_ONLY', type(e).__name__)\n"
        )
        result = json.loads(run_python(code))
        assert "READ_ONLY" in result["stdout"]
        assert "WRITABLE" not in result["stdout"]


class TestTimeout:
    def test_infinite_loop_is_killed(self) -> None:
        code = "while True: pass"
        result = json.loads(run_python(code, timeout=3))
        assert result["timed_out"] is True
        assert result["exit_code"] == -1


class TestOutputTruncation:
    def test_large_output_is_truncated(self) -> None:
        code = f"print('x' * {MAX_OUTPUT_CHARS * 3})"
        result = json.loads(run_python(code))
        assert result["exit_code"] == 0
        assert "omitted" in result["stdout"]
        assert len(result["stdout"]) < MAX_OUTPUT_CHARS * 2
