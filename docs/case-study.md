# Case Study: Automating the Brief-to-Deliverable Workflow

*Piyush Jain Sanjay — June 2026. Code: [brief-to-deck-agent](https://github.com/paramouxt/brief-to-deck-agent)*

> Status: living document. Sections marked **[TODO]** are pending additional
> runs and external review — kept visible deliberately rather than removed,
> because the evaluation plan is part of the work.

## 1. The problem

Consulting and market-intelligence teams burn junior-analyst hours on a highly
repeatable workflow: take a one-line brief ("competitive landscape for X in
market Y"), research it, synthesize the findings, and produce a sourced deck
plus a data appendix. The structure of the output barely changes between
briefs; only the content does. That combination — repeatable structure, clear
quality bar, expensive labor — makes it a prime automation candidate.

I work with companies in India's two-wheeler spare parts aftermarket, where
the highest-margin play is selling own-branded (private label) parts. Landscape
research like this is exactly what I'd want before pitching a private-label
program to a distributor — so I used my own domain as the test brief, which
also lets me judge output quality credibly rather than guessing.

**Manual cost today:** an equivalent first-draft deliverable takes roughly
**[TODO: confirm from my own experience — initial estimate 8–16 analyst-hours]**
covering research, synthesis, chart building, and deck writing.

## 2. The manual process, mapped

| Step | Manual approach | Est. time |
|---|---|---|
| Scoping the brief | Clarify the question, decide deck structure | 0.5–1 h |
| Source gathering | Search reports, news, trade-association data | 2–4 h |
| Reading & synthesis | Read sources, reconcile conflicting figures | 2–4 h |
| Data tables & charts | Build comparison tables, size the market, chart it | 1.5–3 h |
| Deck writing | Storyline, headlines, slide copy | 2–3 h |
| QA & citation check | Verify numbers trace to sources | 0.5–1 h |
| **Total** | | **~8–16 h** |

*(Estimates mine, from working alongside this kind of research in the spares
business. [TODO: validate with one timed manual run or a colleague's estimate.])*

## 3. The automation design

One Python script orchestrates a fully autonomous loop on the Claude API:
a brief goes in; web research, analysis, chart generation, and document
building all happen inside Anthropic's server-side tool environment; a
`.pptx` deck, `.xlsx` appendix, and a `run_metrics.json` come out. (See the
[README](../README.md) for the architecture diagram.)

Design decisions that mattered:

- **Cost-aware model routing.** A cheap classifier call (Claude Haiku,
  fractions of a cent) grades each brief as standard / complex / frontier and
  routes it to the cheapest model that holds the quality bar — Sonnet 4.6
  ($3/$15 per MTok) up to Fable 5 ($10/$50) only when reasoning depth is the
  binding constraint. The routing verdict and rationale are logged with every
  run, so each deliverable documents why it cost what it did.
- **The quality bar lives in the prompt, not the code.** Deck structure,
  citation rules, and the "every number traceable to a source" requirement are
  a product spec in `prompts.py`. Iterating on output quality means editing a
  spec, not refactoring a pipeline.
- **Two work modes, measurable against each other.** Default "team mode"
  structures the work as a virtual pod of specialist roles (research lead,
  source verifier, analyst, deck architect, QA reviewer) inside one model
  loop; "direct mode" is a single-consultant baseline. Both log identical
  metrics, so the quality-vs-cost tradeoff is testable, not asserted.
- **Fully autonomous, with verification left manual by design.** No
  human-in-the-loop checkpoints mid-run — the value is unattended turnaround.
  The deliberate exception: load-bearing numbers should be spot-checked by a
  human before client use, and the agent is instructed to flag what to
  double-check in its closing summary.

## 4. Results

### Demo run (executed 2026-06-09)

Brief: *"India two-wheeler spare parts aftermarket: competitive landscape and
private-label (own-brand) opportunity for parts distributors."*

| Metric | Result | Manual baseline |
|---|---|---|
| Wall-clock time | **5.0 minutes** | ~8–16 hours |
| Deliverables | 12-slide deck + 6-sheet Excel appendix | same scope |
| Research performed | 7 web searches, full-text fetch, source triangulation | 2–4 h equivalent |
| Charts | 3 (market sizing, counterfeit share, demand segments) | manual Excel work |
| Citations | every figure sourced; conflicting estimates shown as ranges | often skipped under time pressure |

*Transparency note: this run was executed via a Claude Code session on the
same model (Claude Fable 5) and the same workflow as the pipeline, rather
than through the standalone API script — marginal cost $0 on subscription.
Pipeline runs are estimated at $0.50–$4.00 depending on the routed tier.*

### Pipeline runs **[TODO: 3–5 briefs through `agent.py` once API credits are set up]**

| Brief | Mode | Model routed | Time | Cost | Slides | Sources |
|---|---|---|---|---|---|---|
| | | | | | | |

### Team mode vs. direct mode **[TODO: same brief, both modes]**

| Mode | Time | Cost | Reviewer quality score |
|---|---|---|---|
| `--agent-mode team` | | | |
| `--agent-mode direct` | | | |

Hypothesis: team mode buys measurably better source verification and storyline
at 20–40% higher output-token cost. Worth it for client-facing work; direct
mode wins for internal quick-looks.

### Quality evaluation **[TODO: 2–3 blind reviewers from the spares business, 1–5 scale]**

| Criterion | Agent avg | Human baseline avg |
|---|---|---|
| Factual accuracy (spot-checked) | | |
| Structure & storyline | | |
| Insight quality (non-generic) | | |
| Citation completeness | | |

### Headline (demo run, conservative)

- **Time: ~5 minutes vs. 8–16 analyst-hours — a ~99% reduction** (pipeline
  runs take 10–25 minutes; still ≥97%).
- **Cost: under $4 of API spend vs. hundreds of dollars of analyst time.**
- Quality: pending blind review — but the deliverable was credible enough to
  judge against my own industry knowledge, including correctly surfacing the
  counterfeit-parts problem and the organized-vs-unorganized channel split
  that drive the private-label thesis.

## 5. Limitations and failure modes observed

Observed in the demo run — kept here because knowing where it breaks is the
useful part:

- **Stale authoritative data gets cited confidently.** The most-quoted
  counterfeit-parts figures (ACMA's 30–40% share estimates) date from
  2014–2016. The agent used them — correctly flagged as directional, but a
  careless reader would treat them as current. Mitigation already in the spec:
  publication dates required per source; the closing summary names what to
  double-check.
- **Market sizing conflicts across research vendors.** IMARC, Markets & Data,
  and ACMA-derived figures for "the same" market differ by definition
  (components vs. services, aftermarket vs. OEM channel). The agent handled
  this the right way — showing ranges and saying so — but only because the
  prompt demands it; earlier prompt drafts produced a single confident number.
- **Paywalled reports cap research depth.** The best data (Ken Research,
  ResearchAndMarkets) sits behind paywalls; the agent works from abstracts and
  press releases. A production version would integrate licensed data sources.
- **Brief sensitivity.** Vague briefs produce generic decks. The workflow
  rewards a well-specified brief — same as a human analyst.

## 6. What I would do to take this to production

- **Quality gates:** an automated citation-checker pass (regex the deck for
  numbers, verify each maps to the sources sheet) and a second-model review
  pass before delivery — the QA-reviewer role in team mode is the seed of this.
- **Human-in-the-loop where it pays:** a 10-minute human review of the five
  load-bearing numbers beats re-reading everything; the agent's "double-check
  this" summary is designed to make that review fast.
- **Scale economics:** batch API for non-urgent briefs (50% cost reduction),
  prompt caching across runs sharing a domain, and a per-100-decks cost model.
- **Productization:** the user is a consulting team lead or a distributor's
  strategy function; pricing logic is per-deliverable (anchored against
  analyst-hours, not tokens); the first adoption blocker to attack is trust —
  which is why every run ships with its metrics, sources, and stated caveats
  attached.
