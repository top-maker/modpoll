PROJECT_NAME ?= modsim

.PHONY: install
install: ## Install the uv environment and install the pre-commit hooks
	@echo "🚀 Installing the project and pre-commit hooks"
	@uv sync --all-groups
	@uv run pre-commit install --allow-missing-config

.PHONY: check
check: ## Run code quality tools.
	@echo "🚀 Checking uv lock file consistency with 'pyproject.toml': Running uv lock --check"
	@uv lock --check
	@echo "🚀 Linting code: Running pre-commit"
	@uv run pre-commit run -a
	@echo "🚀 Static type checking: Running mypy"
	@uv run mypy
	@echo "🚀 Checking for obsolete dependencies: Running deptry"
	@uv run deptry .

.PHONY: test
test: ## Test the code with pytest
	@echo "🚀 Testing code: Running pytest"
	@uv run pytest --doctest-modules

.PHONY: build
build: clean-build ## Build wheel file using uv
	@echo "🚀 Creating wheel file"
	@uv build

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
docker-run-dev: docker-build-dev ## Run docker for local dev
	@echo "🚀 Docker run: ${PROJECT_NAME}:dev"
	@docker run --rm ${PROJECT_NAME}:dev

.PHONY: docs-test
docs-test: ## Test if documentation can be built without warnings or errors
	@uv run --group docs mkdocs build -s

.PHONY: docs
docs: ## Build and serve the documentation
	@uv run --group docs mkdocs serve

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
