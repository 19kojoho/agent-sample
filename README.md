# agent-sample

A minimal reference application showing how to send agent traces to Galileo from
two different agent frameworks running on the same Bedrock model:

- **`langgraph_agent/`** uses LangGraph with the native Galileo SDK callback.
- **`strands_agent/`** uses the Strands SDK with the OpenTelemetry path.

Both agents call the same two mock tools and answer the same kind of question,
so the trace shape on the Galileo side is directly comparable across the two
frameworks.

This repository is meant as a reference. Clone it, run both agents, see traces
land in your Galileo project, then strip out the mock tools and drop in your
real ones.

## What the agents do

Both versions are a credit-rating research helper. The user asks for a briefing
on an issuer. The agent calls `lookup_issuer_profile` to confirm the entity,
then calls `lookup_rating_history` to get the recent rating actions, then
synthesizes a short briefing.

The data behind both tools is hard-coded and fictional. The issuer names are
real companies but the profile fields and rating actions are not factual. The
goal is to give the agent a multi-step trace that looks realistic when viewed
in the Galileo UI.

## What gets sent to Galileo

When you run either agent, Galileo receives a trace with this shape:

```
session
  └── trace (user question)
        └── agent run
              ├── tool: lookup_issuer_profile
              ├── llm call to Bedrock (Claude)
              ├── tool: lookup_rating_history
              ├── llm call to Bedrock (Claude)
              └── final agent message
```

The LangGraph version produces this through the native `GalileoCallback`.
The Strands version produces this through OpenTelemetry exported to
Galileo's OTel endpoint. The traces look the same in the Galileo UI.

## Quickstart

### 1. Prerequisites

- Python 3.10 or newer.
- An AWS account with Bedrock model access for Anthropic Claude. Bedrock
  serverless models auto-enable on first invocation, but Anthropic models
  may prompt for a one-time use-case form per account. Do that in the
  Bedrock playground before running the agents.
- AWS credentials available to `boto3`. Anything `boto3` can resolve will
  work: environment variables, a named profile in `~/.aws/credentials`,
  an EC2 instance role, an EKS service account role (IRSA), or an ECS task
  role. See `iam-credentials-with-strands-galileo.pdf` (sent separately) for
  the full set of patterns. No bearer token required.
- A Galileo API key from <https://app.galileo.ai/settings/api-keys>.

### 2. Clone and install

```bash
git clone https://github.com/19kojoho/agent-sample.git
cd agent-sample
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your Galileo API key and project name.
# AWS values can be left blank if your environment already has working
# AWS credentials (recommended for production deployments).
```

### 4. Run

```bash
# LangGraph variant (uses the native Galileo callback)
python -m langgraph_agent.agent

# Strands variant (uses the OpenTelemetry exporter)
python -m strands_agent.agent

# Or ask your own question
python -m langgraph_agent.agent "Tell me about JPMorgan Chase's credit trajectory."
```

Each run prints the agent's answer to your terminal and sends the trace to
your Galileo project.

## After the first run, in the Galileo UI

Open your project in the Galileo console. You should see a new log stream
called `production` with one or more traces.

1. **Inspect the trace.** Click any trace to see the agent run, the two tool
   calls, the two LLM calls to Bedrock, and the final message. This is the
   trace shape you can expect from any tool-using agent.

2. **Enable evaluation metrics.** On the log stream settings page, enable
   these metrics. Each runs on every trace going forward and backfills onto
   the traces you have already sent:

   - `context_adherence_luna` — uses Galileo's purpose-built small language
     model. Cheap, fast, and runs on the cluster.
   - `tool_selection_quality` — flags traces where the agent called the
     wrong tool or skipped one it should have called.
   - `tool_error_rate` — surfaces tool calls that returned errors.

   Once enabled, switch back to the traces view. The scores attach
   automatically.

3. **Add a custom metric.** Click "Create metric" on the log stream. Pick
   "LLM-as-judge". Paste this as the natural-language description:

   > Detect when the agent's response references a rating value, date, or
   > rationale that does not appear in the output of either lookup tool.
   > Score 1 = fabricated content detected, 0 = all stated facts are present
   > in the retrieved tool outputs.

   Galileo will auto-generate a Chain-Poll judge prompt. Validate it on the
   log stream, give feedback on any misses, and Galileo will tune the judge.

## Project layout

```
agent-sample/
├── README.md              this file
├── LICENSE                MIT
├── requirements.txt       pinned dependencies
├── .env.example           template for your local config
├── common/
│   └── tools.py           shared mock tool implementations
├── langgraph_agent/
│   └── agent.py           LangGraph agent with GalileoCallback
└── strands_agent/
    └── agent.py           Strands agent with OTel exporter
```

`common/tools.py` defines both tool functions in plain Python. Each agent
file wraps them in the framework's tool decorator. Swap in your real
business tools by editing the two `lookup_*` functions or by adding new
ones and importing them in the agent files.

## Hand-off notes

If you are picking this up from someone else's account:

- All Galileo configuration is in `.env`. Update the API key, project name,
  and log stream to point at your own Galileo project.
- All AWS configuration is whatever `boto3` resolves locally. The agents
  themselves never read AWS keys from disk.
- `BEDROCK_MODEL_ID` in `.env` controls which Claude model gets called. The
  default is Claude Haiku 4.5 for cost. Swap to Sonnet 4.6 or any Opus 4.x
  variant by changing this one value.
- Neither agent persists state between runs. Stop and start at will.

## Notes on the Strands path

The Strands agent uses OpenTelemetry instead of a native Galileo callback.
That is the supported integration today and produces the same trace shape
in the Galileo UI. Native Strands support in the Galileo SDK is on the
roadmap. When it lands, this sample will be updated to use it; the
customer-facing API in `strands_agent/agent.py` will not change.

## License

MIT. See `LICENSE`.
