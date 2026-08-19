# 10. Limitations

`ANA-PAPER-LIMITATIONS`

Current limitations:

- experiments are concentrated on the CypherBench `company` slice;
- the wrapper currently targets Neo4j;
- the service shape is experimental;
- several broad tools remain marked experimental;
- schema discovery for very large graphs needs stronger paging and targeting;
- results are not yet consolidated against all external baselines;
- tool trajectories can use more calls than direct text-to-Cypher.

The key validity risk is overfitting tool design to benchmark questions. The
project intentionally avoids dataset-specific vertical tools, but continued
evaluation on additional graph datasets is required.
