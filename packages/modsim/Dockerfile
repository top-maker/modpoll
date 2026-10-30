# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/

# Copy dependency metadata first to cache the install layer.
WORKDIR /app
COPY uv.lock pyproject.toml README.md /app/

# Project initialization:
RUN uv sync --locked --no-dev --no-install-project

# Copy Python app to the Docker image
COPY modsim /app/modsim/
COPY contrib /app/contrib/
COPY examples /app/examples

CMD [ "python", "-m", "modsim" ]
