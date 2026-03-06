from __future__ import annotations

import os

import litellm
from dotenv import load_dotenv

from llm_harness.agent import run_agent_loop
from llm_harness.telemetry import JsonlLogger
from llm_harness.tools import TOOL_DEFINITIONS
from llm_harness.types import Message


def main() -> None:
    load_dotenv()

    model = os.environ.get("LH_MODEL")
    if not model:
        print("error> LH_MODEL is required (set in .env or environment)")
        print("example: LH_MODEL=gemini/gemini-2.5-flash")
        return

    system_prompt = os.environ.get("LH_SYSTEM_PROMPT")
    if not system_prompt:
        print("error> LH_SYSTEM_PROMPT is required (set in .env or environment)")
        return

    litellm.callbacks = [JsonlLogger()]

    messages: list[Message] = [{"role": "system", "content": system_prompt}]

    print(f"llm-harness ({model})")
    print("Type 'quit' to exit.\n")

    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            break

        messages.append({"role": "user", "content": user_input})

        try:
            reply = run_agent_loop(
                model=model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                completion=litellm.completion,
            )
        except Exception as exc:
            messages.pop()
            print(f"\nerror> {exc}\n")
            continue

        if reply:
            print(f"\nassistant> {reply}\n")
        else:
            print("\nassistant> [max turns reached]\n")


if __name__ == "__main__":
    main()
