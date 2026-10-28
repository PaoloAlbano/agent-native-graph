# Appendix A. Recorded Worked Examples

`ANA-PAPER-WORKED-EXAMPLES`

These examples illustrate the measured interface, not newly generated ideal
plans. Both come from Q28-0M: Qwen3.5-27B, temperature 0, requested medium
thinking, native tools, `auto`, 16,000 output tokens and a 12-step budget.
The [source manifest](../results/cypherbench-company/full/runs/2026-10-28_qwen-qwen3.5-27b_temp0_reasoning-medium_tools-native_n347_2026-10-28t10-49-03.059153-00-00/manifest.json)
and adjacent `run.jsonl` retain complete responses. The
[evaluation manifest](../results/cypherbench-company/query-reexecution/2026-10-28-qwen-matrix/manifest.json)
pins both external baseline traces, their commit and re-executed rows.

## Selection Rule And Presentation

Within Q28-0M, restrict to the pinned 100 QIDs, exclude the known non-reproduced
gold case, require at most six recorded steps, one to five expected rows and
zero recorded tool errors. Sort by QID and select the first correct case and
the first executed `semantic_mismatch` case. Baseline outcomes do not enter
selection. The examples are chosen for legibility, not representativeness or
an ANA advantage. In fact both baseline queries succeed in both examples.

Every recorded tool call and its complete argument dictionary is reproduced.
`result_excerpt` contains literal selected fields from the response; large
schema details, alternative entity candidates and prose hints are omitted.
The excerpts are not the complete payloads sent to the agent. Handle names
are the historical workflow-local identifiers, not reusable live server tokens.
The expected and final rows below are complete for these small answers.
No raw reasoning text was archived; the explanations are analyst commentary.

## A.1 Correct Constraints, With A Redundant Grounding Step

QID: `01fa1a43-2752-42bd-8e99-720b4e8204cf`.

**Question:** What are the names of companies that have Makoto Uchida as their
CEO and are parent of Nissan New Zealand?

**Golden query, as archived:**

```cypher
MATCH (n:Company)-[r0:hasCEO]->(m0:Person {name: 'Makoto Uchida'}),(n:Company)<-[r1:subsidiaryOf]-(m1:Company {name: 'Nissan New Zealand'}) WITH DISTINCT n RETURN n.name
```

**Recorded ANA trajectory:**

```json
{
  "observation": "Q28-0M",
  "qid": "01fa1a43-2752-42bd-8e99-720b4e8204cf",
  "expected": [["Nissan Motor Co. Ltd."]],
  "rows": [["Nissan Motor Co. Ltd."]],
  "ok": true,
  "matches_answer_json": true,
  "calls": [
    {
      "action": {"tool": "schema_overview", "args": {}},
      "result_excerpt": {
        "labels": [{"label": "Company"}, {"label": "Country"}, {"label": "Industry"}, {"label": "Person"}]
      }
    },
    {
      "action": {
        "tool": "entity_resolve",
        "args": {"as": "person", "label": "Person", "limit": 5, "text": "Makoto Uchida"}
      },
      "result_excerpt": {
        "handle": "h1", "kind": "rows", "entity_variables": ["person"],
        "matched_count": 1, "preview": ["Makoto Uchida"]
      }
    },
    {
      "action": {
        "tool": "constraint_query",
        "args": {
          "find": {"as": "company", "label": "Company"},
          "return_mode": "names",
          "return_property": "name",
          "where": [
            {"direction": "out", "op": "eq", "property": "name", "relationship_type": "hasCEO", "target_label": "Person", "value": "Makoto Uchida"},
            {"direction": "in", "op": "eq", "property": "name", "relationship_type": "subsidiaryOf", "target_label": "Company", "value": "Nissan New Zealand"}
          ]
        }
      },
      "result_excerpt": {
        "handle": "h2", "kind": "table", "columns": ["name"], "entity_variables": [],
        "matched_count": 1, "preview": [{"name": "Nissan Motor Co. Ltd."}]
      }
    },
    {
      "action": {"tool": "fetch", "args": {"from": "h2"}},
      "result_excerpt": {
        "columns": ["name"], "rows": [["Nissan Motor Co. Ltd."]],
        "returned_count": 1, "next_offset": null, "truncated": false
      }
    }
  ]
}
```

The two relationship constraints select the same company. The directions matter:
the company points to its CEO, while a subsidiary points to its parent. `h2` is
a scalar table, then fetched as the answer. `h1` is not consumed by
`constraint_query`: the model restates the name instead. This successful trace
therefore does not demonstrate a minimal plan or reuse of every grounded handle.
It contains four LLM calls and four tool calls.

**Saved baseline query:** the direct and multi-agent final query strings are
identical for this question, so the shared string is shown once:

```cypher
MATCH (ceo:Person {name: "Makoto Uchida"})
MATCH (company:Company)-[:hasCEO]->(ceo)
MATCH (nissan:Company {name: "Nissan New Zealand"})-[:subsidiaryOf]->(company)
RETURN company.name
```

Each re-execution returns `[["Nissan Motor Co. Ltd."]]` and matches the expected
answer. The example shows two ways of expressing the same retrieval, not a
case where only ANA can answer. It does not imply either baseline used one LLM
call; only its final query and retrieved rows are shown here.

## A.2 Correct Person, Incompatible Result Shape

QID: `1b64800c-e1b6-4227-8319-d80288b85362`.

**Question:** Who are the individuals who both founded Global Market Insite
and have served as its CEO, and what are their countries of citizenship?

**Golden query, as archived:**

```cypher
MATCH (n:Person)<-[r0:foundedBy]-(m0:Company {name: 'Global Market Insite'}),(n:Person)<-[r1:hasCEO]-(m1:Company {name: 'Global Market Insite'}) WITH DISTINCT n RETURN n.name, n.country_of_citizenship
```

**Recorded ANA trajectory:**

```json
{
  "observation": "Q28-0M",
  "qid": "1b64800c-e1b6-4227-8319-d80288b85362",
  "expected": [["Rob Monster", ["Kingdom of the Netherlands", "United States of America"]]],
  "rows": [["Rob Monster", "Kingdom of the Netherlands"], ["Rob Monster", "United States of America"]],
  "ok": true,
  "matches_answer_json": false,
  "calls": [
    {
      "action": {"tool": "schema_overview", "args": {}},
      "result_excerpt": {
        "labels": [{"label": "Company"}, {"label": "Country"}, {"label": "Industry"}, {"label": "Person"}]
      }
    },
    {
      "action": {
        "tool": "same_target_role_intersection",
        "args": {
          "filters": [{"op": "eq", "property": "name", "value": "Global Market Insite", "var": "company"}],
          "keep_entities": false,
          "relationships": [
            {"direction": "in", "relationship_type": "foundedBy"},
            {"direction": "in", "relationship_type": "hasCEO"}
          ],
          "select": [
            {"alias": "name", "property": "name", "var": "person"},
            {"alias": "country_of_citizenship", "explode": true, "property": "country_of_citizenship", "var": "person"}
          ],
          "source_label": "Person",
          "target_label": "Company"
        }
      },
      "result_excerpt": {
        "handle": "h1", "kind": "table", "columns": ["name", "country_of_citizenship"],
        "entity_variables": [], "matched_count": 2,
        "preview": [
          {"country_of_citizenship": "Kingdom of the Netherlands", "name": "Rob Monster"},
          {"country_of_citizenship": "United States of America", "name": "Rob Monster"}
        ]
      }
    },
    {
      "action": {"tool": "fetch", "args": {"from": "h1"}},
      "result_excerpt": {
        "columns": ["name", "country_of_citizenship"],
        "rows": [["Rob Monster", "Kingdom of the Netherlands"], ["Rob Monster", "United States of America"]],
        "returned_count": 2, "next_offset": null, "truncated": false
      }
    }
  ]
}
```

The model requests `explode=true` for a list-valued property. The result contains
the expected person and both expected citizenship values, but as two rows rather
than one row containing a list. The recorded exact comparator rejects that
shape. All three operations execute successfully; this is neither an unknown
person nor an invalid tool call. It is evidence of representation sensitivity,
not proof that the retrieved facts are false or the backend malfunctioned.

**Saved baseline query:** again both final baseline query strings coincide:

```cypher
MATCH (c:Company {name: "Global Market Insite"})
MATCH (c)-[:foundedBy]->(p:Person)
MATCH (c)-[:hasCEO]->(p:Person)
RETURN p.name, p.country_of_citizenship
```

Both re-executions preserve the list-valued property and return the complete
expected one-row answer. ANA makes three LLM calls and three tool calls. A
different, explicitly defined answer-equivalence policy might accept the
flattened facts; that is not the recorded comparator and no score is changed.

## What These Cases Do And Do Not Establish

The first trace exposes useful constraint composition but also redundant
grounding. The second exposes the model's shape choice and the evaluator's
representation contract. They motivate studying handle reuse and list/row
semantics with generic contracts and controlled ablations, not adding a tool
specific to either company or retrospectively changing the benchmark metric.
Neither example establishes a population-level error rate or causal advantage.
