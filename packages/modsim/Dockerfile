# syntax=docker/dockerfile:1
# Build from the repository root: docker build -f packages/modsim/Dockerfile .

FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/

# Copy dependency metadata first to cache the install layer. The workspace lock covers every
# member, so each member's metadata is copied for `--locked`; modsim itself runs from /app/modsim.
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock /app/
COPY packages/modpoll/pyproject.toml /app/packages/modpoll/
COPY packages/modpoll-wot /app/packages/modpoll-wot
COPY packages/modsim/pyproject.toml packages/modsim/README.md /app/packages/modsim/

# Project initialization:
RUN uv sync --locked --no-dev --no-install-project --no-editable --package modsim

# Copy Python app to the Docker image
COPY packages/modsim/modsim /app/modsim/
COPY packages/modsim/examples /app/examples
COPY packages/modsim/tests/fixtures/io-module /app/tests/fixtures/io-module
COPY packages/modsim/examples/deployment.yaml /app/deployment.yaml
COPY packages/modsim/tools/fetch-models.py /app/tools/fetch-models.py
RUN .venv/bin/python tools/fetch-models.py

CMD [ "python", "-m", "modsim" ]
