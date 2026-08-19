# 7. Results

`ANA-PAPER-RESULTS`

Representative first-100 CypherBench company results are currently summarized in
[`../docs/cypherbench-company-results.md`](../docs/cypherbench-company-results.md).

## Main Comparison Table

The paper-ready comparison table will be filled after rerunning all approaches
with the same code revision, task subset, graph snapshot, models, and evaluator.

| Approach | Model | Profile | Tasks | Correct | Accuracy | Technical success | Avg LLM calls | Avg tool calls |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Gold Cypher execution | TBD | n/a | TBD | TBD | TBD | TBD | n/a | n/a |
| Direct text-to-Cypher | TBD | temp 0 | TBD | TBD | TBD | TBD | TBD | n/a |
| Multi-agent text-to-Cypher | TBD | temp 0 | TBD | TBD | TBD | TBD | TBD | n/a |
| Multi-Agent GraphRAG-style text-to-Cypher | TBD | temp 0 | TBD | TBD | TBD | TBD | TBD | n/a |
| ANA tool calls | TBD | temp 0 | TBD | TBD | TBD | TBD | TBD | TBD |
| ANA tool calls | TBD | temp 1 + reasoning medium | TBD | TBD | TBD | TBD | TBD | TBD |

At the time of this draft, agent-native runs cluster around the high 80s to
roughly 90/100 correct answers on the first 100 examples, depending on model and
reasoning profile.

These numbers should be treated as research evidence, not final claims. The next
paper-ready step is to consolidate comparable baseline tables from the external
run repository and ensure every approach is evaluated with the same task subset,
model profile, and scoring script.
