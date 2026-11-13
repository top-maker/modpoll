# syntax=docker/dockerfile:1

# FROM python:3.12-alpine
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/

# Copy dependency metadata first to cache the install layer.
WORKDIR /app
COPY uv.lock pyproject.toml README.md /app/
COPY modpoll /app/modpoll

# Project initialization:
RUN uv sync --locked --no-dev --all-extras --no-editable
ENV PATH="/app/.venv/bin:${PATH}"

CMD ["modpoll", "--version"]
