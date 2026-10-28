# 10. Limitations

`ANA-PAPER-LIMITATIONS`

## Development Exposure And Generalization

Tool design was iterated with Company questions and outcomes, including test
examples. The reported split is therefore not an untouched held-out validation
of a frozen API. Generic operator names and the absence of question-ID routing
do not remove development exposure; some descriptions retain Company-flavored
examples. No cross-domain, unseen-schema, SQL or programming-workflow result
is reported. Only two served model identifiers and one graph are studied.

## Comparative Validity

Common QIDs, a verified re-execution graph and an exact comparator improve
comparability, but do not reconstruct the historical baseline generation graph
or align prompts, context, retries, token budgets and model revisions. The
baseline implementation is independent of the cited paper's experiment. We
score saved query rows, not its final natural-language answer. Its original
judge scores are not interchangeable with these results.

We have not compared ANA experimentally with StructGPT, ToG or an
AgentBench-inspired minimal graph API. Their related-work discussion is not
evidence of superior performance over other interface-based approaches.

Historical ANA provenance is incomplete. Most profiles have one observation;
the repeated GPT-OSS T0/none runs are not a controlled replication. We report no
statistical significance or causal effect estimate. The same questions and
baseline runs recur across tables; their rows are not independent replications.

## Measurement And Engineering Limits

Exact-result scoring ignores row order, preserves columns and duplicates, and
retains two full-split gold discrepancies. It does not capture every notion
of semantic equivalence. Failed response bodies, raw reasoning text, served
model revision and some external call counts are unavailable. We therefore
cannot make complete token-cost, reasoning-content or efficiency comparisons.

The backend currently targets Neo4j. Broad pattern tools remain experimental,
and bounded output does not imply bounded query cost. Schema discovery may be
expensive; memory quotas and multi-worker session sharing are not implemented.
Demo API keys, session isolation and read-only metadata are not graph-level
tenant authorization or a production-security audit. No claim of safe public
deployment follows from benchmark accuracy or container smoke tests.
