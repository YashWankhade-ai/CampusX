.PHONY: up down build bash db-shell shell db-upgrade db-migrate

up:
	docker-compose up -d

down:
	docker-compose down

build:
	docker-compose build

bash:
	docker-compose exec app bash

db-shell:
	docker-compose exec db psql -U postgres -d campusx

shell:
	docker-compose exec app flask shell

db-upgrade:
	docker-compose exec app flask db upgrade

db-migrate:
	docker-compose exec app flask db migrate -m "$(m)"
