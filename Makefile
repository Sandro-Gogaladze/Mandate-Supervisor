# Packaging and run targets. Day-to-day development still happens outside
# Docker (.venv + npm run dev); these are for the packaged application.

COMPOSE       := docker compose
BUILD_COMPOSE := docker compose -f compose.yml -f compose.build.yml
IMAGES        := ghcr.io/sandro-gogaladze/mandate-supervisor-api \
                 ghcr.io/sandro-gogaladze/mandate-supervisor-runtime \
                 ghcr.io/sandro-gogaladze/mandate-supervisor-dashboard
TAG           ?= latest
PORT          ?= 5173

.PHONY: help up up-build down clean logs ps pull save load smoke

help:  ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[1m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Pull the published images and start (the download path)
	@test -f .env || { cp .env.example .env; echo "Created .env — add your ANTHROPIC_API_KEY to it (optional)."; }
	$(COMPOSE) up -d
	@echo "Console: http://localhost:$(PORT)"

up-build: ## Build from this checkout and start (the development path)
	@test -f .env || cp .env.example .env
	$(BUILD_COMPOSE) up --build -d
	@echo "Console: http://localhost:$(PORT)"

down: ## Stop, keeping the ledger and uploads
	$(COMPOSE) down

clean: ## Stop and delete all state — ledger, uploads, drafts
	$(COMPOSE) down -v

logs: ## Follow logs from all three services
	$(COMPOSE) logs -f

ps: ## Show service status
	$(COMPOSE) ps

pull: ## Fetch the latest published images
	$(COMPOSE) pull

smoke: ## Verify a running stack answers on every path
	@curl -fsS http://localhost:$(PORT)/            > /dev/null && echo "console  ok"
	@curl -fsS http://localhost:$(PORT)/api/health  > /dev/null && echo "api      ok"
	@curl -fsS http://localhost:$(PORT)/copilotkit/info > /dev/null && echo "runtime  ok"

save: ## Write the images to one tarball for offline install (USB / no wifi)
	docker save $(foreach i,$(IMAGES),$(i):$(TAG)) | gzip > mandate-supervisor-$(TAG).tar.gz
	@ls -lh mandate-supervisor-$(TAG).tar.gz

load: ## Install images from that tarball on a machine with no network
	gunzip -c mandate-supervisor-$(TAG).tar.gz | docker load
