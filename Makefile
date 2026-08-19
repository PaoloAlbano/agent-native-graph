.PHONY: help sync install-mcp format lint test test-backend test-quality test-interfaces load-company benchmark benchmark-temp1 evaluate list-tools paper serve serve-mcp docker-build docker-run clean

NEO4J_URI ?= bolt://127.0.0.1:7687
NEO4J_USER ?= neo4j
NEO4J_PASSWORD ?= password
BASE_URL ?= https://openrouter.ai/api/
MODEL ?= openai/gpt-oss-120b
API_KEY_FILE ?= /tmp/grapharrow-agent-key

TASKS ?= data/tasks_company_test.jsonl
SCHEMA_JSON ?= data/company_schema.json
GRAPH ?= downloads/company_simplekg.json
OUT ?= results/agent_tools_first100_gpt_oss_120b.jsonl
OUT_TEMP1 ?= results/agent_tools_first100_gpt_oss_120b_temp1_reasoning.jsonl
LIMIT ?= 100
MAX_TOKENS ?= 16000
MAX_STEPS ?= 12
CONCURRENCY ?= 3
BATCH_SIZE ?= 2000
DOCKER_IMAGE ?= agent-native-graph

help:
	@echo "Agent-Native Graph targets"
	@echo ""
	@echo "  make sync                Alias for make install"
	@echo "  make install             Install uv dependencies with dev and service extras"
	@echo "  make format           Format Python code with ruff"
	@echo "  make lint             Check Python code with ruff"
	@echo "  make test             Run all current unit tests"
	@echo "  make load-company     Clear/load the CypherBench company graph into Neo4j"
	@echo "  make benchmark        Run temp=0 ANA benchmark"
	@echo "  make benchmark-temp1  Run temp=1 + thinking medium ANA benchmark"
	@echo "  make evaluate         Evaluate OUT with deterministic answer_json scoring"
	@echo "  make list-tools       Print the ANA tool catalog"
	@echo "  make paper            Print the paper/preprint table of contents"
	@echo "  make serve            Run the experimental HTTP service"
	@echo "  make serve-mcp        Run the experimental MCP service"
	@echo "  make docker-build     Build service image"
	@echo "  make docker-run       Run service image"
	@echo ""
	@echo "Common overrides:"
	@echo "  MODEL=$(MODEL)"
	@echo "  LIMIT=$(LIMIT)"
	@echo "  OUT=$(OUT)"

install:
	@uv sync --extra dev --extra service

sync: install

install-mcp:
	@uv sync --extra dev --extra service --extra mcp

format:
	@uv run ruff format src/agent_native_graph

lint:
	@uv run ruff check src/agent_native_graph --exclude src/agent_native_graph/backends/neo4j/backend.py

test: test-backend test-quality test-interfaces

test-backend:
	@uv run pytest tests/test_agent_tool_backend.py -q

test-quality:
	@uv run pytest tests/test_tool_quality_analysis.py -q

test-interfaces:
	@uv run pytest tests/test_mcp_interface.py -q

load-company:
	@uv run python scripts/load_simplekg_neo4j.py \
	  --neo4j-uri "$(NEO4J_URI)" \
	  --neo4j-user "$(NEO4J_USER)" \
	  --neo4j-password "$(NEO4J_PASSWORD)" \
	  --graph "$(GRAPH)" \
	  --clear \
	  --batch-size "$(BATCH_SIZE)"

benchmark:
	@uv run agent-native-graph benchmark-neo4j \
	  --neo4j-uri "$(NEO4J_URI)" \
	  --neo4j-user "$(NEO4J_USER)" \
	  --neo4j-password "$(NEO4J_PASSWORD)" \
	  --base-url "$(BASE_URL)" \
	  --model "$(MODEL)" \
	  --api-key-file "$(API_KEY_FILE)" \
	  --tasks "$(TASKS)" \
	  --schema-json "$(SCHEMA_JSON)" \
	  --out "$(OUT)" \
	  --limit "$(LIMIT)" \
	  --native-tools \
	  --max-tokens "$(MAX_TOKENS)" \
	  --max-steps "$(MAX_STEPS)" \
	  --concurrency "$(CONCURRENCY)" \
	  --evaluation-fetch-all-pages

benchmark-temp1:
	@uv run agent-native-graph benchmark-neo4j \
	  --neo4j-uri "$(NEO4J_URI)" \
	  --neo4j-user "$(NEO4J_USER)" \
	  --neo4j-password "$(NEO4J_PASSWORD)" \
	  --base-url "$(BASE_URL)" \
	  --model "$(MODEL)" \
	  --api-key-file "$(API_KEY_FILE)" \
	  --tasks "$(TASKS)" \
	  --schema-json "$(SCHEMA_JSON)" \
	  --out "$(OUT_TEMP1)" \
	  --limit "$(LIMIT)" \
	  --native-tools \
	  --temperature 1 \
	  --enable-thinking \
	  --thinking-effort medium \
	  --max-tokens "$(MAX_TOKENS)" \
	  --max-steps "$(MAX_STEPS)" \
	  --concurrency "$(CONCURRENCY)" \
	  --evaluation-fetch-all-pages

evaluate:
	@uv run python scripts/evaluate_run.py --run "$(OUT)"

list-tools:
	@uv run agent-native-graph tools

paper:
	@sed -n '1,120p' paper/README.md

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
	@find tests scripts src -type d -name '__pycache__' -prune -exec rm -rf {} +
	@rm -rf .pytest_cache .ruff_cache .mypy_cache
