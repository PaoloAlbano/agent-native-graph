import pytest

from agent_native_graph.application.auth import ApiKeyAuth, ApiKeyClient


@pytest.fixture
def demo_auth():
    """Explicit test-only clients; no implicit authentication bypass in the app."""
    return ApiKeyAuth((ApiKeyClient("test-client", "a" * 32),))


@pytest.fixture
def demo_headers():
    return {"Authorization": "Bearer " + "a" * 32}
