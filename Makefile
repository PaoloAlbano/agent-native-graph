.PHONY: help sync install-mcp format lint test test-distribution test-backend test-quality test-interfaces prepare-company-tasks load-company export-schema benchmark benchmark-full benchmark-temp1 evaluate archive-result baseline-check baseline-run baseline-archive compare-results list-tools paper docs-build docs-serve serve serve-mcp docker-build docker-run clean

NEO4J_URI ?= bolt://127.0.0.1:7687
NEO4J_USER ?= neo4j
NEO4J_PASSWORD ?= password
NEO4J_DATABASE ?=
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
EVALUATION_ROOT ?= results/cypherbench-company/query-reexecution
CONTROLLED_OUT ?= $(RUN_DIR)/controlled-plan.json
REFERENCE_PYTHON ?= uv run --extra reference python
BASELINE_MODE ?= direct
BASELINE_PROFILE ?=
REFERENCE_COMMIT ?=
BASELINE_OUT ?= $(RUN_DIR)/baseline_$(BASELINE_MODE)_$(subst /,_,$(MODEL))_$(if $(BASELINE_PROFILE),$(BASELINE_PROFILE),temp$(TEMPERATURE)_reasoning_$(REASONING))_n$(FULL_LIMIT).jsonl
COMPARISON_OUT ?= $(RUN_DIR)/comparison/cypherbench-company.md
DOCS_PORT ?= 8000
DOCS_OUT ?= build/site
DOCS_PUBLIC_URL ?= https://paoloalbano.github.io/agent-native-graph/
PROFILE ?= temp0-none
SHARED_PREFLIGHT ?= 0
RESULT_POLICY ?=
VERIFY_GRAPH_BLOCK ?= 0
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
	@echo "  make test-reference   Offline pinned-controller tests with fake model/graph"
	@echo "  make test-distribution  Opt-in wheel/Docker smoke on disposable Neo4j (no LLM)"
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
	@echo "  make compact-evaluations  Losslessly compact saved query evaluations (no queries)"
	@echo "  make controlled-plan  Prepare an offline study draft; never launch inference"
	@echo "  make list-tools       Print the ANA tool catalog"
	@echo "  make paper            Print the paper/preprint table of contents"
	@echo "  make docs-build       Generate the research website and tool reference"
	@echo "  make docs-serve       Build and preview the website on localhost:$(DOCS_PORT)"
	@echo "  make serve            Run the experimental HTTP service"
	@echo "  make demo-client      Run the bounded HTTP workflow example (ANA_API_KEY_FILE)"
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
	@uv run ruff format src/agent_native_graph tests examples docs/site/social_preview.py

lint:
	@uv run ruff check src/agent_native_graph tests examples docs/site/social_preview.py

test:
	@uv run pytest tests -q

.PHONY: test-reference
test-reference:
	@ANA_TEST_REFERENCE=1 ANA_REFERENCE_REPO="$(abspath $(REFERENCE_REPO))" \
	  uv run --extra dev --extra reference pytest \
	  tests/test_reference_foundation.py tests/test_reference_workflows.py tests/test_reference_retrieval.py -q

test-distribution:
	@ANA_TEST_DISTRIBUTION=1 uv run pytest tests/test_distribution.py -q

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
	  $(if $(filter 1,$(SHARED_PREFLIGHT)),--shared-preflight --database "$(or $(NEO4J_DATABASE),neo4j)",) \
	  $(if $(RESULT_POLICY),--result-policy "$(RESULT_POLICY)",) \
	  $(if $(filter 1,$(VERIFY_GRAPH_BLOCK)),--verify-graph-block,) \
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
	  --out "$(BASELINE_OUT)" --check-only \
	  $(if $(RESULT_POLICY),--result-policy "$(RESULT_POLICY)",) \
	  $(if $(filter 1,$(SHARED_PREFLIGHT)),--shared-preflight,) \
	  --neo4j-uri "$(NEO4J_URI)" --neo4j-user "$(NEO4J_USER)" \
	  --neo4j-password "$(NEO4J_PASSWORD)" --database "$(or $(NEO4J_DATABASE),neo4j)" \
	  $(if $(BASELINE_PROFILE),--profile "$(BASELINE_PROFILE)",) \
	  $(if $(REFERENCE_COMMIT),--reference-commit "$(REFERENCE_COMMIT)",)

baseline-run:
	@PYTHONPATH=src $(REFERENCE_PYTHON) -m agent_native_graph.interfaces.cli baseline-run \
	  --reference-repo "$(REFERENCE_REPO)" --mode "$(BASELINE_MODE)" \
	  --out "$(BASELINE_OUT)" --model "$(MODEL)" --base-url "$(BASE_URL)" \
	  $(if $(filter 1,$(VERIFY_GRAPH_BLOCK)),--verify-graph-block,) \
	  $(if $(RESULT_POLICY),--result-policy "$(RESULT_POLICY)",) \
	  $(if $(filter 1,$(SHARED_PREFLIGHT)),--shared-preflight,) \
	  --api-key-file "$(API_KEY_FILE)" --neo4j-uri "$(NEO4J_URI)" \
	  --neo4j-user "$(NEO4J_USER)" --neo4j-password "$(NEO4J_PASSWORD)" \
	  --database "$(or $(NEO4J_DATABASE),neo4j)" \
	  --temperature "$(TEMPERATURE)" --reasoning "$(REASONING)" \
	  --max-tokens "$(MAX_TOKENS)" --concurrency "$(CONCURRENCY)" \
	  --limit "$(FULL_LIMIT)" $(if $(filter 1,$(RESUME)),--resume,) \
	  $(if $(BASELINE_PROFILE),--profile "$(BASELINE_PROFILE)",) \
	  $(if $(REFERENCE_COMMIT),--reference-commit "$(REFERENCE_COMMIT)",)

baseline-archive:
	@uv run agent-native-graph baseline-archive --run "$(BASELINE_OUT)"

compare-results:
	@test -n "$(ANA_RUN)" -a -n "$(DIRECT_RUN)" -a -n "$(AGENTIC_RUN)" || \
	  (echo "Set ANA_RUN, DIRECT_RUN and AGENTIC_RUN to archived run directories" && exit 1)
	@uv run agent-native-graph compare-results \
	  --ana "$(ANA_RUN)" --direct "$(DIRECT_RUN)" \
	  --agentic "$(AGENTIC_RUN)" --out "$(COMPARISON_OUT)"

.PHONY: reexecute-reference compact-evaluations controlled-plan
controlled-plan:
	@uv run python -m agent_native_graph.research.controlled_plan \
	  --tasks "$(TASKS)" --graph "$(GRAPH)" --reference-repo "$(REFERENCE_REPO)" \
	  --out "$(CONTROLLED_OUT)"

compact-evaluations:
	@uv run python -m agent_native_graph.research.evaluation_storage compact --root "$(EVALUATION_ROOT)"

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
	@uv run python docs/site/social_preview.py --site-dir "$(DOCS_OUT)" --base-url "$(DOCS_PUBLIC_URL)"

docs-serve: docs-build
	@uv run python -m http.server "$(DOCS_PORT)" --bind 127.0.0.1 --directory "$(DOCS_OUT)"

serve:
	@NEO4J_URI="$(NEO4J_URI)" \
	NEO4J_USER="$(NEO4J_USER)" \
	NEO4J_PASSWORD="$(NEO4J_PASSWORD)" \
	NEO4J_DATABASE="$(NEO4J_DATABASE)" \
	uv run agent-native-graph serve

.PHONY: demo-client
demo-client:
	@uv run python examples/http_workflow.py

serve-mcp:
	@uv run agent-native-graph serve-mcp

docker-build:
	@docker build -t "$(DOCKER_IMAGE)" .

docker-run:
	@test -n "$$ANA_AUTH_FILE" || (echo "Set ANA_AUTH_FILE to your private client config path"; exit 1)
	@docker run --rm -p 127.0.0.1:8080:8080 \
	  --mount "type=bind,src=$$ANA_AUTH_FILE,dst=/run/secrets/ana-auth.json,readonly" \
	  -e ANA_AUTH_FILE=/run/secrets/ana-auth.json \
	  -e NEO4J_URI=bolt://host.docker.internal:7687 \
	  -e NEO4J_USER="$(NEO4J_USER)" \
	  -e NEO4J_PASSWORD="$(NEO4J_PASSWORD)" \
	  -e NEO4J_DATABASE="$(NEO4J_DATABASE)" \
	  "$(DOCKER_IMAGE)"

clean:
	@find tests src -type d -name '__pycache__' -prune -exec rm -rf {} +
	@rm -rf .pytest_cache .ruff_cache .mypy_cache
