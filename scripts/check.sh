#!/usr/bin/env sh
set -eu

docker compose config --quiet
docker compose run --rm --no-deps backend pytest
docker compose run --rm --no-deps frontend npm test -- --run
docker compose run --rm --no-deps frontend npm run build
