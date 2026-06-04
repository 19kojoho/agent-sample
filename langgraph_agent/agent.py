"""Credit-rating research helper, built on LangGraph + Bedrock.

Runs a prebuilt ReAct-style agent that calls two mock tools, hits an
Anthropic Claude model on Bedrock through the AWS Converse API, and ships
every span to Galileo via the native GalileoCallback.

Run:
    python -m langgraph_agent.agent
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from galileo import galileo_context
from galileo.handlers.langchain import GalileoCallback

from common.tools import (
    SYSTEM_PROMPT,
    lookup_issuer_profile,
    lookup_rating_history,
)


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


def build_agent():
    model = ChatBedrockConverse(
        model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        temperature=0,
        max_tokens=1024,
    )
    return create_react_agent(
        model=model,
        tools=[lookup_issuer_profile_tool, lookup_rating_history_tool],
        prompt=SYSTEM_PROMPT,
    )


def run(question: str) -> str:
    agent = build_agent()
    callback = GalileoCallback()
    config = RunnableConfig(callbacks=[callback])

    with galileo_context(
        project=os.environ.get("GALILEO_PROJECT", "agent-sample"),
        log_stream=os.environ.get("GALILEO_LOG_STREAM", "production"),
    ):
        result = agent.invoke(
            {"messages": [HumanMessage(content=question)]},
            config=config,
        )
    return result["messages"][-1].content


def main() -> None:
    load_dotenv()
    question = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "Give me a credit briefing on The Boeing Company. What is the recent trajectory?"
    )
    print(f"\nQ: {question}\n")
    answer = run(question)
    print(f"A: {answer}\n")


if __name__ == "__main__":
    main()
