"""Reference workflow wiring with ANA transport and bounded read-only graph access.

Reference imports stay inside factories: callers must first select their source
using reference_source. No reference checkout or global factory is patched.
"""

import asyncio

from agent_native_graph.llm_providers.accounting import request_role
from agent_native_graph.llm_providers.execution import ensure_question_open, gather_and_settle
from agent_native_graph.research.read_only import execute_read_only_async


def guarded_graph_class(*, timeout: float, max_rows: int):
    """Guard every query, including inherited introspection and entity verification."""
    from multigraphrag.graph.memgraph_client import MemgraphClient
    from multigraphrag.graph.models import QueryOutcome

    hard_limit = max_rows

    class ReadOnlyReferenceGraph(MemgraphClient):
        async def run_query(self, cypher, parameters=None, *, max_rows=200):
            result = await execute_read_only_async(
                self._driver,
                self._settings.database,
                cypher,
                timeout,
                hard_limit,
                parameters=parameters,
            )
            if not result["ok"]:
                return QueryOutcome(success=False, error_message=result["error"])
            rows = result["rows"]
            return QueryOutcome(
                success=True,
                records=[dict(zip(result["columns"], row, strict=True)) for row in rows[:max_rows]],
                truncated=len(rows) > max_rows,
            )

    return ReadOnlyReferenceGraph


def profile_client(provider, *, role: str, logger, concurrency: int):
    """Adapt ANA HTTP calls to the pinned reference client's structured-output API."""
    from multigraphrag.llm.base import LLMClient
    from multigraphrag.llm.vllm_client import VllmClient

    class ProfileClient(LLMClient):
        async def _request(self, system_prompt, user_prompt, response_model=None):
            ensure_question_open()
            response, error = None, None
            try:
                response_format = None
                if response_model is not None:
                    response_format = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": response_model.__name__,
                            "schema": response_model.model_json_schema(),
                            "strict": True,
                        },
                    }
                with request_role(role):
                    message = await provider.achat(
                        [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        response_format=response_format,
                    )
                response = message.get("content") or ""
                if response_model is not None:
                    return VllmClient._parse_structured(response, response_model)
                return response
            except BaseException as exc:
                error = type(exc).__name__
                raise
            finally:
                logger.log(
                    agent=role,
                    model=provider._model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response=response,
                    error=error,
                )

        async def complete(self, *, system_prompt, user_prompt):
            return await self._request(system_prompt, user_prompt)

        async def complete_structured(self, *, system_prompt, user_prompt, response_model):
            return await self._request(system_prompt, user_prompt, response_model)

        async def _batch(self, prompts, response_model=None):
            semaphore = asyncio.Semaphore(self.max_concurrency)

            async def complete(prompt):
                async with semaphore:
                    return await self._request(
                        prompt.system_prompt, prompt.user_prompt, response_model
                    )

            return await gather_and_settle(complete(prompt) for prompt in prompts)

        async def complete_many(self, prompts):
            return await self._batch(prompts)

        async def complete_structured_many(self, prompts, response_model):
            return await self._batch(prompts, response_model)

    instance = ProfileClient()
    instance.max_concurrency = concurrency
    return instance


def build_profile_runner(mode, settings, graph_client, provider, logger):
    """Compose unchanged reference agents/workflows; replace only their LLM adapter."""
    from multigraphrag.agents.entity_extractor import NamedEntityExtractorAgent
    from multigraphrag.agents.evaluator import QueryEvaluatorAgent
    from multigraphrag.agents.feedback_aggregator import FeedbackAggregatorAgent
    from multigraphrag.agents.instructions_generator import InstructionsGeneratorAgent
    from multigraphrag.agents.interpreter import InterpreterAgent
    from multigraphrag.agents.query_generator import QueryGeneratorAgent
    from multigraphrag.agents.verification import VerificationModule
    from multigraphrag.workflow.pipeline import AgentBundle, GraphRAGPipeline
    from multigraphrag.workflow.single_pass import SinglePassRunner

    def client(role):
        return profile_client(
            provider, role=role, logger=logger, concurrency=settings.llm.max_concurrency
        )

    generator = QueryGeneratorAgent(client("query_generator"))
    if mode == "direct":
        return generator
    interpreter = InterpreterAgent(client("interpreter"))
    workflow = settings.workflow
    if mode == "single":
        return SinglePassRunner(
            generator,
            interpreter,
            graph_client,
            max_attempts=workflow.max_refinement_iterations,
            max_query_result_rows=workflow.max_query_result_rows,
        )
    bundle = AgentBundle(
        query_generator=generator,
        interpreter=interpreter,
        evaluator=QueryEvaluatorAgent(client("query_evaluator")),
        entity_extractor=NamedEntityExtractorAgent(client("entity_extractor")),
        verification=VerificationModule(client("verification_ranker"), graph_client, workflow),
        instructions_generator=InstructionsGeneratorAgent(client("instructions_generator")),
        feedback_aggregator=FeedbackAggregatorAgent(client("feedback_aggregator")),
    )
    return GraphRAGPipeline(
        bundle,
        graph_client,
        [],
        max_refinement_iterations=workflow.max_refinement_iterations,
        max_query_result_rows=workflow.max_query_result_rows,
    )
