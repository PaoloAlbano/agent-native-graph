# 9. Discussion

`ANA-PAPER-DISCUSSION`

ANA changes the interface question. Instead of asking only whether an LLM can
generate Cypher, it asks whether the data system can expose operations that make
the agent's job easier, safer, and more inspectable.

The observations make this a useful interface-design question, not an answer
that generalizes to every system. Generated queries are compact and inspectable
by database tools; agentic query pipelines can also expose feedback and repair
steps. ANA additionally makes intermediate graph operations and state shapes
part of the public contract. Its trace is longer, but exposes handles, counts
and decision points that can be examined independently of final prose.

The tradeoff is real. Too many tools can confuse models. Too powerful a tool can
become query generation under another name. Too narrow a tool can overfit to one
dataset. The design target is generic composability with bounded execution.

The API is itself an inductive bias. Operators such as role intersection or
optional counting encode reusable database knowledge that a text-to-Cypher
model might otherwise reconstruct. A fair interpretation includes the human
engineering invested in those operators; it does not attribute all observed
differences to intrinsic model reasoning. Controlled ablations are needed to
separate granularity, descriptions, intermediate state and compute budget.

No embedded LLM is necessary in the data service: a caller can use the same
backend from Python or the demo HTTP interface. That separation makes future
adapters possible without making this a production-system evaluation. Extending
the method to SQL or technical workflows remains an empirical question.
