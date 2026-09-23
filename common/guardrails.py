"""Runtime guardrails for the credit-rating research helper.

Two checks run around every agent call, both scored by Galileo Luna small
language models through Agent Control:

- Before the agent runs, `screen_question` sends the analyst's question to
  the Prompt Injection (SLM) scorer. If the control fires, the request is
  denied and the agent never runs.
- After the agent answers, `check_briefing` sends the briefing, plus the
  question and tool outputs it was based on, to the Context Adherence (SLM)
  scorer. If the briefing is not supported by what the tools returned, the
  control steers: the briefing is replaced with a safe reply.

The controls themselves (scorer, threshold, action) live on the Agent Control
server, not in this file. Create them once with `python setup_guardrails.py`,
then tune thresholds or switch actions in the Galileo console without
touching code. The decorators below only mark where the checks run.

Guardrails are off unless GUARDRAILS_ENABLED=true, so the agents keep
working exactly as before for anyone who has not set up Agent Control.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import agent_control
from agent_control import ControlSteerError, ControlViolationError, control

logger = logging.getLogger(__name__)

DEFAULT_AGENT_NAME = "agent-sample-credit-research"

BLOCKED_REPLY = (
    "This request was blocked by a runtime guardrail because it looks like an "
    "attempt to override the assistant's instructions. Please rephrase it as a "
    "research question about an issuer."
)

_initialized = False


def guardrails_enabled() -> bool:
    return os.getenv("GUARDRAILS_ENABLED", "false").lower() in ("1", "true", "yes")


def init_guardrails() -> bool:
    """Register this agent with Agent Control. Returns True when guardrails are active."""
    global _initialized
    if _initialized:
        return True
    if not guardrails_enabled():
        return False

    # The @control decorator reads these from the environment on every call,
    # so set them here rather than only passing them to init().
    os.environ.setdefault("AGENT_CONTROL_API_KEY", os.getenv("GALILEO_API_KEY", ""))
    os.environ.setdefault("AGENT_CONTROL_API_KEY_HEADER", "Galileo-API-Key")

    # Controls are bound to the Galileo log stream this agent logs to, and
    # runtime checks authenticate against that same log stream.
    agent_control.init(
        agent_name=os.getenv("AGENT_CONTROL_AGENT_NAME", DEFAULT_AGENT_NAME),
        agent_description="Credit-rating research helper with Luna runtime guardrails.",
        agent_version="1.0.0",
        target_type="log_stream",
        target_id=log_stream_id(),
    )
    _initialized = True
    return True


def log_stream_id() -> str:
    """Resolve the ID of GALILEO_PROJECT / GALILEO_LOG_STREAM (or AGENT_CONTROL_TARGET_ID)."""
    if os.getenv("AGENT_CONTROL_TARGET_ID"):
        return os.environ["AGENT_CONTROL_TARGET_ID"]

    from galileo.log_streams import LogStreams

    project = os.getenv("GALILEO_PROJECT", "agent-sample")
    name = os.getenv("GALILEO_LOG_STREAM", "production")
    for stream in LogStreams().list(project_name=project):
        if stream.name == name:
            return str(stream.id)
    raise RuntimeError(
        f"Log stream '{name}' not found in project '{project}'. Run the agent once "
        "with guardrails off to create it, or set AGENT_CONTROL_TARGET_ID."
    )


# --- Guarded steps ---------------------------------------------------------
# Agent Control reads the `input` argument as the step input and the return
# value as the step output. The controls created by setup_guardrails.py are
# scoped to these step names.

@control(step_name="screen_question")
def _screen_question(input: str) -> str:
    return input


@control(step_name="check_briefing")
def _check_briefing(input: str, briefing: str) -> str:
    return briefing


# --- Public helpers used by both agents ------------------------------------

def screen_question(question: str) -> str | None:
    """Return a blocked reply if the question is denied, otherwise None."""
    if not init_guardrails():
        return None
    try:
        _screen_question(question)
    except ControlViolationError as exc:
        logger.warning("Guardrail denied the question: %s", exc)
        return BLOCKED_REPLY
    except ControlSteerError as exc:
        return exc.steering_context
    return None


def check_briefing(question: str, tool_outputs: list[Any], briefing: str) -> str:
    """Return the briefing if it is grounded in the tool outputs, else the steered reply."""
    if not init_guardrails():
        return briefing
    context = format_context(question, tool_outputs)
    try:
        return _check_briefing(context, briefing)
    except ControlSteerError as exc:
        logger.warning("Guardrail steered the briefing: %s", exc)
        return exc.steering_context
    except ControlViolationError as exc:
        logger.warning("Guardrail denied the briefing: %s", exc)
        return BLOCKED_REPLY


def format_context(question: str, tool_outputs: list[Any]) -> str:
    """Build the text Luna treats as the source of truth for the briefing."""
    parts = [f"Analyst question: {question}", "Tool outputs:"]
    for out in tool_outputs:
        parts.append(out if isinstance(out, str) else json.dumps(out))
    return "\n".join(parts)
