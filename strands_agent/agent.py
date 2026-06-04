"""Credit-rating research helper, built on Strands + Bedrock.

Runs a Strands Agent that calls two mock tools, hits an Anthropic Claude
model on Bedrock through the AWS Converse API, and ships every span to
Galileo via OpenTelemetry. Native Galileo SDK support for Strands is on
the roadmap; until then the OTel path is the supported integration and
produces the same trace shape in the Galileo UI.

Run:
    python -m strands_agent.agent
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from strands.telemetry import StrandsTelemetry

from common.tools import (
    SYSTEM_PROMPT,
    lookup_issuer_profile,
    lookup_rating_history,
)


def _configure_galileo_otel() -> None:
    """Wire Strands' OTel exporter to send traces to the Galileo OTel endpoint."""
    os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = os.environ.get(
        "GALILEO_API_ENDPOINT", "https://api.galileo.ai/otel/traces"
    )
    headers = {
        "Galileo-API-Key": os.environ["GALILEO_API_KEY"],
        "project": os.environ.get("GALILEO_PROJECT", "agent-sample"),
        "logstream": os.environ.get("GALILEO_LOG_STREAM", "production"),
    }
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = ",".join(f"{k}={v}" for k, v in headers.items())

    telemetry = StrandsTelemetry()
    telemetry.setup_otlp_exporter()


@tool
def lookup_issuer_profile_tool(issuer_name: str) -> dict:
    """Look up the static profile (sector, country, HQ, last filing date) for an issuer.

    Args:
        issuer_name: The company name to look up. Partial matches are tolerated.
    """
    return lookup_issuer_profile(issuer_name)


@tool
def lookup_rating_history_tool(issuer_name: str) -> dict:
    """Return the recent credit rating actions for an issuer, most recent first.

    Args:
        issuer_name: The company name to look up. Partial matches are tolerated.
    """
    return lookup_rating_history(issuer_name)


def build_agent() -> Agent:
    model = BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        temperature=0,
        max_tokens=1024,
    )
    return Agent(
        model=model,
        tools=[lookup_issuer_profile_tool, lookup_rating_history_tool],
        system_prompt=SYSTEM_PROMPT,
    )


def main() -> None:
    load_dotenv()
    _configure_galileo_otel()
    agent = build_agent()

    question = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "Give me a credit briefing on The Boeing Company. What is the recent trajectory?"
    )
    print(f"\nQ: {question}\n")
    result = agent(question)
    print(f"\nA: {result}\n")


if __name__ == "__main__":
    main()
