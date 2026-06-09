"""Brief-to-Deck Agent.

Turns a one-line brief into a client-ready PowerPoint deck and Excel data
appendix, fully autonomously: web research -> analysis -> document generation.

Built on Claude Fable 5 with Anthropic server-side tools (web search, web
fetch, code execution), so the entire research-and-build loop runs on
Anthropic's infrastructure — this script only orchestrates, streams progress,
downloads the generated files, and records run metrics.

Usage:
    python agent.py "competitive landscape for meal-kit delivery in India"
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import anthropic

from prompts import SYSTEM_PROMPT

MODEL = "claude-fable-5"
MAX_TOKENS = 64000
# Server-side tools pause every ~10 internal iterations (stop_reason
# "pause_turn"); we resume up to this many times before giving up.
MAX_CONTINUATIONS = 12

# Claude Fable 5 pricing, USD per million tokens.
PRICE = {
    "input": 10.00,
    "output": 50.00,
    "cache_read": 1.00,   # ~0.1x input
    "cache_write": 12.50,  # ~1.25x input
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


def estimate_cost(totals: dict) -> float:
    return sum(totals[k] / 1_000_000 * PRICE[k] for k in PRICE)


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


def run(brief: str, outdir: Path) -> int:
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": brief}]
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    responses = []
    container_id = None
    start = time.monotonic()

    print(f"Brief: {brief}\n{'=' * 60}")

    for turn in range(MAX_CONTINUATIONS):
        request = {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "system": [
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    # Cache the system prompt: repeat runs and pause_turn
                    # continuations reread it at ~10% of input price.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
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
        "model": MODEL,
        "wall_clock_seconds": round(elapsed, 1),
        "api_turns": len(responses),
        "tokens": totals,
        "estimated_cost_usd": round(estimate_cost(totals), 4),
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
    args = parser.parse_args()

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

    sys.exit(run(args.brief, outdir))


if __name__ == "__main__":
    main()
