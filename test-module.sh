#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
set -Eeuo pipefail
node="${1:?missing NS8 test node address}"
image="${2:?missing module image URL}"
if [[ ! "$image" =~ ^ghcr\.io/[a-zA-Z0-9_./:-]+$ ]]; then
    echo 'Invalid test image URL' >&2
    exit 64
fi
key="${SSH_KEYFILE:-$HOME/.ssh/id_ecdsa}"
mkdir -p tests/outputs
ssh -i "$key" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "root@$node" "bash -s -- '$image'" < tests/ns8-smoke.sh \
    2>&1 | tee tests/outputs/ns8-smoke.log
