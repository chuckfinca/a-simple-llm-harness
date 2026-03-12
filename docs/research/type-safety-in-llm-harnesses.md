# Type Safety in LLM Harnesses: Practitioner Research

Research date: 2026-03-09

## Context

This harness is ~700 lines, no framework, uses `mypy --strict`. The question:
is `dict[str, Any]` everywhere a liability, or pragmatic at this scale?

## Finding 1: litellm's ModelResponse Is Not mypy-Strict Compatible

**`ModelResponse.usage` is an extra field, not a declared field.** litellm's
`ModelResponse` inherits from a Pydantic BaseModel with `extra='allow'`, and
`usage` is passed through `super().__init__(**init_values)` only when present.
The declared `model_fields` are: `id`, `created`, `model`, `object`,
`system_fingerprint`, `choices`. That's it.

Consequence: `response: ModelResponse` followed by `response.usage` produces
`error: "ModelResponse" has no attribute "usage" [attr-defined]` under
`mypy --strict`.

**The only patterns that pass mypy strict:**
- `response: Any` with `getattr(response, "usage", None)` -- what the
  codebase already does
- `response: ModelResponse` with `getattr(response, "usage", None)` -- works
  but you gain almost nothing over `Any` since you still can't use dot access

**Verdict: `response: Any` for litellm responses is the pragmatic choice.**
This isn't laziness -- it's a direct consequence of litellm's type
architecture. The library ships `py.typed` but its core response type has
critical fields as dynamic extras. Until litellm declares `usage` as a proper
field (it's a known gap, PR #4258 added some type hints but not this), you
cannot avoid `Any` or `getattr` here.

### What about `_hidden_params`?

The `_extract_cost` function accesses `response._hidden_params`. This is an
undocumented internal attribute not in any type definition. `Any` is the only
honest annotation for code that accesses this.

## Finding 2: The CustomLogger Callback Interface Is Untyped

litellm's `CustomLogger` base class declares its callback methods with **zero
type annotations**:

```python
def log_success_event(self, kwargs, response_obj, start_time, end_time):
    pass
```

However, litellm's internal call sites type `start_time` and `end_time` as
`datetime.datetime`. The `response_obj` is a `ModelResponse` (but with the
same `usage` problem above). The `kwargs` is `dict[str, Any]`.

**Current codebase approach (using `Any` for all four) is the only approach
that matches the base class signature without lying.** If you annotate
`start_time: datetime.datetime`, you're adding a type claim the base class
doesn't make, which could break if litellm changes behavior.

**Recommended improvement:** Add `datetime.datetime` for `start_time` and
`end_time` anyway -- litellm has used `datetime.datetime` internally since at
least 2024 and this is unlikely to change. The risk is low and the readability
gain is real. For `response_obj`, keep `Any`.

## Finding 3: `Message = dict[str, Any]` vs TypedDict

### What practitioners recommend

**Samuel Colvin (Pydantic creator):** Type checking is "a no-brainer in
Python" for production applications. Pydantic AI uses generics extensively.
However, his framework targets larger codebases where the investment pays off.

**Jason Liu (Instructor):** Pydantic models serve as a "contract between the
developer and the model." He advocates structured outputs, but his library is
specifically about LLM *output* validation, not internal message plumbing.

**LangGraph team:** Uses TypedDict for internal state (lightweight, zero
runtime cost), Pydantic at boundaries (validation, safety). Their explicit
recommendation: "State = TypedDict (fast, minimal). Each node's inputs/outputs
validated with Pydantic."

**OpenAI Python SDK:** Messages are TypedDicts (`ChatCompletionMessageParam`
is a Union of `ChatCompletionUserMessageParam`,
`ChatCompletionAssistantMessageParam`, etc.). This is the canonical type for
the message format the codebase is building.

### What actually works with mypy strict

Tested the exact patterns from `agent.py`:

1. **TypedDict union for Message** -- works cleanly if you return
   `AssistantMessage` specifically from `_parse_response_message` instead of
   generic `Message`. The key insight: when you know you're building an
   assistant message, type it as `AssistantMessage`. The `messages` list stays
   typed as `list[Message]` (the union).

2. **Dict literal construction** -- mypy accepts dict literals that match
   TypedDict shapes without explicit constructors. `{"role": "user",
   "content": "hello"}` satisfies `UserMessage`.

3. **Friction point:** accessing `tool_calls` on a generic `Message` union
   member fails because not all variants have that key. This is actually a
   *feature* -- it forces you to narrow the type first (via `in` check or by
   tracking which variant you have).

### The practical trade-off for this codebase

Converting `Message = dict[str, Any]` to a TypedDict union would:

**Gains:**
- Catch key-name typos at check time (e.g., `"tool_call"` vs `"tool_calls"`)
- Document the message schema in code instead of in your head
- Make `_parse_response_message` return type precise

**Costs:**
- ~15 lines of type definitions
- Zero runtime cost (TypedDict is purely a typing construct)
- Some `.get()` calls would need `in` checks instead (but the codebase
  already uses both patterns)

**Verdict: TypedDict for messages is worth it.** The cost is trivial and the
gain is real -- especially since this is the core data structure flowing
through the entire agent loop.

## Finding 4: `ToolDef = dict[str, Any]` Is Fine

Tool definitions are JSON Schema objects passed directly to litellm. Their
shape is defined by the OpenAI API spec and the harness treats them as opaque
data. A TypedDict here would be:

```python
class ToolFunction(TypedDict):
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema -- inherently dynamic

class ToolDef(TypedDict):
    type: str
    function: ToolFunction
```

This adds type safety for the outer structure but the `parameters` field is
still `dict[str, Any]` because JSON Schema is inherently untyped.

**Verdict: optional improvement, low priority.** The tool definitions are
static constants defined once in `tools.py` and passed through unchanged.
Typos here would be caught immediately by the LLM rejecting the tool, not
silently corrupted.

## Finding 5: `dict[str, Any]` for Tool Arguments Is Correct

In `execute_tool`, the parsed arguments from `json.loads(arguments_json)` are
genuinely `dict[str, Any]`. The LLM produces arbitrary JSON matching whatever
schema the tool declared. There is no static type that can represent "whatever
the LLM decided to send." `Any` is the honest type here.

## Finding 6: Where the Community Draws the Line

The consensus across practitioners (synthesized from Colvin, Liu, LangGraph
team, and production case studies):

| Data category | Recommended typing | Rationale |
|---|---|---|
| LLM response objects | `Any` or library type (when usable) | Third-party types often incomplete |
| Message lists | TypedDict union | Known, stable schema; catches real bugs |
| Tool definitions | `dict[str, Any]` or shallow TypedDict | Opaque data passed through unchanged |
| Tool arguments (from LLM) | `dict[str, Any]` | Genuinely dynamic; no static type fits |
| LLM structured outputs | Pydantic model | This is Instructor/PydanticAI's entire thesis |
| Agent internal state | TypedDict (small) or Pydantic (complex) | Depends on whether you need validation |
| Callback/webhook kwargs | `dict[str, Any]` | Third-party contract; can't control shape |

**The line:** Type what you control and what has a stable shape. Use `Any`
for what you don't control or what is inherently dynamic.

## Recommendations for This Codebase

### Do now (high value, low cost)

1. **Add TypedDict definitions for messages** in `types.py`. Four small
   TypedDicts (`SystemMessage`, `UserMessage`, `AssistantMessage`,
   `ToolMessage`) and a `Message` union. ~15 lines. Change
   `_parse_response_message` return type to `AssistantMessage`.

2. **Type `start_time` and `end_time` as `datetime.datetime`** in
   `telemetry.py`. litellm has used `datetime.datetime` here consistently and
   it makes the `_compute_latency` function self-documenting.

### Consider later (moderate value)

3. **Add a shallow TypedDict for `ToolDef`** if the tool definition list grows
   or if you add dynamic tool generation. Not urgent while definitions are
   static constants.

### Leave as-is (correct use of Any)

4. **`response: Any` in agent.py** -- litellm's `ModelResponse` doesn't
   expose `usage` as a typed field. `Any` with `getattr` is the correct
   pattern until litellm fixes their type definitions.

5. **`response_obj: Any` in telemetry.py** -- same reason, plus the base
   class is untyped.

6. **`dict[str, Any]` for parsed tool arguments** -- genuinely dynamic data.

7. **`dict[str, Any]` for `kwargs` in callbacks** -- third-party contract.

## Sources

- [Type Safety in LangGraph: When to Use TypedDict vs. Pydantic](https://shazaali.substack.com/p/type-safety-in-langgraph-when-to) -- LangGraph team's TypedDict-at-core, Pydantic-at-boundaries recommendation
- [Agent Engineering with Pydantic + Graphs -- with Samuel Colvin](https://www.latent.space/p/pydantic) -- Colvin on type safety being "a no-brainer" for production Python
- [High Agency Pydantic > VC Backed Frameworks -- with Jason Liu of Instructor](https://www.latent.space/p/instructor) -- Liu on typed responses as contracts, Pydantic over raw dicts
- [Pydantic AI documentation: Output types](https://ai.pydantic.dev/output/) -- supported output type patterns
- [OpenAI Python SDK: completion_create_params.py](https://github.com/openai/openai-python/blob/main/src/openai/types/chat/completion_create_params.py) -- canonical TypedDict message format
- [litellm PR #4258: add more type hints](https://github.com/BerriAI/litellm/pull/4258) -- litellm's ongoing type improvement effort
- [litellm Custom Callbacks documentation](https://docs.litellm.ai/docs/observability/custom_callback) -- untyped callback interface
- [OpenAI Python SDK issue #911: Fix typing errors from mypy](https://github.com/openai/openai-python/issues/911) -- mypy friction with OpenAI SDK message types

## Verification

All typing recommendations were tested against `mypy --strict` using the
project's Python 3.12 and current dependency versions. The litellm
`ModelResponse.usage` mypy failure was confirmed empirically, not assumed.
