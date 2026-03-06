# CLI Output Display Research

Research into best practices for displaying LLM agent loop output in a
developer-facing CLI chat interface. Conducted 2026-03-06.

---

## 1. What Leading CLI Tools Do

### Claude Code

Claude Code uses a React/Ink-based TUI (TypeScript, not Python) with
the richest display of any CLI agent tool surveyed.

**Tool call display:** Each tool invocation appears as a color-coded badge
with the tool name -- Read (blue), Write (green), Edit (amber), Bash (red).
The badge is followed by the primary argument (file path, command, etc.).
Tool input and output are collapsible -- collapsed by default, expandable
with a keypress. This keeps the conversation scannable while allowing
drill-down.

**Metadata:** Model name is shown at startup. Token usage and cost are
available via `/cost` command or in the status line, not inline per-turn
by default. A community feature request (issue #10593) asked for real-time
token usage inline, indicating this is something developers want but even
Claude Code does not show by default.

**Streaming:** Responses stream token-by-token. Markdown is rendered inline
with syntax highlighting. Extended thinking blocks are collapsed behind
Ctrl+O.

**Key takeaway:** Claude Code leans toward *minimal inline metadata* with
*on-demand detail*. The tool call badges are the main innovation -- they
provide glanceable information about what the agent is doing without
overwhelming the conversation.

Source: [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference),
[Claude Code Guide](https://github.com/Cranot/claude-code-guide),
[Token Usage Feature Request](https://github.com/anthropics/claude-code/issues/10593)

### Aider

Aider is a Python CLI tool using `prompt_toolkit` for input and `rich` for
output rendering.

**Color system:** Configurable colors for different output channels:
- User input: blue (default)
- Assistant output: blue, rendered as Markdown via `rich.Markdown`
- Tool output: unstyled by default (configurable)
- Tool errors: red
- Tool warnings: orange (#FFA500)

**Tool call display:** Aider does not have general tool calls in the
agent-loop sense. Its primary "tool" output is file diffs, which are
shown inline with syntax highlighting. The diff is the central artifact.

**Metadata:** Token usage is available via the `/tokens` slash command.
Cost per token is configured in model settings (`input_cost_per_token`,
`output_cost_per_token`). At startup, aider prints model info, git repo
status, and repo-map token count.

**Streaming:** Enabled by default, streams Markdown to terminal
incrementally.

**Key takeaway:** Aider proves that `rich` + `prompt_toolkit` is a
battle-tested combination for Python CLI chat tools. Its approach is
simple: stream Markdown for the response, use color to separate
channels, and put metadata behind slash commands.

Source: [Aider Usage](https://aider.chat/docs/usage.html),
[Aider Options](https://aider.chat/docs/config/options.html),
[Aider source: io.py](https://github.com/Aider-AI/aider/blob/main/aider/io.py)

### Simon Willison's `llm` CLI

A Python CLI tool focused on simplicity.

**Tool call display:** Uses a `--td` / `--tools-debug` flag that reveals
tool calls in a plain-text format:
```
Tool call: llm_version({})
  0.26a0
```
Without the flag, tool calls are invisible to the user -- only the final
response is shown. This is a clean opt-in verbosity model.

**Metadata:** Minimal by default. The tool focuses on piping output to
other commands, so it avoids adding noise.

**Streaming:** Streams by default for interactive use.

**Key takeaway:** The `--tools-debug` pattern is elegant for a dev tool.
Silent by default, fully transparent when you ask. The display format is
dead simple: `Tool call: name(args)` followed by indented result.

Source: [LLM Tools Documentation](https://llm.datasette.io/en/stable/tools.html),
[LLM 0.26 announcement](https://simonwillison.net/2025/May/27/llm-tools/)

### Open Interpreter

Python CLI using Rich for markdown rendering with a component-based
display system.

**Tool call display:** Shows generated code in a syntax-highlighted
CodeBlock *before* execution. User gets a confirmation prompt (unless
`auto_run=True`). Then console output streams below. Clear visual
separation between "here is the code" and "here is the result."

**Output management:** Truncates long outputs to `max_output` (default
2800 chars) to prevent terminal flooding. This is a critical UX decision
-- unbounded tool output destroys readability.

**Streaming:** Uses generators to yield response chunks for progressive
display. Tracks "active line" during code execution.

**Key takeaway:** The pre-execution / post-execution visual separation
is a strong pattern for code execution tools. Output truncation with a
sensible default is essential.

Source: [Open Interpreter DeepWiki](https://deepwiki.com/OpenInterpreter/open-interpreter),
[Open Interpreter Usage](https://docs.openinterpreter.com/guides/basic-usage)

### OpenAI Codex CLI

TypeScript TUI (Ink/React, like Claude Code).

**Tool call display:** Shows each background terminal's command plus up
to three recent non-empty output lines. Syntax-highlights fenced code
blocks and file diffs. Surfaces a transcript of actions for review.

**Streaming:** Streams responses to terminal. Non-interactive mode
(`codex exec`) streams to stdout or JSONL.

**Output management:** Truncates tool output to 256 lines or 10KB,
showing first 128 lines + last 128 lines when exceeded.

**Key takeaway:** The "first N + last N" truncation pattern is widely
used (Codex, your existing `sandbox.py` already does this with
characters). The 3-line preview of running commands is a nice touch for
long-running operations.

Source: [Codex CLI Features](https://developers.openai.com/codex/cli/features/),
[Codex CLI](https://github.com/openai/codex)

### ShellGPT (sgpt)

Python CLI, simpler than the above.

**Output:** Streams Markdown by default, with `--no-markdown` to disable.
Color-coded output. Minimal metadata display.

**Key takeaway:** Even the simplest tools default to Markdown rendering
and streaming. These are table stakes.

Source: [ShellGPT](https://github.com/TheR1D/shell_gpt)

---

## 2. Terminal Formatting Approaches

### Recommendation: `rich` library

Every Python CLI tool surveyed that has good output uses `rich` (by
Textualize). It is the clear standard for Python terminal formatting.

**Why `rich` is the right choice for this harness:**

1. **Drop-in migration.** `console.print()` has the same signature as
   `print()`. You can migrate incrementally -- replace `print()` calls
   one at a time.

2. **Inline markup.** BBCode-style: `[bold cyan]text[/bold cyan]`,
   `[dim]text[/dim]`, `[red]error[/red]`. No need to manage ANSI codes.

3. **Markdown rendering.** `rich.Markdown(text)` renders headings, code
   blocks with syntax highlighting, lists, etc. Critical for LLM output.

4. **Panel.** `rich.Panel(content, title="Tool: run_python")` draws a
   bordered box around content. Great for visually separating tool calls
   from the conversation flow.

5. **Rule.** `console.rule("tool call")` draws a horizontal line with a
   label. Lighter-weight alternative to Panel for section separators.

6. **Status/Spinner.** `console.status("Calling model...")` shows an
   animated spinner during LLM calls. Simple context manager API.

7. **Live display.** `rich.Live` enables updating text in-place, useful
   for streaming token display without scrolling.

8. **Graceful degradation.** Automatically disables styling in dumb
   terminals or when `NO_COLOR` is set.

**What NOT to use:**

- **Textual** (also by Textualize): Full TUI framework, massive overkill
  for a REPL. Designed for complex multi-panel applications.
- **prompt_toolkit**: Excellent for input (history, autocomplete, vi/emacs
  keybindings) but not needed for output formatting. Consider it later if
  you want better input handling, but `input()` is fine for now.
- **Raw ANSI codes**: Fragile, hard to read, no reason to use them when
  `rich` exists.
- **click.style/click.echo**: Less capable than `rich`, and you are not
  using click for argument parsing.

**Dependency cost:** `rich` has zero required dependencies (it vendors
`pygments` and `markdown-it-py`). Adding it to `pyproject.toml` is a
single line.

Source: [Rich GitHub](https://github.com/Textualize/rich),
[Rich Documentation](https://rich.readthedocs.io/en/stable/introduction.html),
[Rich Panel Docs](https://rich.readthedocs.io/en/stable/panel.html),
[Rich Live Docs](https://rich.readthedocs.io/en/stable/live.html)

---

## 3. What Metadata to Show Inline vs. Hide

Based on patterns across all surveyed tools, here is the recommended
metadata visibility strategy for a developer audience.

### Always visible (every turn)

| Metadata | Why | Format |
|---|---|---|
| Model name | Developers switch models constantly; must always know which is active | Show once at startup and in prompt prefix |
| Tool calls (name + key arg) | Core visibility into what the agent is doing | Inline, styled distinctly from conversation |
| Tool results (truncated) | Developers need to verify tool behavior | Inline, truncated with char/line limit |
| Errors | Must never be hidden | Red, prominent |

### Shown per-turn in a compact footer

| Metadata | Why | Format |
|---|---|---|
| Latency | Developers care about speed during iteration | `1.2s` after the response |
| Token count (in/out) | Directly affects cost and context window budget | `245 in / 89 out` |
| Cost (if available) | Budget awareness | `$0.003` |

### Behind a flag or slash command

| Metadata | Why | Format |
|---|---|---|
| Full tool call arguments | Usually too verbose for inline display | `--verbose` or `/debug` |
| Full tool results (untruncated) | Can be hundreds of lines | Logged to file always, expandable in verbose mode |
| Provider API base URL | Rarely needed | `/status` command |
| Cache hit status | Useful for cost debugging, not routine | `/status` or verbose mode |
| Cumulative session cost/tokens | Useful but not per-turn | `/cost` or `/tokens` slash command |

### The key principle

**Show what the agent is doing (tool calls) always. Show how much it
cost (tokens/latency) in a compact footer. Hide the rest behind a
flag.** This matches the pattern across Claude Code, aider, and llm.

---

## 4. Tool Call Display Patterns

### Recommended pattern: labeled, indented, truncated

Based on the survey, here is the recommended display pattern, adapted
for a Python CLI using `rich`:

**During execution (while the model is thinking or tools are running):**
```
assistant> [spinner] Thinking...
```

**Tool call with short result:**
```
  [tool] run_python("print(2+2)")
  [result] {"stdout": "4\n", "exit_code": 0}
```

**Tool call with long result (truncated):**
```
  [tool] run_python("import pandas as pd; ...")
  [result] {"stdout": "   col_a  col_b\n0      1      2\n1   ...
            (truncated, 2847 chars total)
```

**Final assistant response:**
```
assistant> The result of 2+2 is 4.
           [1.2s | 245 in, 89 out | $0.003]
```

### Implementation with `rich`

The tool call display should use:

- **Dim text** (`[dim]`) for the `[tool]` and `[result]` labels -- they
  are metadata, not the main conversation
- **Indentation** (2-4 spaces) to visually nest tool calls under the
  assistant turn
- **Color** for the tool name (e.g., cyan for `run_python`, yellow for
  `calculator`) to make it scannable
- **Truncation** at a sensible default (e.g., 200 chars for inline
  display, full output in the JSONL log)
- **Dim compact footer** for the per-turn metadata line

### Alternative: Panel-based display

```
+----- tool: run_python ---------------+
| code: print(2+2)                     |
+--------------------------------------+
| stdout: 4                            |
| exit_code: 0                         |
+--------------------------------------+
```

Using `rich.Panel` with `box=box.ROUNDED` or `box=box.SIMPLE`. This is
visually cleaner but takes more vertical space. Best reserved for verbose
mode or when there are few tool calls per turn.

### What NOT to do

- **Do not print full tool arguments inline.** A `run_python` call with
  a 50-line code block will destroy readability. Show a truncated
  preview (first line + `...`) or just the tool name.
- **Do not print full tool results inline.** Same problem. Truncate to
  ~200 chars or ~10 lines, with the full content in the log file.
- **Do not use collapsible/expandable UI.** This requires a TUI
  framework (Textual, Ink). Stick with static printed output for
  simplicity.

---

## 5. Streaming Considerations

### Should you stream token-by-token?

**Yes, but it is not the highest priority for this harness.**

The case for streaming:
- LLM responses take 2-15 seconds. Without streaming, the user stares
  at nothing. Streaming shows the first token in ~500ms.
- Every major CLI tool streams by default (aider, llm, sgpt, Claude
  Code, Codex).
- Perceived latency improvement is 10-20x for longer responses.

The case for deferring streaming:
- The current harness uses `litellm.completion()` (non-streaming). To
  stream, you switch to `litellm.completion(..., stream=True)` and
  iterate over chunks.
- Streaming complicates the agent loop: you must accumulate the full
  response to detect tool calls (they arrive as deltas across chunks).
- Streaming + `rich.Markdown` rendering is tricky: you cannot render
  Markdown incrementally without re-rendering the whole block (which
  is what `rich.Live` enables, but adds complexity).
- For a dev tool where the primary output is often tool calls (not long
  prose), the benefit is smaller than for a chatbot.

### Practical recommendation

**Phase 1 (now):** Keep buffered output. Add a `console.status()` spinner
during the LLM call so the user knows something is happening. This is
trivial to implement and eliminates the "staring at nothing" problem.

**Phase 2 (later):** Add streaming. Use `litellm.completion(stream=True)`,
accumulate chunks, and print each text delta with `console.print(delta,
end="")`. Do NOT try to render Markdown incrementally -- just stream
raw text. After the full response is assembled, optionally re-render as
Markdown.

**Phase 3 (if needed):** Use `rich.Live` for true incremental Markdown
rendering during streaming. This is what aider does and it looks great,
but it is significantly more complex.

---

## 6. Practical Recommendation

### The simplest approach that looks good

Given this is a simple Python CLI harness for developer use with
`litellm` as the only dependency:

**Step 1: Add `rich` as a dependency.**

One line in `pyproject.toml`: add `"rich>=14"` to dependencies.

**Step 2: Create a `display.py` module.**

A single module with a `Console` instance and a few functions:

- `print_header(model: str)` -- prints the startup banner with model name
- `print_user_prompt()` -- prints `you>` in a distinct color
- `print_tool_call(name: str, arguments: str)` -- prints the tool name
  and truncated arguments in dim/indented style
- `print_tool_result(result: str)` -- prints the truncated result in
  dim/indented style
- `print_assistant_response(content: str)` -- renders the response as
  Markdown
- `print_turn_footer(latency_s: float, prompt_tokens: int,
  completion_tokens: int, cost: float | None)` -- prints the compact
  metadata line
- `print_error(message: str)` -- prints errors in red

**Step 3: Modify `agent.py` to emit display events.**

The `run_agent_loop` function currently returns only the final string.
Instead, it should accept a callback or yield events so the caller can
display tool calls and results as they happen. The simplest approach:
pass display functions into the loop, or have the loop yield
`ToolCall`, `ToolResult`, and `Response` events.

**Step 4: Add a spinner during LLM calls.**

Wrap the `completion()` call in `with console.status("Thinking...")`.
This is one line of code and immediately improves the UX.

**Step 5: Extract metadata from litellm responses.**

The telemetry logger already extracts `prompt_tokens`,
`completion_tokens`, `latency_s`, and `cost` from the litellm response.
Surface the same data to the display layer. You can either have the
agent loop return this metadata alongside the response, or extract it
in `__main__.py` from the same response object.

### What the output would look like

```
llm-harness (gemini/gemini-2.5-flash)
Type 'quit' to exit.

you> What is 2+2?

  [tool] calculator("2 + 2")
  [result] {"result": 4}

assistant>
The answer is **4**.
                                      1.2s | 145 in, 32 out | $0.001

you> Run a Python script that prints hello world

  [tool] run_python("print('hello world')")
  [result] {"stdout": "hello world\n", "exit_code": 0}

assistant>
The script ran successfully and printed "hello world".
                                      3.4s | 312 in, 45 out | $0.002

you> quit
```

### What this does NOT include (intentionally)

- **Streaming:** Deferred to Phase 2. The spinner covers the waiting UX.
- **Slash commands:** (`/cost`, `/tokens`, `/debug`). Nice to have, but
  adds input parsing complexity. Defer until needed.
- **Prompt_toolkit:** Better input handling (history, multi-line, etc.)
  is a separate concern from output display.
- **Collapsible sections:** Requires a TUI framework. Not worth it.
- **Markdown rendering of tool results:** Tool results are JSON; render
  them as plain text. Only the assistant's natural language response
  benefits from Markdown rendering.

### Migration path

The migration from current code to rich output is incremental:

1. Replace `print(f"llm-harness ({model})")` with
   `console.print(f"[bold]llm-harness[/bold] [dim]({model})[/dim]")`
2. Replace `print(f"\nassistant> {reply}\n")` with
   `console.print(Markdown(reply))` + footer
3. Add `print_tool_call` / `print_tool_result` calls in the agent loop
4. Wrap `completion()` in `console.status()`
5. Extract metadata from the response object for the footer

Each step is independently deployable and testable. No big-bang rewrite.

---

## Summary of Patterns Across Tools

| Tool | Language | Output Lib | Tool Call Display | Metadata Display | Streaming |
|---|---|---|---|---|---|
| Claude Code | TS | Ink (React) | Color-coded badges, collapsible | `/cost` command, status line | Yes |
| Aider | Python | rich + prompt_toolkit | File diffs inline | `/tokens` command, startup info | Yes |
| llm (Willison) | Python | rich (optional) | `--td` flag: `Tool call: name(args)` | Minimal | Yes |
| Open Interpreter | Python | rich | CodeBlock + MessageBlock | Minimal | Yes |
| Codex CLI | TS | Ink (React) | 3-line preview, syntax highlighting | Transcript | Yes |
| sgpt | Python | Markdown rendering | N/A (no tool calls) | Minimal | Yes |
| **Recommended** | **Python** | **rich** | **Dim indented label + truncated args/result** | **Compact per-turn footer** | **Phase 2** |

---

## Sources

- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference)
- [Claude Code Guide (GitHub)](https://github.com/Cranot/claude-code-guide)
- [Claude Code Token Usage Feature Request](https://github.com/anthropics/claude-code/issues/10593)
- [Aider Usage](https://aider.chat/docs/usage.html)
- [Aider Options](https://aider.chat/docs/config/options.html)
- [Aider io.py Source](https://github.com/Aider-AI/aider/blob/main/aider/io.py)
- [LLM Tools Documentation](https://llm.datasette.io/en/stable/tools.html)
- [LLM 0.26 Announcement](https://simonwillison.net/2025/May/27/llm-tools/)
- [Open Interpreter DeepWiki](https://deepwiki.com/OpenInterpreter/open-interpreter)
- [Open Interpreter Usage](https://docs.openinterpreter.com/guides/basic-usage)
- [Codex CLI Features](https://developers.openai.com/codex/cli/features/)
- [Codex CLI GitHub](https://github.com/openai/codex)
- [ShellGPT GitHub](https://github.com/TheR1D/shell_gpt)
- [Rich GitHub](https://github.com/Textualize/rich)
- [Rich Introduction](https://rich.readthedocs.io/en/stable/introduction.html)
- [Rich Panel Docs](https://rich.readthedocs.io/en/stable/panel.html)
- [Rich Live Docs](https://rich.readthedocs.io/en/stable/live.html)
- [Rich Box Styles](https://rich.readthedocs.io/en/stable/appendix/box.html)
- [Rich Console API](https://rich.readthedocs.io/en/stable/console.html)
- [OpenHands CLI Truncation Issue](https://github.com/OpenHands/OpenHands-CLI/issues/102)
- [CLI UX Progress Displays (Evil Martians)](https://evilmartians.com/chronicles/cli-ux-best-practices-3-patterns-for-improving-progress-displays)
- [LiteLLM Token Usage](https://docs.litellm.ai/docs/completion/token_usage)
