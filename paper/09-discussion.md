# 9. Discussion

`ANA-PAPER-DISCUSSION`

ANA changes the interface question. Instead of asking only whether an LLM can
generate Cypher, it asks whether the data system can expose operations that make
the agent's job easier, safer, and more inspectable.

This matters for production systems. A generated query is compact but opaque:
once it is wrong, the system must debug the whole artifact. A tool trajectory is
longer, but it exposes intermediate state, counts, handles, pagination, and
decision points.

The tradeoff is real. Too many tools can confuse models. Too powerful a tool can
become query generation under another name. Too narrow a tool can overfit to one
dataset. The design target is generic composability with bounded execution.
