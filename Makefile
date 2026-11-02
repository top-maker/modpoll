PROJECT_NAME ?= modpoll

.PHONY: install
install: ## Install the uv environment and pre-commit hooks
	@uv sync --all-extras --all-groups
	@uv run pre-commit install --allow-missing-config

.PHONY: check
check: ## Run code quality tools.
	@echo "🚀 Checking uv lock file consistency with 'pyproject.toml'"
	@uv lock --check
	@echo "🚀 Linting code: Running pre-commit"
	@uv run pre-commit run -a
	@echo "🚀 Checking for obsolete dependencies: Running deptry"
	@uv run deptry .

.PHONY: test
test: ## Test the code with pytest
	@echo "🚀 Testing code: Running pytest"
	@uv run pytest tests --doctest-modules
	@uv run python tools/test-wot-source.py --doctest-modules

.PHONY: build
build: clean-build ## Build wheel file using uv
	@echo "🚀 Creating wheel file"
	@uv build --no-sources

.PHONY: clean-build
clean-build: ## clean build artifacts
	@rm -rf dist

.PHONY: publish
publish: ## Publish a release to PyPI.
	@echo "🚀 Publishing: Dry run."
	@if uv publish --dry-run --token ${PYPI_TOKEN}; then \
		echo "Dry run successful. Proceeding with publishing..."; \
		uv publish --token ${PYPI_TOKEN}; \
	else \
		echo "Dry run failed. Version might already exist or other error occurred."; \
		exit 1; \
	fi

.PHONY: build-and-publish
build-and-publish: build publish ## Build and publish.

.PHONY: docker-build-dev
docker-build-dev: ## Build docker for local dev
	@echo "🚀 Creating docker image file"
	@docker build -t ${PROJECT_NAME}:dev .

.PHONY: docker-run-dev
docker-run-dev: docker-build-dev ## Run docker compose for local dev
	@echo "🚀 Docker compose run: ${PROJECT_NAME}:dev"
	@docker compose up --build

.PHONY: docs
docs: ## Build docs into html files
	@uv run --group docs pandoc --from=markdown --to=rst CHANGELOG.md -o docs/site/changelog.rst
	@uv run --group docs sphinx-build docs/site/ docs/_build/html

.PHONY: docs-serve
docs-serve: ## Build and serve the docs for local dev
	@uv run --group docs pandoc --from=markdown --to=rst CHANGELOG.md -o docs/site/changelog.rst
	@uv run --group docs sphinx-autobuild docs/site/ docs/_build/html

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
