#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
set -Eeuo pipefail
repobase="${REPOBASE:-ghcr.io/platypuschan}"
repobase="${repobase,,}"
runtime_image="$(REPOBASE="$repobase" .github/scripts/runtime-image)"
maubot_image="$(REPOBASE="$repobase" .github/scripts/runtime-image maubot)"
if [[ -z "${CI:-}" ]]; then
    buildah bud --layers -t "$runtime_image" runtime/synapse
    buildah bud --layers -t "$maubot_image" runtime/maubot
fi
node_image="docker.io/library/node:24.21.0-slim"
builder="nodebuilder-matrix-reworked2"
container="$(buildah from scratch)"
cleanup() { buildah rm "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT
if ! buildah inspect --type container "$builder" >/dev/null 2>&1; then
    buildah from --name "$builder" -v "${PWD}:/usr/src:Z" "$node_image" >/dev/null
fi
buildah run --workingdir=/usr/src/ui --env=NODE_OPTIONS=--openssl-legacy-provider "$builder" sh -c 'corepack enable && yarn install --immutable && yarn build'
buildah add "$container" imageroot /imageroot
buildah add "$container" ui/dist /ui
# Record the runtime hashes in both the label and the module image manifest.
manifest="$(mktemp)"
RUNTIME_IMAGE="$runtime_image" MAUBOT_IMAGE="$maubot_image" python3 - <<'PY' > "$manifest"
import json,os
images=json.load(open('imageroot/images.json'))
images['synapse']=os.environ['RUNTIME_IMAGE']
images['maubot']=os.environ['MAUBOT_IMAGE']
print(json.dumps(images,indent=2))
PY
images="$(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1])).values()))' "$manifest")"
buildah add "$container" "$manifest" /imageroot/images.json
python3 -c 'import os,sys; os.unlink(sys.argv[1])' "$manifest"
buildah config --entrypoint=/ \
    --label="org.opencontainers.image.source=https://github.com/Platypuschan/ns8-matrix-reworked2" \
    --label="org.opencontainers.image.revision=${GITHUB_SHA:-$(git rev-parse HEAD)}" \
    --label="org.opencontainers.image.licenses=AGPL-3.0-or-later" \
    --label="org.nethserver.authorizations=traefik@node:routeadm cluster:accountconsumer node:fwadm" \
    --label="org.nethserver.tcp-ports-demand=20" \
    --label="org.nethserver.udp-ports-demand=66" \
    --label="org.nethserver.rootfull=0" \
    --label="org.nethserver.min-core=3.20.1" \
    --label="org.nethserver.images=${images}" "$container"
buildah commit "$container" "$repobase/matrix-reworked2" >/dev/null
if [[ -n "${CI:-}" ]]; then
    printf 'images=%s\n' "$repobase/matrix-reworked2" >> "$GITHUB_OUTPUT"
else
    printf 'Built %s, %s and %s\n' "$repobase/matrix-reworked2" "$runtime_image" "$maubot_image"
fi
