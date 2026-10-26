# Gold Query Validation

Executed all 347 Company `gold_cypher` queries against Neo4j 2026.05.0 after
loading `company_simplekg.json` (SHA-256
`54d15b5db4c30b9d7d0e31cbc30ca7c144d3e2cad30bddf8d92390a095f0b82b`).
All queries executed; 345 reproduced CypherBench `answer_json` exactly.
Per-question status is in `gold-validation.jsonl`.

Two questions do not have a reproducible answer from the loaded graph:

| QID | Question | Gold answer | Current query result |
|---|---|---|---|
| `8536d1ef-cb04-4bc6-8f9a-4aff1279dc0f` | Youngest board member | Wayne J. Riley | Gustaf Schlieper |
| `44840930-74b3-491e-a497-4042e8e4fd74` | Youngest person who was CEO and board member of the same company | Alfred F. Kelly Jr. | Brian Cornell |

Both gold queries use `ORDER BY n.date_of_birth DESC LIMIT 1`. The expected and
returned people in these cases have no `date_of_birth` property in the loaded
graph. Ordering among tied null values does not identify a unique youngest
person. Report benchmark accuracy both on all 347 tasks and on the 345 tasks
whose gold queries reproduce `answer_json`; do not silently remove the two.
