# 12. Conclusion

LLM agents do not need to be limited to interfaces designed primarily for human
operators. Formal query languages remain valuable, but agent-facing systems can
expose different affordances: discovery, handles, bounded traversal, set
composition, aggregation, pagination, and inspection.

Agent-Native APIs are a proposal for that interface layer. On the Company case
study, nine ANA runs obtain 78.7%-87.0% exact-result match over 347 questions.
On the pinned 100-question comparison, ANA has more exact matches than the
corresponding saved-query baselines under a shared comparator. Those results
motivate further experiments, not a causal or cross-domain superiority claim.

The implementation provides inspectable state transitions without embedding an
LLM in the graph-access service. Safety, efficiency and transfer require their
own evaluation. The next research step is a frozen treatment, controlled
baseline generations and replication, rather than further tuning to the same
observed test failures.

The broader claim is simple: as agents become first-class users of software
systems, API design should evolve from merely exposing functions to designing
operations that agents can reliably reason with.
