.PHONY: install
install: ## Install the uv environment
	@echo "🚀 Creating virtual environment using uv"
	uv sync

.PHONY: check
check: ## Run the quality checks on the code
	@echo "🚀 Running quality checks"
	uv run ruff check .
	uv run pyright .

.PHONY: test
test: ## Test the code with pytest
	@echo "🚀 Testing code: Running pytest"
	uv run pytest

.PHONY: bench
bench: ## Benchmark analysis speed against main on a generated project
	uv run python benchmarks/compare.py --ref main --size medium

.PHONY: docs
docs:  ## Build and serve the documentation
	@echo "🚀 Testing documentation: Building and testing"
	uv run mkdocs serve

.PHONY: deploy-docs
deploy-docs: ## Build and serve the documentation
	@echo "🚀 Deploying documentation"
	uv run python deploy_docs.py


.PHONY: docs-test
docs-test: ## Test if documentation can be built without warnings or errors
	@uv run mkdocs build -s

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
