"""Create the two Luna runtime guardrails in Agent Control and bind them to the log stream.

Run once per environment:

    python setup_guardrails.py

What it creates:

1. `credit_block_prompt_injection`
   Step `screen_question`, pre stage. Scores the analyst's question with the
   Prompt Injection (SLM) Luna scorer. Score >= PROMPT_INJECTION_THRESHOLD
   denies the request before the agent runs.

2. `credit_briefing_context_adherence`
   Step `check_briefing`, post stage. Scores the briefing against the
   question and tool outputs with the Context Adherence (SLM) Luna scorer.
   Score < CONTEXT_ADHERENCE_THRESHOLD steers to a safe reply instead of
   returning a briefing the tool data does not support.

Both controls run with execution="server": the Agent Control server calls
Luna inside your Galileo deployment, so the question and briefing are scored
where Galileo runs and the agent process needs no extra model access.

Each control is bound to the Galileo log stream in GALILEO_PROJECT /
GALILEO_LOG_STREAM, the same one the agent sends traces to, so the guardrails
show up next to that log stream in the console.

Luna scorer IDs differ between Galileo environments, so this script looks
them up by name. Re-running it is safe: existing controls are reused.
"""
from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import agent_control
from galileo.scorers import Scorers

from common.guardrails import BLOCKED_REPLY, DEFAULT_AGENT_NAME, log_stream_id

PROMPT_INJECTION_SCORER = "prompt_injection_luna"
CONTEXT_ADHERENCE_SCORER = "context_adherence_luna"

PROMPT_INJECTION_THRESHOLD = float(os.getenv("PROMPT_INJECTION_THRESHOLD", "0.5"))
CONTEXT_ADHERENCE_THRESHOLD = float(os.getenv("CONTEXT_ADHERENCE_THRESHOLD", "0.5"))

SAFE_BRIEFING_REPLY = (
    "I could not verify every rating, date, or rationale in this briefing "
    "against the issuer profile and rating history on file, so I am not "
    "returning it. Please re-run the request or check the rating history "
    "directly."
)


def _scorer_id(name: str) -> str:
    matches = [s for s in Scorers().list(name=name) if s.name == name]
    if not matches:
        sys.exit(
            f"ERROR: Luna scorer '{name}' not found in this Galileo environment. "
            "Check GALILEO_CONSOLE_URL and that Luna scorers are enabled."
        )
    return str(matches[0].id)


def _controls(prompt_injection_id: str, context_adherence_id: str) -> dict[str, dict]:
    return {
        "credit_block_prompt_injection": {
            "description": "Deny analyst questions that Luna scores as prompt injection.",
            "enabled": True,
            "execution": "server",
            "tags": ["agent-sample", "luna", "prompt-injection"],
            "scope": {
                "step_types": ["llm"],
                "step_names": ["screen_question"],
                "stages": ["pre"],
            },
            "condition": {
                "selector": {"path": "input"},
                "evaluator": {
                    "name": "galileo.luna",
                    "config": {
                        "scorer_id": prompt_injection_id,
                        "scorer_label": "Prompt Injection (SLM)",
                        "operator": "gte",
                        "threshold": PROMPT_INJECTION_THRESHOLD,
                        "payload_field": "input",
                    },
                },
            },
            "action": {
                "decision": "deny",
                "steering_context": {"message": BLOCKED_REPLY},
            },
        },
        "credit_briefing_context_adherence": {
            "description": (
                "Steer to a safe reply when Luna scores the briefing as not "
                "supported by the lookup tool outputs."
            ),
            "enabled": True,
            "execution": "server",
            "tags": ["agent-sample", "luna", "context-adherence"],
            "scope": {
                "step_types": ["llm"],
                "step_names": ["check_briefing"],
                "stages": ["post"],
            },
            "condition": {
                # "*" hands Luna the whole step: input = question + tool
                # outputs, output = briefing.
                "selector": {"path": "*"},
                "evaluator": {
                    "name": "galileo.luna",
                    "config": {
                        "scorer_id": context_adherence_id,
                        "scorer_label": "Context Adherence (SLM)",
                        "operator": "lt",
                        "threshold": CONTEXT_ADHERENCE_THRESHOLD,
                    },
                },
            },
            "action": {
                "decision": "steer",
                "steering_context": {"message": SAFE_BRIEFING_REPLY},
            },
        },
    }


async def _find_control_id(name: str) -> int | None:
    res = await agent_control.list_controls(name=name, limit=10)
    for c in res.get("controls") or res.get("items") or []:
        if c.get("name") == name:
            return c.get("id")
    return None


async def main() -> None:
    if not (os.getenv("AGENT_CONTROL_API_KEY") or os.getenv("GALILEO_API_KEY")):
        sys.exit("ERROR: set GALILEO_API_KEY (or AGENT_CONTROL_API_KEY) in .env")
    if not os.getenv("AGENT_CONTROL_URL"):
        sys.exit("ERROR: set AGENT_CONTROL_URL in .env")
    os.environ.setdefault("AGENT_CONTROL_API_KEY", os.environ.get("GALILEO_API_KEY", ""))
    os.environ.setdefault("AGENT_CONTROL_API_KEY_HEADER", "Galileo-API-Key")

    agent_name = os.getenv("AGENT_CONTROL_AGENT_NAME", DEFAULT_AGENT_NAME)
    print(f"Agent Control: {os.environ['AGENT_CONTROL_URL']}")
    print(f"Agent        : {agent_name}\n")

    print("[1/3] Looking up Luna scorers")
    pi_id = _scorer_id(PROMPT_INJECTION_SCORER)
    ca_id = _scorer_id(CONTEXT_ADHERENCE_SCORER)
    print(f"  {PROMPT_INJECTION_SCORER}: {pi_id}")
    print(f"  {CONTEXT_ADHERENCE_SCORER}: {ca_id}")

    stream_id = log_stream_id()
    print(f"\n[2/3] Registering agent on log stream {stream_id}")
    agent_control.init(
        agent_name=agent_name,
        agent_description="Credit-rating research helper with Luna runtime guardrails.",
        agent_version="1.0.0",
        target_type="log_stream",
        target_id=stream_id,
        policy_refresh_interval_seconds=0,
    )

    print("\n[3/3] Creating controls and binding them to the log stream")
    for name, definition in _controls(pi_id, ca_id).items():
        cid = await _find_control_id(name)
        if cid is None:
            cid = (await agent_control.create_control(name=name, data=definition))["control_id"]
            print(f"  created {name} (id {cid})")
        else:
            print(f"  reused  {name} (id {cid})")

        bound_name = f"{name}-{stream_id[:8]}"
        if await _find_control_id(bound_name) is None:
            bound = await agent_control.clone_and_bind_control(
                cid, target_type="log_stream", target_id=stream_id, name=bound_name
            )
            print(f"    bound to log stream as {bound_name} (id {bound['id']})")
        else:
            print(f"    already bound as {bound_name}")

    print("\nDone. Set GUARDRAILS_ENABLED=true in .env and run either agent.")


if __name__ == "__main__":
    asyncio.run(main())
