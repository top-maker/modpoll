# syntax=docker/dockerfile:1
# Build from the repository root: docker build -f packages/modpoll/Dockerfile .

# FROM python:3.12-alpine
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/

# The workspace lock covers every member, so each member's metadata is copied for `--locked`.
# Only modpoll and the modpoll-wot it pins are installed.
WORKDIR /app
COPY pyproject.toml uv.lock /app/
COPY packages/modsim/pyproject.toml /app/packages/modsim/
COPY packages/modpoll-wot /app/packages/modpoll-wot
COPY packages/modpoll/pyproject.toml packages/modpoll/README.md /app/packages/modpoll/
COPY packages/modpoll/modpoll /app/packages/modpoll/modpoll

# Project initialization:
RUN uv sync --locked --no-dev --all-extras --no-editable --package modpoll
ENV PATH="/app/.venv/bin:${PATH}"

CMD ["modpoll", "--version"]
