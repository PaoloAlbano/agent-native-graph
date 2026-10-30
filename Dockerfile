FROM python:3.12-slim AS build-base

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.5.31 /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

RUN uv export --frozen --no-dev --extra service --no-emit-project --format requirements-txt > /requirements.txt

FROM build-base AS wheel-build
RUN uv build --wheel --out-dir /dist

# Release builds override this stage with --build-context wheels=./dist.
FROM scratch AS wheels
COPY --from=wheel-build /dist/ /

FROM python:3.12-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
COPY --from=build-base /bin/uv /bin/uv
COPY --from=build-base /requirements.txt /tmp/requirements.txt
COPY --from=wheels /*.whl /tmp/wheels/
RUN uv venv /app/.venv \
    && uv pip install --python /app/.venv/bin/python --require-hashes -r /tmp/requirements.txt \
    && uv pip install --python /app/.venv/bin/python --no-deps /tmp/wheels/*.whl \
    && rm -rf /tmp/wheels /tmp/requirements.txt
RUN groupadd --gid 10001 ana && useradd --uid 10001 --gid ana --no-create-home ana

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).close()"]

CMD ["agent-native-graph", "serve"]
