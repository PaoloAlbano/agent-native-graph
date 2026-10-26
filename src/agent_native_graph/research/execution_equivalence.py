"""Compare query results using CypherBench-style execution semantics."""

import json
from collections import Counter
from itertools import permutations
from typing import Any


def _value(value: Any) -> str:
    if isinstance(value, list):
        # CypherBench treats list-valued cells as unordered for execution matching.
        value = sorted(_value(item) for item in value)
    elif isinstance(value, dict):
        value = {key: _value(item) for key, item in sorted(value.items())}
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def execution_equivalent(
    predicted: list[list[Any]], gold: list[list[Any]], *, order_matters: bool
) -> bool:
    """Match row bags with a consistent column permutation; preserve ordered rows."""
    if len(predicted) != len(gold):
        return False
    if not gold:
        return True
    width = len(gold[0])
    if any(len(row) != width for row in [*gold, *predicted]):
        return False
    expected = [tuple(_value(cell) for cell in row) for row in gold]
    actual = [tuple(_value(cell) for cell in row) for row in predicted]
    for column_order in permutations(range(width)):
        aligned = [tuple(row[index] for index in column_order) for row in actual]
        matches = aligned == expected if order_matters else Counter(aligned) == Counter(expected)
        if matches:
            return True
    return False
