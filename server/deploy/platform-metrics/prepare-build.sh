#!/bin/sh
# Local metadata preflight by default; --build explicitly opts in to tagging/building.
set -eu
base_id='sha256:cc3c918041ea047ea924eee60eba1c0789235950df84606ee8aa89249d04b8a9'
base_tag='platform-metrics-base:approved-cc3c918041ea'
output_tag='platform-metrics-receiver:local'
mode=${1:---dry-run}
[ "$#" -le 1 ] && { [ "$mode" = --dry-run ] || [ "$mode" = --build ]; } || {
    printf 'Usage: %s [--dry-run|--build]\n' "$0" >&2; exit 2;
}
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
server_dir=$(CDPATH= cd -- "$script_dir/../.." && pwd)
repo=$(git -C "$server_dir" rev-parse --show-toplevel)
# Do not silently build from a dirty tree, including untracked files.
[ -z "$(git -C "$repo" status --porcelain --untracked-files=all)" ] || {
    printf 'Checkout is dirty; use a clean, reviewed checkout.\n' >&2; exit 1;
}
for path in server/src/cottage_monitoring/config.py server/src/cottage_monitoring/api/platform_metrics.py; do
    git -C "$repo" diff --quiet 03081f3 -- "$path" || {
        printf 'Accepted PM1 source differs: %s\n' "$path" >&2; exit 1;
    }
done
# Pin every Docker call to the selected context. The context's built-in docker
# builder must name that same context (or its exact Docker endpoint).
context=$(docker context show)
[ -n "$context" ] || { printf 'Docker context is empty.\n' >&2; exit 1; }
endpoint=$(docker --context "$context" context inspect "$context" --format '{{.Endpoints.docker.Host}}')
[ -n "$endpoint" ] && [ "$endpoint" != '<no value>' ] || {
    printf 'Docker context has no endpoint.\n' >&2; exit 1;
}
builder=$context
actual=$(docker --context "$context" image inspect "$base_id" --format '{{.Id}}')
[ "$actual" = "$base_id" ] || { printf 'Base image ID mismatch.\n' >&2; exit 1; }
platform=$(docker --context "$context" image inspect "$base_id" --format '{{.Os}}/{{.Architecture}}')
[ "$platform" = linux/amd64 ] || { printf 'Base must be linux/amd64.\n' >&2; exit 1; }
metadata=$(docker --context "$context" buildx inspect "$builder")
printf '%s\n' "$metadata" | grep -Eq '^Driver:[[:space:]]+docker[[:space:]]*$' || {
    printf 'Builder must use the docker driver/local image store.\n' >&2; exit 1;
}
builder_endpoints=$(printf '%s\n' "$metadata" | awk '/^[[:space:]]*Endpoint:/ {sub(/^[[:space:]]*Endpoint:[[:space:]]*/, ""); print}')
[ "$builder_endpoints" = "$context" ] || [ "$builder_endpoints" = "$endpoint" ] || {
    printf 'Builder endpoint does not uniquely match selected Docker context.\n' >&2; exit 1;
}
printf '%s\n' "$metadata" | grep -Eq '^Platforms:.*linux/amd64([, *]|$)' || {
    printf 'Builder must support linux/amd64.\n' >&2; exit 1;
}
if docker --context "$context" image inspect "$base_tag" >/dev/null 2>&1; then
    tagged=$(docker --context "$context" image inspect "$base_tag" --format '{{.Id}}')
    [ "$tagged" = "$base_id" ] || { printf 'Local base tag is already in use.\n' >&2; exit 1; }
fi
if docker --context "$context" image inspect "$output_tag" >/dev/null 2>&1; then
    printf 'Output tag already exists; choose a reviewed cleanup or another tag.\n' >&2; exit 1
fi
printf 'Preflight passed: approved base %s; %s; context/builder %s (docker).\n' "$base_id" "$platform" "$builder"
printf 'Build command: docker --context %s buildx build --builder %s --platform linux/amd64 --pull=false --load -f %s/Dockerfile -t %s %s\n' "$context" "$builder" "$script_dir" "$output_tag" "$server_dir"
[ "$mode" = --build ] || exit 0
# One trusted local operator; no concurrent retagging/builds during this operation.
docker --context "$context" image tag "$base_id" "$base_tag"
[ "$(docker --context "$context" image inspect "$base_tag" --format '{{.Id}}')" = "$base_id" ] || {
    printf 'Base tag verification failed.\n' >&2; exit 1;
}
docker --context "$context" buildx build --builder "$builder" --platform linux/amd64 --pull=false --load \
    -f "$script_dir/Dockerfile" -t "$output_tag" "$server_dir"
[ "$(docker --context "$context" image inspect "$base_tag" --format '{{.Id}}')" = "$base_id" ] || {
    printf 'Base tag changed during build; discard output.\n' >&2; exit 1;
}
printf 'Build finished. Inspect the resulting image and record its ID before use.\n'
