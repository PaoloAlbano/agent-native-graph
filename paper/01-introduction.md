# 1. Introduction

`ANA-PAPER-INTRODUCTION`

Formal query languages were designed to let humans describe data access
precisely. Cypher, SQL, and SPARQL are successful because they compress
complex data operations into compact, readable syntax for trained operators.

LLM agents are different users. They can write formal language, but they are also
good at iterative exploration: inspect, try, summarize, repair, combine, and
verify. This raises the central question of this project:

**Should data systems expose only human-native query languages to agents, or
should they expose agent-native APIs designed for how agents actually operate?**

We investigate this question in knowledge graph question answering, where the
gap is especially visible. A text-to-Cypher system must infer graph schema,
relationship direction, entity names, optional semantics, grouping, and return
shape before executing anything. ANA makes those steps explicit and
composable.

The broader goal, however, is not limited to graphs. The same design question
appears whenever agents are asked to use interfaces originally designed for
humans: SQL over relational databases, SPARQL over RDF stores, command-line
interfaces, SDKs, or programming languages. ANA frames these not as fixed
interfaces that agents must adapt to, but as design spaces where we can build
agent-facing operations that improve reliability, inspectability, and task
performance.

The core claim is not that Cypher should disappear. Humans should keep
human-friendly query languages. ANA instead argues that agent-facing interfaces
deserve their own design principles.
