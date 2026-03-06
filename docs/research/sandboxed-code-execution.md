# Sandboxed Code Execution for LLM Agents: Research Findings

**Date:** 2026-03-06
**Context:** Evaluating approaches for giving an LLM model a sandboxed Python
coding environment, wired into our existing tool-use agent loop.

---

## 1. Using `uv` for Sandboxing

### What `uv` Actually Provides

`uv run --isolated` creates an **ephemeral virtual environment** populated by
`--with` requirements, bypassing project discovery. Combined with PEP 723
inline script metadata, uv can spin up a throwaway venv with declared
dependencies in seconds. This is dependency isolation, not security isolation.

### What `uv` Does NOT Provide

`uv` offers **zero security sandboxing**. Specifically:

- **No filesystem restrictions.** Code running in a uv environment has full
  read/write access to the host filesystem.
- **No network restrictions.** Outbound network access is unrestricted.
- **No process isolation.** The code runs as the same user with the same
  permissions as the parent process.
- **No resource limits.** No CPU, memory, or execution time constraints.
- **No syscall filtering.** No seccomp, no namespace isolation, nothing
  preventing `os.system("rm -rf /")`.

A `uv run --isolated` environment is functionally equivalent to running
`python -c "..."` in a fresh venv. It prevents dependency conflicts between
the agent's own dependencies and the LLM-generated code's dependencies, which
is useful but orthogonal to security.

### When `uv` IS Useful

For a development/research harness where the threat model is "prevent the LLM
from accidentally polluting my project's venv," `uv` is genuinely helpful:

- `uv run --isolated --with pandas,numpy script.py` gives the LLM access to
  data science packages without touching the harness venv.
- Dependencies are cached, so repeated runs are fast.
- The ephemeral environment is discarded after execution.

**Bottom line:** Use `uv` for dependency management within a sandbox, not as
the sandbox itself.

Sources:
- [uv Running Scripts docs](https://docs.astral.sh/uv/guides/scripts/)
- [uv Running Commands docs](https://docs.astral.sh/uv/concepts/projects/run/)
- [marimo sandboxed notebooks (uv-powered)](https://marimo.io/blog/sandboxed-notebooks)

---

## 2. Sandboxing Approaches: A Taxonomy

The field has converged on a clear hierarchy of isolation strength. From
weakest to strongest:

### Level 0: No Sandbox (exec/eval in-process)

Running `exec()` or `eval()` on LLM-generated code in the host process.
**Never do this in any context.** Python's introspection features make it
trivial to escape any in-process restriction. Even removing `__builtins__`
is bypassable via `().__class__.__bases__[0].__subclasses__()` chains.

### Level 1: AST-Based Interpreter (smolagents LocalPythonExecutor)

HuggingFace's smolagents re-implements a Python interpreter that walks the
AST node by node, enforcing:

- Import allowlists (must be explicitly authorized)
- Operation count caps (prevents infinite loops)
- Blocked access to dunder attributes that enable escapes

**Pros:** Zero infrastructure. Works anywhere. No Docker, no containers.
**Cons:** Fundamentally limited. A CVE (CVE-2025-5120) demonstrated sandbox
escape achieving RCE in smolagents v1.14.0. The smolagents docs themselves
warn: "no local python sandbox can ever be completely secure." Cannot run
code that uses native extensions (numpy C code, etc.) since it's an AST
interpreter, not a real Python runtime.

**Verdict:** Acceptable as a first layer for simple computations in low-risk
research contexts. Not a real sandbox.

Sources:
- [smolagents secure code execution docs](https://huggingface.co/docs/smolagents/en/tutorials/secure_code_execution)
- [CVE-2025-5120: smolagents sandbox escape](https://www.miggo.io/vulnerability-database/cve/CVE-2025-5120)

### Level 2: Subprocess with OS-Level Restrictions

Run LLM code in a separate Python subprocess with OS-enforced constraints:

- **seccomp-bpf** (Linux): Restrict allowed syscalls to a whitelist. The
  subprocess can only `read`, `write`, `exit`, `sigreturn` on pre-opened
  file descriptors.
- **setrlimit** (Linux/macOS): Cap CPU time (`RLIMIT_CPU`), virtual memory
  (`RLIMIT_AS`), and file write size (`RLIMIT_FSIZE`).
- **subprocess timeout**: `asyncio.wait_for(proc.communicate(...), timeout=N)`
  with `proc.kill()` on expiry.

The pattern from Simon Willison:

```python
proc = await asyncio.create_subprocess_exec(
    sys.executable, "-",
    stdout=asyncio.subprocess.PIPE,
    stdin=asyncio.subprocess.PIPE,
)
try:
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(code.encode()), timeout=time_limit
    )
except asyncio.TimeoutError:
    proc.kill()
    raise
```

**Pros:** Simple. No Docker dependency. Works on developer machines.
**Cons:** seccomp is Linux-only. setrlimit is partial on macOS. No filesystem
isolation without additional work. No network isolation. Andrew Healey's
analysis: "sandboxing untrusted code inside a separate process requires
OS-level protections rather than language-level filtering."

**Verdict:** Good for development/research. The "simplest thing that
provides real protection" on a single developer machine. Combine with a
tempdir and timeout for a practical minimum.

Sources:
- [Simon Willison: subprocess with time limit](https://til.simonwillison.net/python/subprocess-time-limit)
- [Andrew Healey: running untrusted Python code](https://healeycodes.com/running-untrusted-python-code)

### Level 3: Container Isolation (Docker/Podman)

Run code inside a Docker container with security constraints:

```
mem_limit="512m"
cpu_quota=50000
pids_limit=100
security_opt=["no-new-privileges"]
cap_drop=["ALL"]
network_mode="none"
```

This is the most common production pattern. Standard Linux containers use
kernel namespaces (PID, mount, network, user), cgroups for resource limits,
and seccomp-bpf for syscall filtering.

**Pros:** Well-understood. Broad ecosystem support. Works on macOS (via
Docker Desktop VM) and Linux. Filesystem, network, and resource isolation
out of the box. Many pre-built solutions exist.

**Cons:** Requires Docker installed. Container startup adds latency (though
typically only 1-3 seconds). On macOS, Docker runs a Linux VM, adding
overhead. Container management adds operational complexity.

**Verdict:** The industry standard. If Docker is acceptable infrastructure,
this is the go-to.

Sources:
- [dida.do: secure Python sandbox for LLM agents](https://dida.do/blog/setting-up-a-secure-python-sandbox-for-llm-agents)
- [Amir Malik: code sandboxes for LLMs](https://amirmalik.net/2025/03/07/code-sandboxes-for-llm-ai-agents)

### Level 3.5: Container + gVisor

Add gVisor as the container runtime. gVisor is a user-space kernel (written
in Go) that intercepts syscalls before they reach the host kernel. Standard
containers share the host kernel; gVisor provides its own implementation of
the Linux API.

Integration is a single Docker daemon config change:

```json
{
  "runtimes": {
    "runsc": {
      "path": "/usr/local/bin/runsc"
    }
  }
}
```

Then: `docker run --runtime=runsc ...`

**Pros:** Significantly stronger isolation than standard containers. No
hardware virtualization required. Minimal config change.
**Cons:** Linux-only (gVisor requires Linux). Some syscall compatibility
gaps. Performance overhead for syscall-heavy workloads.

Amir Malik's assessment: "I think it's a perfect middle ground for running
untrusted code. Integrating it only requires a simple Docker daemon
configuration change."

Sources:
- [gVisor project](https://github.com/google/gvisor)
- [Amir Malik: code sandboxes for LLMs](https://amirmalik.net/2025/03/07/code-sandboxes-for-llm-ai-agents)

### Level 3.5 (alt): nsjail

Google's nsjail combines Linux namespaces, cgroups, and seccomp-bpf into a
single tool purpose-built for sandboxing. Lighter than full containers.

**Pros:** Very fine-grained control. No Docker dependency. Used in Google's
production systems.
**Cons:** Linux-only. More complex configuration than Docker. Less ecosystem
support.

Source:
- [nsjail on GitHub](https://github.com/google/nsjail)

### Level 4: MicroVM Isolation (Firecracker)

Firecracker (the technology behind AWS Lambda and E2B) launches full microVMs
with hardware-level isolation. Startup in ~125ms. Each sandbox gets its own
kernel.

**Pros:** Strongest isolation. Hardware-level security boundary.
**Cons:** Requires KVM (Linux only, bare metal or nested virt). Not practical
for local development on macOS. Operationally complex to self-host.

Source:
- [Firecracker on GitHub](https://github.com/firecracker-microvm/firecracker)

### Level 5: WebAssembly (WASM)

Run Python compiled to WASM (via Pyodide or VMware's python.wasm). The WASM
runtime enforces memory safety, capability-based filesystem access, and
instruction-count limits ("fuel").

**Pros:** Truly portable. Works everywhere. Strong theoretical isolation.
**Cons:** No native extension support (no numpy C code, no pandas C
extensions). Limited stdlib. Slow for compute-heavy work. Pyodide is
improving but still has gaps. Cohere's Terrarium uses this approach and
reports it works well for basic computations.

Sources:
- [Simon Willison: Python in a WASM sandbox](https://til.simonwillison.net/webassembly/python-in-a-wasm-sandbox)
- [Cohere Terrarium](https://github.com/cohere-ai/cohere-terrarium)

---

## 3. What Leading Projects Do

### Claude Code (Anthropic)

Uses OS-level primitives directly, no containers:

- **macOS:** `sandbox-exec` with dynamically generated Seatbelt profiles
- **Linux:** Bubblewrap + seccomp-bpf filters

Two isolation boundaries enforced:
1. **Filesystem:** Read/write allowed in cwd only. Writes blocked outside.
2. **Network:** All traffic routed through a Unix domain socket proxy that
   enforces domain allowlists.

Anthropic open-sourced this as `sandbox-runtime` (srt): a CLI tool that wraps
any command with filesystem and network restrictions at the OS level, without
containers. Usage: `srt "python script.py"`.

Key finding: sandboxing reduced permission prompts by 84% in Anthropic's
internal usage, meaning the agent can operate more autonomously within
defined boundaries.

Sources:
- [Anthropic engineering: Claude Code sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing)
- [sandbox-runtime on GitHub](https://github.com/anthropic-experimental/sandbox-runtime)
- [Claude Code sandboxing docs](https://code.claude.com/docs/en/sandboxing)

### Anthropic Code Execution Tool (API)

Anthropic offers a server-side code execution tool in the API itself. You
pass `{"type": "code_execution_20250825", "name": "code_execution"}` as a
tool, and Claude can run Bash/Python in Anthropic's sandboxed containers.

- Free when used with web_search or web_fetch tools
- Supports Python and Bash (as of the 20250825 version)
- Not eligible for Zero Data Retention

This is the zero-infrastructure option: Anthropic handles sandboxing entirely.
The tradeoff is that code runs on Anthropic's servers, not locally.

Source:
- [Anthropic code execution tool docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool)

### smolagents (HuggingFace)

Supports five execution backends:
1. **LocalPythonExecutor** -- AST-based interpreter (default, weakest)
2. **E2B** -- Cloud Firecracker microVMs
3. **Modal** -- Cloud containers with sub-second starts
4. **Docker** -- Local container isolation
5. **Blaxel** -- Cloud VMs with <25ms hibernation wake
6. **WASM** -- Pyodide + Deno WebAssembly sandbox

Configuration is a single parameter: `executor_type="docker"` (or "e2b",
"modal", "blaxel", "wasm").

Two architectural patterns:
- **Snippet sandboxing:** Only LLM-generated code runs in sandbox. Simpler.
  Does not support multi-agent.
- **Full system sandboxing:** Entire agent runs in sandbox. Supports
  multi-agent but requires passing API keys into sandbox.

Source:
- [smolagents secure code execution](https://huggingface.co/docs/smolagents/en/tutorials/secure_code_execution)

### Open Interpreter

Supports Docker and E2B as sandbox backends. Important caveat: E2B only
sandboxes Python; shell and JavaScript still execute locally. Docker
sandboxing is labeled "experimental."

Source:
- [Open Interpreter isolation docs](https://docs.openinterpreter.com/safety/isolation)

### Aider

Aider does NOT sandbox code execution. It is a code editing tool, not a code
execution tool. It writes code to files and uses git for safety (rollback via
git reset). There is no execute-and-return-output loop.

### Cohere Terrarium

Python compiled to WASM (Pyodide) running inside a Node.js process, deployed
as a Docker container on GCP Cloud Run. State is completely recycled after
every invocation. Includes numpy, pandas, matplotlib, scikit-learn.

Performance: 500-900ms for matplotlib chart generation. Cost: under $30/month
during internal use.

Source:
- [Cohere Terrarium on GitHub](https://github.com/cohere-ai/cohere-terrarium)

---

## 4. The "Code Execution as a Tool" Pattern

### Tool Interface Design

The consensus pattern across all projects surveyed:

**Input:** A string of code (Python source).
**Output:** JSON containing stdout, stderr, exit code, and optionally
generated files (base64-encoded).

Typical tool schema:

```json
{
  "name": "run_python",
  "description": "Execute Python code in a sandboxed environment. Returns stdout, stderr, and exit code.",
  "parameters": {
    "type": "object",
    "properties": {
      "code": {
        "type": "string",
        "description": "Python source code to execute"
      }
    },
    "required": ["code"]
  }
}
```

Typical result format:

```json
{
  "stdout": "Hello, world!\n",
  "stderr": "",
  "exit_code": 0,
  "timed_out": false
}
```

### Timeouts

Every implementation surveyed uses timeouts:
- Anthropic API code execution: not publicly documented but clearly enforced
- The strongdm/attractor agent loop spec: 10 seconds default, configurable
  up to 10 minutes
- Cohere Terrarium: configurable per-request
- Simon Willison's pattern: explicit `asyncio.wait_for` with `proc.kill()`

**Recommendation:** 30 seconds default for research use. 10 seconds is too
short for data processing; 5 minutes is too generous for runaway loops.

### Output Truncation

The strongdm/attractor spec documents the best practice:

1. **Full output goes to the host application** (logs, UI, event stream).
2. **Truncated output goes to the LLM** to avoid context window bloat.
3. Two-stage truncation: character-based first (handles single-line dumps),
   then line-based (head + tail with "... truncated ..." marker).
4. A visible warning marker indicates truncation occurred, so the model knows
   it's seeing partial output.

**Recommendation:** Cap LLM-visible output at ~4000 characters. Keep full
output in a log. Insert a truncation notice that tells the model how many
characters/lines were omitted.

### Resource Limits

At minimum:
- **Timeout:** Kill after N seconds
- **Memory:** Cap virtual memory (setrlimit or container mem_limit)
- **CPU:** Cap CPU time or quota
- **Disk:** Write to a tmpdir with size limits, cleaned after execution
- **Network:** Block or restrict (especially important for preventing
  data exfiltration or accidental API calls)
- **Process count:** Limit forking (pids_limit in Docker, RLIMIT_NPROC)

### Wiring Into the Agent Loop

Based on the existing `tools.py` pattern, a code execution tool would be:

1. A new entry in `TOOL_DEFINITIONS` with the schema above.
2. A new `_run_python(code: str) -> str` function that:
   - Writes code to a temp file
   - Executes it in a subprocess with timeout
   - Captures stdout/stderr
   - Truncates output
   - Returns JSON result
3. A new case in `execute_tool()` dispatching to `_run_python`.

No changes to `agent.py` are needed. The agent loop already handles
arbitrary tools.

### Stateless vs. Stateful Execution

Two patterns exist:
- **Stateless:** Each code execution starts fresh. Simpler, safer, no state
  leakage between calls. Used by Terrarium, Code Sandbox MCP.
- **Stateful (REPL):** Execution environment persists across calls. Variables
  and imports carry over. Used by llm-sandbox's InteractiveSandboxSession,
  Jupyter-based approaches.

For a research harness, **start stateless**. It is simpler and avoids a
category of bugs around stale state. If the LLM needs to build on previous
results, it can include all necessary setup in each code block.

---

## 5. Practical Recommendation

### Context

This is a development/research harness, not public-facing. The threat model
is:
- Protecting against accidental damage from LLM-generated code (infinite
  loops, disk fills, accidental file deletion)
- NOT protecting against a determined adversary crafting escape exploits

### Recommended Approach: Tiered, Starting Simple

#### Tier 1 (Implement Now): Subprocess + Timeout + Tempdir

The simplest approach that provides real protection:

1. Write LLM-generated code to a temp file in a fresh tmpdir.
2. Execute via `subprocess.run()` (or async equivalent) with:
   - `timeout=30` seconds
   - `cwd` set to the tmpdir (so file operations are contained)
   - `capture_output=True`
3. Return stdout/stderr/exit_code as JSON.
4. Clean up the tmpdir after execution.
5. Truncate output before returning to the LLM.

Optional improvements (still no Docker):
- Use `uv run --isolated --with <packages>` as the execution command
  instead of bare `sys.executable`. This gives the LLM access to data
  science packages without polluting the harness venv.
- On Linux, add `setrlimit` for memory and CPU caps.
- On macOS, the subprocess timeout is your main protection.

**This fits naturally into the existing `tools.py` pattern.** It is a single
function, no new dependencies, no infrastructure.

#### Tier 2 (When Needed): Docker Container

When the harness is used for tasks where code touches sensitive data or
makes network calls:

1. Use the `llm-sandbox` library (`pip install llm-sandbox`). It wraps
   Docker/Podman with a clean Python API:
   ```python
   with SandboxSession(lang="python") as session:
       result = session.run(code, libraries=["pandas", "numpy"])
   ```
2. Configure: `mem_limit="512m"`, `network_mode="none"`, `cap_drop=["ALL"]`.
3. Consider gVisor as the runtime for stronger isolation.

**The llm-sandbox library is the best off-the-shelf option** for a simple
harness. It supports Docker/Podman/Kubernetes, handles container lifecycle,
captures stdout/stderr/exit_code, and supports artifact extraction
(matplotlib plots as base64).

#### Tier 3 (If Cloud Is Acceptable): Anthropic's Code Execution Tool

If the harness uses Anthropic models via the API, the simplest possible
approach is to use Anthropic's built-in code execution tool:

```python
tools=[{"type": "code_execution_20250825", "name": "code_execution"}]
```

Zero infrastructure. Anthropic handles all sandboxing. The tradeoff: code
runs on Anthropic's servers, not locally. Not eligible for Zero Data
Retention. And since the harness uses litellm, this may require
Anthropic-specific API calls rather than the generic completion interface.

#### Tier 3 (Alt): E2B or Modal

Cloud-hosted sandboxes with simple Python SDKs:
- **E2B:** Firecracker microVMs, ~200ms cold start, $0.000028/CPU/s.
  Free tier includes $100 credit.
- **Modal:** Sub-second starts, $0.0000131/CPU/s, $30 free credits/month.

Both have clean Python SDKs. E2B is more popular in the agent ecosystem;
Modal has better autoscaling.

### What NOT to Do

1. **Do not use `exec()` or `eval()` on LLM-generated code.** The existing
   calculator tool already uses `eval()` with restricted builtins, which is
   fine for math expressions but would be dangerous for arbitrary code.
2. **Do not rely on AST-based interpreters alone** (smolagents'
   LocalPythonExecutor pattern). They have been repeatedly bypassed.
3. **Do not assume `uv --isolated` provides security.** It provides
   dependency isolation only.
4. **Do not give the sandbox network access** unless specifically needed.
   An LLM with network access can exfiltrate data, make API calls, or
   download malicious packages.

---

## 6. Summary Comparison Table

| Approach | Isolation | Setup Cost | macOS | Linux | Latency | Deps |
|---|---|---|---|---|---|---|
| subprocess + timeout | Minimal | None | Yes | Yes | ~100ms | None |
| subprocess + setrlimit + seccomp | Moderate | Low | Partial | Yes | ~100ms | None |
| Anthropic sandbox-runtime (srt) | Good | Low | Yes | Yes | ~100ms | srt CLI |
| Docker container | Strong | Medium | Yes* | Yes | 1-3s | Docker |
| Docker + gVisor | Very strong | Medium | No | Yes | 1-3s | Docker + gVisor |
| nsjail | Strong | Medium | No | Yes | ~100ms | nsjail |
| Anthropic code execution API | Full | None | Yes | Yes | ~1-2s | API key |
| E2B (cloud) | Full | None | Yes | Yes | ~200ms | API key |
| Modal (cloud) | Full | None | Yes | Yes | <1s | API key |
| WASM (Pyodide) | Strong | Low | Yes | Yes | 500-900ms | wasmtime |

*Docker on macOS runs via a Linux VM, which adds overhead but works.

---

## 7. Open Questions

1. **State management across calls.** If the LLM generates code that
   produces a DataFrame, and then wants to filter it in a subsequent call,
   stateless execution forces regenerating the data each time. Is this
   acceptable, or will we need REPL-style state? Jupyter-based approaches
   solve this but add complexity.

2. **Package availability.** If the LLM needs numpy/pandas/scipy, these must
   be available in the sandbox. With subprocess+uv, `uv run --with pandas`
   handles this. With Docker, the image must include them. With WASM, many
   packages are unavailable.

3. **File I/O.** If the LLM generates a plot or writes a CSV, how does that
   get back to the user? llm-sandbox handles this with artifact extraction.
   A subprocess approach would need explicit file reading after execution.

4. **Anthropic's sandbox-runtime (srt) viability.** This is the exact tool
   Anthropic built for Claude Code. It provides filesystem + network
   isolation without Docker. However, it's a TypeScript/Node CLI, not a
   Python library, and it's labeled "experimental research preview." Worth
   monitoring but not ready to build on.

5. **litellm compatibility with Anthropic's code execution tool.** The
   harness uses litellm for model abstraction. Anthropic's server-side
   code execution tool uses a provider-specific tool type
   (`code_execution_20250825`), which may not be supported through litellm's
   generic interface.

---

## 8. Decision

Implement **Docker container isolation** as a new `run_python` tool in
`tools.py`. Docker is already available on the dev machine, and the
implementation complexity is nearly identical to subprocess — just a different
`subprocess.run()` command. This gives us real filesystem, network, and
resource isolation from day one.

Approach:
- Build a small base image with Python + common packages (pandas, numpy, etc.)
- Tool writes code to a tempfile, bind-mounts it into the container
- Container runs with `--cap-drop=ALL --network=none --memory=512m`
- `subprocess.run()` with timeout wraps the `docker run` invocation
- Returns `{stdout, stderr, exit_code, timed_out}` JSON
- Start stateless (fresh container per call)
- Truncate output before returning to the LLM

The tool interface is backend-agnostic, so swapping to gVisor, E2B, or any
other backend later requires no changes to the agent loop or tool schema.
