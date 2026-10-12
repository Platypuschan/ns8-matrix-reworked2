#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Only run in a disposable NS8 integration-test VM.
set -Eeuo pipefail
umask 077
image="${1:?}"
module=""
work="$(mktemp -d)"
failed() {
    echo "NS8 Matrix test failed at line $1" >&2
    if [[ -n "$module" ]]; then
        runagent -m "$module" systemctl --user --no-pager status 'matrix-*' || true
        runagent -m "$module" journalctl --user --no-pager -n 100 || true
    fi
}
trap 'failed "$LINENO"' ERR
api-cli run add-module --data "$(jq -n --arg image "$image" '{image:$image,node:1}')" > "$work/add.json"
module="$(jq -r '.module_id' "$work/add.json")"
[[ "$module" != null && -n "$module" ]]
echo "Installed $module"

action() {
    local data='{}'
    if [[ $# -gt 1 ]]; then data="$2"; fi
    api-cli run "module/$module/$1" --data "$data"
}
core='{"server_name":"example.test","synapse_domain_name":"matrix.example.test","element_domain_name":"chat.example.test","lets_encrypt":false,"federation":true}'
action configure-module "$core" > "$work/configure.json"
action get-configuration > "$work/config.json"
port="$(jq -r '.ports.gateway' "$work/config.json")"
synapse="$(jq -r '.ports.synapse' "$work/config.json")"
base="http://127.0.0.1:$port"
curl -fsS "$base/_matrix/client/versions" | jq -e '.versions | length > 0' >/dev/null
curl -fsS "$base/.well-known/matrix/server" | jq -e '."m.server" == "matrix.example.test:443"' >/dev/null
curl -fsS "$base/.well-known/matrix/client" | jq -e '."m.homeserver".base_url == "https://matrix.example.test"' >/dev/null
action manage-recovery-admin > "$work/recovery.json"
jq '{type:"m.login.password", identifier:{type:"m.id.user",user:.user},password:.password}' "$work/recovery.json" > "$work/login.json"
curl -fsS -H 'Content-Type: application/json' --data-binary "@$work/login.json" "$base/_matrix/client/v3/login" > "$work/login-result.json"
token="$(jq -r '.access_token' "$work/login-result.json")"
[[ "$token" != null && -n "$token" ]]
echo 'Synapse API, discovery and local administrator login passed'

# A no-op save keeps the same running Synapse container.
before="$(runagent -m "$module" podman inspect matrix-synapse --format '{{.Id}}')"
action configure-module "$core" > "$work/noop.json"
after="$(runagent -m "$module" podman inspect matrix-synapse --format '{{.Id}}')"
[[ "$before" == "$after" ]]
echo 'Unchanged configuration did not restart Synapse'

# Enable the static administration client and maubot, then check their real HTTP servers.
jq '. + {extensions:{maubot:{enabled:true,host:"maubot.example.test"},ketesa:{enabled:true,host:"admin.example.test"}}}' <<< "$core" > "$work/extensions.json"
action configure-module "$(cat "$work/extensions.json")" > "$work/configure.json"
action get-configuration > "$work/config.json"
maubot_port="$(jq -r '.ports.maubot' "$work/config.json")"
ketesa_port="$(jq -r '.ports.ketesa' "$work/config.json")"
for attempt in {1..60}; do
    if curl -fsS "http://127.0.0.1:$maubot_port/_matrix/maubot/" > /dev/null && curl -fsS "http://127.0.0.1:$ketesa_port/" > /dev/null; then break; fi
    sleep 2
done
curl -fsS "http://127.0.0.1:$maubot_port/_matrix/maubot/" > /dev/null
curl -fsS "http://127.0.0.1:$ketesa_port/" > /dev/null
curl -fsS "http://127.0.0.1:$ketesa_port/config.json" | jq -e '.restrictBaseUrl == "https://matrix.example.test"' > /dev/null
echo 'maubot and Ketesa HTTP servers passed'

if action configure-module "$(jq '.extensions.telegram={enabled:true}' "$work/extensions.json")" > "$work/invalid.json" 2>/dev/null; then
    echo 'Telegram accepted missing API credentials' >&2
    exit 1
fi
action get-configuration | jq -e '.extensions.telegram.enabled == false' >/dev/null
echo 'Invalid extension configuration did not replace the working settings'

# Exercise every bridge adapter against the local Synapse; no remote accounts are logged in.
curl -fsS -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
    --data '{"name":"NS8 moderation test"}' "$base/_matrix/client/v3/createRoom" > "$work/room.json"
room="$(jq -r '.room_id' "$work/room.json")"
curl -fsS -H "Authorization: Bearer $token" \
    "$base/_matrix/client/v3/rooms/$room/state/m.room.power_levels" | \
    jq '.users["@draupnir:example.test"]=100' > "$work/power-levels.json"
curl -fsS -X PUT -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
    --data-binary "@$work/power-levels.json" \
    "$base/_matrix/client/v3/rooms/$room/state/m.room.power_levels" > /dev/null
jq --arg room "$room" '. + {bridge_admin:"@recovery-admin:example.test"} |
    .extensions.discord={enabled:true} |
    .extensions.telegram={enabled:true,config:{network:{api_id:12345,api_hash:"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}} |
    .extensions.whatsapp={enabled:true} |
    .extensions.signal={enabled:true} |
    .extensions.heisenbridge={enabled:true} |
    .extensions.hookshot={enabled:true,host:"hookshot.example.test"} |
    .extensions.steam={enabled:true} |
    .extensions.postmoogle={enabled:true,config:{POSTMOOGLE_DOMAINS:"example.test",POSTMOOGLE_TLS_REQUIRED:false}} |
    .extensions.buscarron={enabled:true,host:"forms.example.test",config:{BUSCARRON_LIST:"contact",BUSCARRON_CONTACT_ROOM:$room}} |
    .extensions.draupnir={enabled:true,config:{managementRoom:$room,initialManager:"@recovery-admin:example.test"}}' \
    "$work/extensions.json" > "$work/all.json"
action configure-module "$(cat "$work/all.json")" > "$work/all-result.json"
curl -fsS -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
    --data '{"user_id":"@draupnir:example.test"}' "$base/_synapse/admin/v1/join/$room" > /dev/null
sleep 10
for service in discord telegram whatsapp signal heisenbridge hookshot steam postmoogle buscarron draupnir; do
    [[ "$(runagent -m "$module" podman inspect "matrix-$service" --format '{{.State.Running}}')" == true ]]
done
echo 'All bridge and bot containers started with their generated registrations/configuration'

# Persistent data and signing key survive the actual backup/restore hooks.
runagent -m "$module" podman exec matrix-postgres psql -U matrix -d synapse -v ON_ERROR_STOP=1 -c 'CREATE TABLE ns8_backup_probe(value text); INSERT INTO ns8_backup_probe VALUES ($$before$$);' > /dev/null
runagent -m "$module" podman exec matrix-maubot sh -c 'printf before > /data/plugins/ns8-backup-probe.txt'
signing_before="$(runagent -m "$module" podman exec matrix-synapse sha256sum /data/signing.key | cut -d' ' -f1)"
runagent -m "$module" module-dump-state
runagent -m "$module" podman exec matrix-postgres psql -U matrix -d synapse -v ON_ERROR_STOP=1 -c 'UPDATE ns8_backup_probe SET value=$$after$$;' > /dev/null
runagent -m "$module" podman exec matrix-postgres psql -U matrix -d synapse -v ON_ERROR_STOP=1 -c 'CREATE TABLE ns8_after_backup_probe(value text);' > /dev/null
runagent -m "$module" podman exec matrix-maubot sh -c 'printf after > /data/plugins/ns8-backup-probe.txt'
runagent -m "$module" podman exec matrix-maubot sh -c 'printf after > /data/plugins/ns8-after-backup-probe.txt'
runagent -m "$module" matrixctl restore > "$work/restore.json"
value="$(runagent -m "$module" podman exec matrix-postgres psql -U matrix -d synapse -Atc 'SELECT value FROM ns8_backup_probe;')"
[[ "$value" == before ]]
[[ "$(runagent -m "$module" podman exec matrix-postgres psql -U matrix -d synapse -Atc "SELECT to_regclass('ns8_after_backup_probe') IS NULL;")" == t ]]
[[ "$(runagent -m "$module" podman exec matrix-maubot cat /data/plugins/ns8-backup-probe.txt)" == before ]]
runagent -m "$module" podman exec matrix-maubot sh -c 'test ! -e /data/plugins/ns8-after-backup-probe.txt'
[[ "$(runagent -m "$module" podman exec matrix-synapse sha256sum /data/signing.key | cut -d' ' -f1)" == "$signing_before" ]]
echo 'Database, plugin data, credentials and server signing key survived restore'

# TURN and RTC can start with the advertised test VM IPv4 address.
node_ip="$(hostname -I | awk '{print $1}')"
jq --arg ip "$node_ip" '. + {rtc:{enabled:true,domain_name:"rtc.example.test",public_ip:$ip},turn:{enabled:true,domain_name:"turn.example.test",public_ip:$ip}}' "$work/all.json" > "$work/media.json"
action configure-module "$(cat "$work/media.json")" > "$work/media-result.json"
sleep 5
for service in turn livekit jwt; do
    [[ "$(runagent -m "$module" podman inspect "matrix-$service" --format '{{.State.Running}}')" == true ]]
done
action get-stack-status | jq -e '.ports | length == 6' > /dev/null
curl -fsS "$base/.well-known/matrix/client" | jq -e '."org.matrix.msc4143.rtc_foci"[0].type == "livekit"' > /dev/null
echo 'coturn, LiveKit and JWT service started; RTC discovery is available'

# Disabling components removes firewall exposure and stops their services.
action configure-module "$(jq '.rtc.enabled=false | .turn.enabled=false' "$work/media.json")" > "$work/disabled.json"
action get-stack-status | jq -e '.ports | length == 1' >/dev/null
action rotate-recovery-admin > "$work/rotated.json"
[[ "$(jq -r .password "$work/recovery.json")" != "$(jq -r .password "$work/rotated.json")" ]]
jq '{type:"m.login.password",identifier:{type:"m.id.user",user:.user},password:.password}' "$work/rotated.json" > "$work/login.json"
curl -fsS -H 'Content-Type: application/json' --data-binary "@$work/login.json" "$base/_matrix/client/v3/login" | jq -e '.access_token != null' > /dev/null
remove-module --no-preserve "$module"
module=""
echo 'Disable, administrator password rotation and module removal passed'
echo 'NS8 integration tests passed'
