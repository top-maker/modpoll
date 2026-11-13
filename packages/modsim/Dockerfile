# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/

# Copy dependency metadata first to cache the install layer.
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
COPY uv.lock pyproject.toml README.md /app/

# Project initialization:
RUN uv sync --locked --no-dev --no-install-project

# Copy Python app to the Docker image
COPY modsim /app/modsim/
COPY examples /app/examples
COPY tests/fixtures/io-module /app/tests/fixtures/io-module
COPY examples/deployment.yaml /app/deployment.yaml
COPY tools/fetch-models.py /app/tools/fetch-models.py
RUN .venv/bin/python tools/fetch-models.py

CMD [ "python", "-m", "modsim" ]
