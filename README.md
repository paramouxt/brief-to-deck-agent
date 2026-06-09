# Brief-to-Deck Agent

**One-line brief in → client-ready PowerPoint deck + Excel data appendix out. Fully autonomous.**

```
python agent.py "competitive landscape for meal-kit delivery in India"
```

~15–20 minutes later you have a 10–14 slide consulting-style deck with cited sources, charts, a competitor comparison matrix, and an Excel appendix where every data row carries its source — work that would take a junior analyst one to two days.

Built on **Claude Fable 5** (Anthropic's most capable model) using server-side tools: the agent researches with live web search, reads sources in full, analyzes the data and renders charts in a sandboxed code environment, and builds the actual `.pptx` / `.xlsx` files with `python-pptx` and `openpyxl` — all in one autonomous loop with no human in between.

## Why this project exists

Knowledge-work automation is mostly talked about in the abstract. This repo is a concrete, measurable example: it takes a real consulting workflow (brief → research → analysis → deliverable), automates it end-to-end, and instruments the run so you can put numbers on it — wall-clock time, token usage, and cost per deliverable are written to `run_metrics.json` on every run.

## How it works

```mermaid
flowchart LR
    A[One-line brief] --> B[Claude Fable 5<br/>agent loop]
    B --> C[Web search<br/>8-12 sources]
    B --> D[Web fetch<br/>full articles]
    B --> E[Code execution sandbox<br/>analysis + charts]
    E --> F[deck.pptx<br/>python-pptx]
    E --> G[appendix.xlsx<br/>openpyxl]
    F --> H[Downloaded via Files API<br/>+ run_metrics.json]
    G --> H
```

The orchestration script (`agent.py`) is deliberately thin — about 200 lines. The heavy lifting happens server-side:

1. **Research** — the model searches the web, fetches the most important sources in full, and tracks URLs + publication dates for the sources slide.
2. **Analysis** — in Anthropic's sandboxed code-execution container it builds comparison tables, computes market sizing, and renders charts with matplotlib.
3. **Document generation** — it writes the deck and appendix with `python-pptx` / `openpyxl` (pre-installed in the sandbox), then the script downloads the files via the Files API.
4. **Metrics** — every run logs duration, tokens, and estimated cost.

The "product spec" of the deliverable — deck structure, quality bar, citation rules — lives entirely in [`prompts.py`](prompts.py), so you can iterate on the output quality without touching pipeline code.

### Engineering notes

- **Long-horizon autonomy**: server-side tool loops pause every ~10 iterations (`stop_reason: "pause_turn"`); the script resumes automatically, reusing the same sandbox container so files persist across continuations.
- **Adaptive thinking + high effort**: `thinking: {type: "adaptive"}` with `effort: "high"` lets the model decide when to reason deeply (source synthesis) vs. act (writing slides).
- **Prompt caching**: the system prompt is cached, so continuations and repeat runs reread it at ~10% of input price.
- **Cost tracking**: usage is accumulated across all turns and priced per token class (input / output / cache read / cache write).

## Quickstart

**Prerequisites:** Python 3.10+, an [Anthropic API key](https://platform.claude.com/).

```bash
git clone https://github.com/paramouxt/brief-to-deck-agent.git
cd brief-to-deck-agent
pip install -r requirements.txt

# Add your API key
cp .env.example .env        # then edit .env
# (Windows PowerShell: Copy-Item .env.example .env)

# Run
python agent.py "competitive landscape for meal-kit delivery in India"
```

Outputs land in `outputs/<slugified-brief>/`:

```
outputs/competitive-landscape-for-meal-kit-delivery-in-india/
├── meal-kit-india-deck.pptx          # the deck
├── meal-kit-india-data-appendix.xlsx # data appendix, sources per row
└── run_metrics.json                  # duration, tokens, cost
```

### Example `run_metrics.json`

```json
{
  "brief": "competitive landscape for meal-kit delivery in India",
  "model": "claude-fable-5",
  "wall_clock_seconds": 1043.2,
  "api_turns": 4,
  "tokens": { "input": 41230, "output": 28114, "cache_read": 96400, "cache_write": 2210 },
  "estimated_cost_usd": 1.93,
  "files": ["meal-kit-india-deck.pptx", "meal-kit-india-data-appendix.xlsx"]
}
```

## What a run costs

A typical brief costs **$1.50–$4.00** in API usage (Fable 5: $10/M input, $50/M output tokens) and takes 10–25 minutes depending on research depth. Compare to the manual baseline: ~8–16 analyst-hours for an equivalent first-draft deliverable.

## Evaluating output quality

For a rigorous comparison, use [`docs/case_study_template.md`](docs/case_study_template.md): run the agent on 3–5 briefs, have reviewers blind-rate the decks against human-made equivalents on accuracy, structure, and insight quality, and report the results. The template structures the full case study (problem → process → design → metrics → limitations).

## Repository structure

```
agent.py                       # orchestration: agent loop, streaming, file download, metrics
prompts.py                     # the deliverable "spec" — deck structure, quality bar, citation rules
requirements.txt
.env.example
docs/case_study_template.md    # write-up template for quality evaluation
outputs/                       # generated deliverables (gitignored)
```

## Honest limitations

- Source quality is whatever live web search surfaces — paywalled industry reports are out of reach, so market-sizing numbers should be treated as directional.
- The model cites its sources, but citation ≠ verification; spot-check load-bearing numbers before client use.
- Deck visual design is functional, not branded. A template/theming pass is the natural next feature.

## License

MIT
