.PHONY: up down logs rebuild shell backup


up:
docker compose up -d --build


rebuild:
docker compose build --no-cache
docker compose up -d


logs:
docker compose logs -f --tail=200 app


shell:
docker compose exec app bash || docker compose exec app sh


backup:
mkdir -p backups && cp data/db.db backups/db_$$(date +%F_%H%M%S).db


down:
docker compose down