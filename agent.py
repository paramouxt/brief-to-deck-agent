"""Brief-to-Deck Agent.

Turns a one-line brief into a client-ready PowerPoint deck and Excel data
appendix, fully autonomously: web research -> analysis -> document generation.

Cost-aware by design: a cheap router call (Claude Haiku) first assesses how
demanding the brief is, then routes the work to the cheapest Claude model
that can still produce client-ready quality — Sonnet 4.6 for standard briefs,
Opus 4.8 for complex ones, Fable 5 only when frontier reasoning is the
binding constraint. The work model runs with Anthropic server-side tools
(web search, web fetch, code execution), so the entire research-and-build
loop runs on Anthropic's infrastructure — this script only orchestrates,
streams progress, downloads the generated files, and records run metrics.

Usage:
    python agent.py "competitive landscape for meal-kit delivery in India"
    python agent.py "..." --model fable   # skip routing, force a model
    python agent.py "..." --agent-mode direct
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import anthropic

from prompts import DIRECT_MODE_PROMPT, ROUTER_PROMPT, SYSTEM_PROMPT, TEAM_MODE_PROMPT

MAX_TOKENS = 64000
# Server-side tools pause every ~10 internal iterations (stop_reason
# "pause_turn"); we resume up to this many times before giving up.
MAX_CONTINUATIONS = 12

# USD per million tokens (input, output). Cache read is ~0.1x input,
# cache write ~1.25x input.
PRICING = {
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Routing: cheapest model that can still produce client-ready quality
# for each complexity tier.
ROUTER_MODEL = "claude-haiku-4-5"
TIER_TO_MODEL = {
    "standard": "claude-sonnet-4-6",
    "complex": "claude-opus-4-8",
    "frontier": "claude-fable-5",
}
MODEL_SHORTHAND = {
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-8",
    "fable": "claude-fable-5",
}
AGENT_MODES = {
    "direct": DIRECT_MODE_PROMPT,
    "team": TEAM_MODE_PROMPT,
}

ROUTER_SCHEMA = {
    "type": "object",
    "properties": {
        "complexity": {"type": "string", "enum": ["standard", "complex", "frontier"]},
        "rationale": {"type": "string"},
    },
    "required": ["complexity", "rationale"],
    "additionalProperties": False,
}

TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
    {"type": "code_execution_20260120", "name": "code_execution"},
]


def load_dotenv(path: Path) -> None:
    """Minimal .env loader so the project has zero dependencies beyond the SDK."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def choose_model(client: anthropic.Anthropic, brief: str) -> dict:
    """Classify brief complexity with a cheap Haiku call and pick the work model.

    Costs a fraction of a cent and typically saves 50-70% on standard briefs
    by routing them to Sonnet instead of a frontier model.
    """
    try:
        response = client.messages.create(
            model=ROUTER_MODEL,
            max_tokens=500,
            output_config={"format": {"type": "json_schema", "schema": ROUTER_SCHEMA}},
            messages=[{"role": "user", "content": ROUTER_PROMPT.format(brief=brief)}],
        )
        text = next(b.text for b in response.content if b.type == "text")
        verdict = json.loads(text)
        in_tok, out_tok = response.usage.input_tokens, response.usage.output_tokens
        router_cost = (in_tok * PRICING[ROUTER_MODEL][0] + out_tok * PRICING[ROUTER_MODEL][1]) / 1_000_000
        return {
            "model": TIER_TO_MODEL[verdict["complexity"]],
            "complexity": verdict["complexity"],
            "rationale": verdict["rationale"],
            "router_cost_usd": round(router_cost, 5),
        }
    except Exception as exc:  # routing must never block the run
        print(f"  [router] failed ({exc}); defaulting to claude-opus-4-8", file=sys.stderr)
        return {
            "model": "claude-opus-4-8",
            "complexity": "complex",
            "rationale": f"router fallback: {exc}",
            "router_cost_usd": 0.0,
        }


def build_system_blocks(agent_mode: str) -> list[dict]:
    """Return cached system instructions for the selected work style."""
    if agent_mode not in AGENT_MODES:
        raise ValueError(f"unknown agent mode: {agent_mode}")
    return [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            # Cache the system prompt: repeat runs and pause_turn
            # continuations reread it at ~10% of input price.
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": AGENT_MODES[agent_mode],
            "cache_control": {"type": "ephemeral"},
        },
    ]


def stream_one_turn(client: anthropic.Anthropic, request: dict) -> anthropic.types.Message:
    """Run one streamed API call, printing live progress, and return the final message."""
    with client.messages.stream(**request) as stream:
        for event in stream:
            if event.type == "content_block_start":
                block = event.content_block
                if block.type == "server_tool_use":
                    print(f"\n  [tool] {block.name}", flush=True)
                elif block.type == "text":
                    print()
            elif event.type == "content_block_delta":
                if event.delta.type == "text_delta":
                    print(event.delta.text, end="", flush=True)
        return stream.get_final_message()


def accumulate_usage(totals: dict, usage) -> None:
    totals["input"] += usage.input_tokens
    totals["output"] += usage.output_tokens
    totals["cache_read"] += usage.cache_read_input_tokens or 0
    totals["cache_write"] += usage.cache_creation_input_tokens or 0


def estimate_cost(totals: dict, model: str) -> float:
    price_in, price_out = PRICING[model]
    return (
        totals["input"] * price_in
        + totals["output"] * price_out
        + totals["cache_read"] * price_in * 0.1
        + totals["cache_write"] * price_in * 1.25
    ) / 1_000_000


def download_generated_files(client: anthropic.Anthropic, responses: list, outdir: Path) -> list:
    """Find files the agent created in the code-execution sandbox and save them locally."""
    saved = []
    seen_ids = set()
    for response in responses:
        for block in response.content:
            if block.type != "bash_code_execution_tool_result":
                continue
            result = block.content
            if result.type != "bash_code_execution_result" or not result.content:
                continue
            for ref in result.content:
                if ref.type != "bash_code_execution_output" or ref.file_id in seen_ids:
                    continue
                seen_ids.add(ref.file_id)
                metadata = client.beta.files.retrieve_metadata(ref.file_id)
                # basename guards against path traversal in generated filenames
                safe_name = os.path.basename(metadata.filename)
                if not safe_name or safe_name in (".", ".."):
                    continue
                target = outdir / safe_name
                client.beta.files.download(ref.file_id).write_to_file(str(target))
                saved.append(target)
                print(f"  saved {target}")
    return saved


def run(
    brief: str,
    outdir: Path,
    forced_model: str | None = None,
    agent_mode: str = "team",
) -> int:
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": brief}]
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    responses = []
    container_id = None
    start = time.monotonic()

    print(f"Brief: {brief}")
    print(f"Agent mode: {agent_mode}")
    if forced_model:
        routing = {
            "model": forced_model,
            "complexity": "manual override",
            "rationale": "model forced via --model flag",
            "router_cost_usd": 0.0,
        }
    else:
        routing = choose_model(client, brief)
    model = routing["model"]
    print(f"Model: {model} ({routing['complexity']}) — {routing['rationale']}\n{'=' * 60}")

    for turn in range(MAX_CONTINUATIONS):
        request = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "system": build_system_blocks(agent_mode),
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "high"},
            "tools": TOOLS,
            "messages": messages,
        }
        if container_id:
            # Reuse the sandbox container so files persist across continuations.
            request["container"] = container_id

        response = stream_one_turn(client, request)
        responses.append(response)
        accumulate_usage(totals, response.usage)
        if response.container:
            container_id = response.container.id

        if response.stop_reason == "pause_turn":
            # Server-side tool loop hit its iteration limit; append the
            # assistant turn and re-send — the server resumes automatically.
            messages.append({"role": "assistant", "content": response.content})
            continue
        if response.stop_reason == "refusal":
            print("\nThe model refused this brief.", file=sys.stderr)
            return 1
        break
    else:
        print(f"\nStopped after {MAX_CONTINUATIONS} continuations without finishing.", file=sys.stderr)

    elapsed = time.monotonic() - start
    print(f"\n{'=' * 60}\nDownloading deliverables...")
    outdir.mkdir(parents=True, exist_ok=True)
    saved = download_generated_files(client, responses, outdir)

    metrics = {
        "brief": brief,
        "agent_mode": agent_mode,
        "model": model,
        "routing": routing,
        "wall_clock_seconds": round(elapsed, 1),
        "api_turns": len(responses),
        "tokens": totals,
        "estimated_cost_usd": round(estimate_cost(totals, model) + routing["router_cost_usd"], 4),
        "files": [p.name for p in saved],
    }
    metrics_path = outdir / "run_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(
        f"\nDone in {elapsed / 60:.1f} min | est. cost ${metrics['estimated_cost_usd']:.2f} "
        f"| {len(saved)} file(s) -> {outdir}"
    )
    print(f"Metrics written to {metrics_path}")
    if not saved:
        print(
            "Warning: no files were produced. Check the transcript above — the "
            "agent may have hit an error before saving the deliverables.",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Turn a one-line brief into a client-ready deck + data appendix."
    )
    parser.add_argument("brief", help='e.g. "competitive landscape for meal-kit delivery in India"')
    parser.add_argument(
        "--outdir",
        type=Path,
        default=None,
        help="Output directory (default: outputs/<slugified-brief>/)",
    )
    parser.add_argument(
        "--model",
        default="auto",
        help=(
            "auto (default: a cheap router call picks the most cost-efficient "
            "model for the brief), or force one: sonnet | opus | fable, "
            "or any full model id"
        ),
    )
    parser.add_argument(
        "--agent-mode",
        choices=sorted(AGENT_MODES),
        default="team",
        help=(
            "team (default: use a virtual pod of specialist agents inside the "
            "same autonomous Claude loop), or direct (single consultant mode)"
        ),
    )
    args = parser.parse_args()

    forced_model = None
    if args.model != "auto":
        forced_model = MODEL_SHORTHAND.get(args.model, args.model)
        if forced_model not in PRICING:
            sys.exit(
                f"Unknown model '{args.model}'. Use auto, sonnet, opus, fable, "
                f"or one of: {', '.join(sorted(PRICING))}"
            )

    load_dotenv(Path(__file__).parent / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your "
            "key, or set the environment variable."
        )

    outdir = args.outdir
    if outdir is None:
        slug = re.sub(r"[^a-z0-9]+", "-", args.brief.lower()).strip("-")[:60]
        outdir = Path(__file__).parent / "outputs" / slug

    sys.exit(run(args.brief, outdir, forced_model, args.agent_mode))


if __name__ == "__main__":
    main()
