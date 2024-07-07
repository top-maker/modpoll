#!/bin/bash
APP_NAME="modsim"
APP_TAG="0.3.4"
PYTHON_TAG="3.8-slim-buster"

# Log into Docker registry
echo "${DOCKER_PASSWORD}" | docker login -u "${DOCKER_USERNAME}" --password-stdin "${$DOCKER_REGISTRY}"

# # Enable experimental features for Docker CLI
# export DOCKER_CLI_EXPERIMENTAL=enabled

# Ensure QEMU is set up for multi-architecture builds
docker buildx inspect mybuilder &>/dev/null || docker buildx create --name mybuilder ; docker buildx use mybuilder

# Build and push the Docker image using buildx
docker buildx build \
  --build-arg "APP_TAG=${APP_TAG}" \
  --build-arg "PYTHON_TAG=${PYTHON_TAG}" \
  --platform "linux/amd64,linux/arm64,linux/arm/v7" \
  --tag "${$DOCKER_REGISTRY}/${DOCKER_USERNAME}/${APP_NAME}:${APP_TAG}" \
  --tag "${$DOCKER_REGISTRY}/${DOCKER_USERNAME}/${APP_NAME}:latest" \
  --push .
