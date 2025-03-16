#!make
DOCKER_COMPOSE=docker compose

.PHONY: init
init: build up logs

.PHONY: up
up:
	$(DOCKER_COMPOSE) up -d

.PHONY: down
down:
	$(DOCKER_COMPOSE) down

.PHONY: ps
ps:
	$(DOCKER_COMPOSE) ps

.PHONY: build
build:
	$(DOCKER_COMPOSE) build --force-rm

.PHONY: exec
exec:
	docker exec -it vm_manager.server bash

.PHONY: logs
logs:
	$(DOCKER_COMPOSE) logs -f

