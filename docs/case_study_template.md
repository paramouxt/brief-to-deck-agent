# Case Study: Automating the Brief-to-Deliverable Workflow

> Fill this in after running the agent on 3–5 real briefs. This write-up is the
> artifact consulting and PM interviewers will actually read — link it from
> your resume alongside the repo.

## 1. The problem

- What workflow is being automated? (brief → research → analysis → deck)
- Who does this work today, and what does it cost? (analyst-hours per
  deliverable, fully-loaded hourly cost)
- Why is it a good automation candidate? (repeatable structure, clear quality
  bar, high volume)

## 2. The manual process, mapped

| Step | Manual approach | Time |
|---|---|---|
| Scoping the brief | | |
| Source gathering | | |
| Reading & synthesis | | |
| Data tables & charts | | |
| Deck writing | | |
| QA & citation check | | |
| **Total** | | **~X hours** |

## 3. The automation design

- Architecture summary (one paragraph + reference the README diagram)
- Key design decisions and why:
  - Why a fully autonomous loop instead of human-in-the-loop checkpoints?
  - Why the quality bar lives in the prompt (the "product spec") rather than code
  - What was deliberately left manual (final verification of load-bearing numbers)

## 4. Results

Run the agent on 3–5 briefs and record from each `run_metrics.json`:

| Brief | Time | Cost | Slides | Sources cited |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |

**Quality evaluation** — have 2–3 reviewers blind-rate agent decks vs. a human
baseline (1–5 scale):

| Criterion | Agent avg | Human avg |
|---|---|---|
| Factual accuracy (spot-checked) | | |
| Structure & storyline | | |
| Insight quality (non-generic) | | |
| Citation completeness | | |

**Headline numbers:**

- Time per deliverable: __ minutes vs. ~__ analyst-hours (≈ __% reduction)
- Cost per deliverable: $__ API spend vs. ~$__ analyst cost
- Quality: __ / 5 vs. __ / 5 human baseline

## 5. Limitations and failure modes observed

- Where did the agent get numbers wrong or cite weak sources?
- What kinds of briefs does it handle poorly?
- What did you change in the prompt to fix recurring issues? (this section
  demonstrates iteration — interviewers care about it more than the wins)

## 6. What I would do to take this to production

- Quality gates: automated citation checking, a second-model review pass
- Human-in-the-loop: where a reviewer adds the most value per minute spent
- Scale economics: batch processing, caching strategy, cost per 100 decks
- Productization: who the user is, pricing logic, and the adoption blocker
  you'd tackle first
