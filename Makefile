.PHONY: help sync install-mcp format lint test test-backend test-quality test-interfaces prepare-company-tasks load-company export-schema benchmark benchmark-full benchmark-temp1 evaluate archive-result baseline-check baseline-run baseline-archive compare-results list-tools paper docs-build docs-serve serve serve-mcp docker-build docker-run clean

NEO4J_URI ?= bolt://127.0.0.1:7687
NEO4J_USER ?= neo4j
NEO4J_PASSWORD ?= password
BASE_URL ?= https://openrouter.ai/api/
MODEL ?= openai/gpt-oss-120b
API_KEY_FILE ?= /tmp/grapharrow-agent-key
export BASE_URL NEO4J_URI NEO4J_USER NEO4J_PASSWORD API_KEY_FILE

TASKS ?= data/tasks_company_test.jsonl
SCHEMA_JSON ?= data/company_schema.json
SCHEMA_PROMPT ?= data/company_schema_prompt.txt
GRAPH ?= downloads/company_simplekg.json
RUN_DIR ?= /tmp/agent-native-graph-runs
OUT ?=
BENCHMARK ?= cypherbench-company
LIMIT ?= 347
FULL_LIMIT ?= 347
TEMPERATURE ?= 0
REASONING ?= none
THINKING ?= 0
THINKING_EFFORT ?= medium
MAX_TOKENS ?= 16000
MAX_STEPS ?= 12
CONCURRENCY ?= 3
RESUME ?= 0
BATCH_SIZE ?= 2000
DOCKER_IMAGE ?= agent-native-graph
REFERENCE_REPO ?= ../multigraphrag
REEXECUTION_OUT ?= $(RUN_DIR)/query-reexecution
REFERENCE_PYTHON ?= $(REFERENCE_REPO)/.venv/bin/python
BASELINE_MODE ?= direct
BASELINE_OUT ?= $(RUN_DIR)/baseline_$(BASELINE_MODE)_$(subst /,_,$(MODEL))_temp$(TEMPERATURE)_reasoning_$(REASONING)_n$(FULL_LIMIT).jsonl
COMPARISON_OUT ?= $(RUN_DIR)/comparison/cypherbench-company.md
DOCS_PORT ?= 8000
DOCS_OUT ?= build/site
PROFILE ?= temp0-none
PROVIDER_TAG ?= openai-compatible
CHECK_ONLY ?= 0

help:
	@echo "Agent-Native Graph targets"
	@echo ""
	@echo "  make sync             Alias for make install"
	@echo "  make install          Install uv dependencies with dev and service extras"
	@echo "  make format           Format Python code with ruff"
	@echo "  make lint             Check Python code with ruff"
	@echo "  make test             Run all current unit tests"
	@echo "  make prepare-company-tasks  Build data/tasks_company_test.jsonl from CypherBench"
	@echo "  make load-company     Clear/load the CypherBench company graph into Neo4j"
	@echo "  make export-schema    Export the loaded Company graph schema for benchmarking"
	@echo "  make benchmark        Run ANA benchmark with configurable model/profile"
	@echo "  make benchmark-full   Run ANA benchmark on the full company split"
	@echo "  make benchmark-temp1  Run temp=1 + thinking medium ANA benchmark"
	@echo "  make evaluate         Evaluate OUT with deterministic answer_json scoring"
	@echo "  make archive-result OUT=...  Validate/archive using saved run metadata"
	@echo "  make baseline-check   Verify reference tasks, graph and Neo4j without LLM calls"
	@echo "  make baseline-run     Run direct/single/agentic reference mode on Company"
	@echo "  make baseline-archive Archive a complete reference run in .local-results/"
	@echo "  make compare-results  Diagnose matched ANA, direct and agentic runs locally"
	@echo "  make reexecute-reference  Re-score pinned baseline queries without LLM calls"
	@echo "  make list-tools       Print the ANA tool catalog"
	@echo "  make paper            Print the paper/preprint table of contents"
	@echo "  make docs-build       Generate the research website and tool reference"
	@echo "  make docs-serve       Build and preview the website on localhost:$(DOCS_PORT)"
	@echo "  make serve            Run the experimental HTTP service"
	@echo "  make serve-mcp        Run the experimental MCP service"
	@echo "  make docker-build     Build service image"
	@echo "  make docker-run       Run service image"
	@echo ""
	@echo "Common overrides:"
	@echo "  MODEL=$(MODEL)"
	@echo "  LIMIT=$(LIMIT)"
	@echo "  PROFILE=$(PROFILE) (YAML name from src/agent_native_graph/profiles/)"
	@echo "  CONCURRENCY=$(CONCURRENCY)"
	@echo "  RUN_DIR=$(RUN_DIR)"
	@echo "  OUT=$(OUT)"

install:
	@uv sync --locked --extra dev --extra service

sync: install

install-mcp:
	@uv sync --locked --extra dev --extra service --extra mcp

format:
	@uv run ruff format src/agent_native_graph tests

lint:
	@uv run ruff check src/agent_native_graph tests

test:
	@uv run pytest tests -q

test-backend:
	@ANA_TEST_NEO4J=1 uv run pytest tests/test_agent_tool_backend.py -q

test-quality:
	@uv run pytest tests/test_tool_quality_analysis.py -q

test-interfaces:
	@uv run pytest tests/test_mcp_interface.py -q

prepare-company-tasks:
	@uv run --with datasets --with pandas --with pyarrow agent-native-graph prepare-company-tasks \
	  --from-hf \
	  --graph company \
	  --split test \
	  --out "$(TASKS)"

load-company:
	@uv run agent-native-graph load-company \
	  --neo4j-uri "$(NEO4J_URI)" \
	  --neo4j-user "$(NEO4J_USER)" \
	  --neo4j-password "$(NEO4J_PASSWORD)" \
	  --graph "$(GRAPH)" \
	  --clear \
	  --batch-size "$(BATCH_SIZE)"

export-schema:
	@uv run agent-native-graph export-schema \
	  --neo4j-uri "$(NEO4J_URI)" \
	  --neo4j-user "$(NEO4J_USER)" \
	  --neo4j-password "$(NEO4J_PASSWORD)" \
	  --out "$(SCHEMA_PROMPT)" \
	  --json-out "$(SCHEMA_JSON)"

benchmark:
	@if [ "$(origin TEMPERATURE)" = "command line" ] || [ "$(origin THINKING)" = "command line" ] || [ "$(origin REASONING)" = "command line" ]; then \
	  echo "Use PROFILE=<YAML name> for ANA benchmarks; custom settings use the direct CLI."; exit 1; fi
	@uv run agent-native-graph benchmark-neo4j \
	  --model "$(MODEL)" \
	  --profile "$(PROFILE)" --provider-tag "$(PROVIDER_TAG)" \
	  --tasks "$(TASKS)" \
	  --schema-json "$(SCHEMA_JSON)" \
	  --graph-file "$(GRAPH)" --run-dir "$(RUN_DIR)" \
	  $(if $(OUT),--out "$(OUT)",) \
	  --limit "$(LIMIT)" \
	  --concurrency "$(CONCURRENCY)" \
	  $(if $(filter 1,$(RESUME)),--resume,) \
	  $(if $(filter 1,$(CHECK_ONLY)),--check-only,)

benchmark-full:
	@$(MAKE) benchmark LIMIT="$(FULL_LIMIT)"

benchmark-temp1:
	@$(MAKE) benchmark PROFILE=temp1-medium

evaluate:
	@test -n "$(OUT)" || (echo "Set OUT to the run.jsonl path printed by the benchmark" && exit 1)
	@uv run agent-native-graph evaluate-run --run "$(OUT)"

archive-result:
	@test -n "$(OUT)" || (echo "Set OUT to the run.jsonl path printed by the benchmark" && exit 1)
	@uv run agent-native-graph archive-result --run "$(OUT)"

baseline-check:
	@PYTHONPATH=src $(REFERENCE_PYTHON) -m agent_native_graph.interfaces.cli baseline-run \
	  --reference-repo "$(REFERENCE_REPO)" --mode "$(BASELINE_MODE)" \
	  --out "$(BASELINE_OUT)" --check-only

baseline-run:
	@PYTHONPATH=src $(REFERENCE_PYTHON) -m agent_native_graph.interfaces.cli baseline-run \
	  --reference-repo "$(REFERENCE_REPO)" --mode "$(BASELINE_MODE)" \
	  --out "$(BASELINE_OUT)" --model "$(MODEL)" --base-url "$(BASE_URL)" \
	  --api-key-file "$(API_KEY_FILE)" --neo4j-uri "$(NEO4J_URI)" \
	  --neo4j-user "$(NEO4J_USER)" --neo4j-password "$(NEO4J_PASSWORD)" \
	  --temperature "$(TEMPERATURE)" --reasoning "$(REASONING)" \
	  --max-tokens "$(MAX_TOKENS)" --concurrency "$(CONCURRENCY)" \
	  --limit "$(FULL_LIMIT)" $(if $(filter 1,$(RESUME)),--resume,)

baseline-archive:
	@uv run agent-native-graph baseline-archive --run "$(BASELINE_OUT)"

compare-results:
	@test -n "$(ANA_RUN)" -a -n "$(DIRECT_RUN)" -a -n "$(AGENTIC_RUN)" || \
	  (echo "Set ANA_RUN, DIRECT_RUN and AGENTIC_RUN to archived run directories" && exit 1)
	@uv run agent-native-graph compare-results \
	  --ana "$(ANA_RUN)" --direct "$(DIRECT_RUN)" \
	  --agentic "$(AGENTIC_RUN)" --out "$(COMPARISON_OUT)"

.PHONY: reexecute-reference
reexecute-reference:
	@uv run python -m agent_native_graph.research.reexecute_reference \
	  --reference-repo "$(REFERENCE_REPO)" --graph "$(GRAPH)" \
	  --neo4j-uri "$(NEO4J_URI)" --neo4j-user "$(NEO4J_USER)" \
	  --neo4j-password "$(NEO4J_PASSWORD)" --out "$(REEXECUTION_OUT)"

list-tools:
	@uv run agent-native-graph tools

paper:
	@sed -n '1,120p' paper/README.md

docs-build:
	@uv run agent-native-graph build-docs --out "$(DOCS_OUT)" --reference-repo "$(REFERENCE_REPO)"

docs-serve: docs-build
	@uv run python -m http.server "$(DOCS_PORT)" --bind 127.0.0.1 --directory "$(DOCS_OUT)"

serve:
	@NEO4J_URI="$(NEO4J_URI)" \
	NEO4J_USER="$(NEO4J_USER)" \
	NEO4J_PASSWORD="$(NEO4J_PASSWORD)" \
	uv run agent-native-graph serve

serve-mcp:
	@uv run agent-native-graph serve-mcp

docker-build:
	@docker build -t "$(DOCKER_IMAGE)" .

docker-run:
	@docker run --rm -p 8080:8080 \
	  -e NEO4J_URI=bolt://host.docker.internal:7687 \
	  -e NEO4J_USER="$(NEO4J_USER)" \
	  -e NEO4J_PASSWORD="$(NEO4J_PASSWORD)" \
	  "$(DOCKER_IMAGE)"

clean:
	@find tests src -type d -name '__pycache__' -prune -exec rm -rf {} +
	@rm -rf .pytest_cache .ruff_cache .mypy_cache
