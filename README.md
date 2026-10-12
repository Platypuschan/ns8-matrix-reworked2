# Matrix Reworked 2 for NethServer 8

A Synapse homeserver with Element Web, NS8 account-provider integration and optional bridges, bots and calling services. Enable the parts you need from the application settings.

This is the initial implementation. It is being tested in disposable NS8 nodes; no stable release or catalog entry has been published yet. Real remote-account logins and calls across a router still need a live test.

## Included components

| Purpose | Component |
| --- | --- |
| Homeserver and database | Synapse, PostgreSQL |
| Browser client | Element Web |
| Authentication | NS8 LDAP/AD, local accounts, Shared Secret Auth |
| Calls | Optional coturn and MatrixRTC (LiveKit Server + JWT service) |
| Messaging bridges | mautrix-discord, mautrix-telegram, mautrix-whatsapp, mautrix-signal |
| Other bridges | Heisenbridge (IRC), Matrix Hookshot, Matrix Steam Bridge, Postmoogle |
| Bots | maubot, Draupnir, Buscarron |
| Administration | Ketesa, local recovery administrator |
| Maintenance | NS8 backups, weekly container cleanup, optional daily Synapse state compression |

NS8 supplies Traefik, HTTPS certificates and backups. Synapse stores media in its persistent data volume and can use the NS8 email smarthost. An existing Jitsi server can be selected in Element settings. The reasons for the component choices are in [docs/components.md](docs/components.md).

## Test installation

Use a disposable NS8 node with Core **3.20.1 or newer**. The CI branch image is a development build:

```sh
add-module ghcr.io/platypuschan/matrix-reworked2:initial-module 1
```

After a stable release is published, install its numbered tag instead of a branch or `latest`. The intended first version is `0.1.0`.

Open the application settings and set:

1. **Matrix identity domain**: the domain in user IDs, for example `@alice:example.com`. It cannot change after setup.
2. **Synapse domain**: for example `matrix.example.com`.
3. **Element Web domain**: for example `chat.example.com`, or leave empty to use other Matrix clients.
4. **LDAP domain**: select the NS8 account provider, or leave empty for local Matrix accounts.
5. **Certificates**: request them through NS8 when the DNS names point to this node and are publicly reachable.

When the identity domain differs from the Synapse domain, the module adds only `/.well-known/matrix` routes to the identity domain. Federation is delegated to HTTPS port 443. Existing clients can discover the server from their Matrix user ID.

The **Recovery administrator** section reveals a generated local administrator password. It also shows the separate maubot management password when maubot is enabled. This account works independently of LDAP. Rotating its Matrix password logs out its devices.

## Extensions

Set the full Matrix ID of the bridge administrator, then enable a bridge. Databases, registrations, callback addresses and tokens are generated automatically. Connect your remote accounts by messaging the corresponding bridge bot in Element; see the [mautrix usage documentation](https://docs.mau.fi/bridges/general/using-bridges.html).

Each extension has a JSON editor for additional upstream settings. JSON is accepted by the applications' YAML readers. You can show the bundled upstream defaults next to the editor. Addresses, database credentials and appservice tokens remain managed by this module. Settings for a disabled extension and its persistent data are retained.

Some extensions need additional configuration:

- **Telegram**: `network.api_id` and `network.api_hash` from [my.telegram.org](https://my.telegram.org).
- **Draupnir**: `managementRoom`; invite `@draupnir:<identity-domain>` and grant the bot the required room power levels.
- **Buscarron**: `BUSCARRON_LIST` and each form's `BUSCARRON_<NAME>_ROOM`. Its public HTTPS endpoint accepts form submissions.
- **Postmoogle**: `POSTMOOGLE_DOMAINS` and, if needed, SMTP relay settings. Deliver incoming mail through an existing SMTP relay to the allocated port shown on the Status page. This module does not bind port 25 or manage DNS MX records.
- **Hookshot**: generic webhooks and feeds work out of the box. GitHub/GitLab and other integrations need their upstream credentials/settings. Private key files must be provisioned separately before enabling integrations that reference them.

maubot includes the plugin libraries from the existing `ns8-maubot` runtime: BeautifulSoup, emoji, APScheduler, cron-descriptor, matplotlib, NumPy and pillow-heif. Upload plugins through maubot's management interface.

## Calls and network

MatrixRTC serves current Element clients. coturn supports classic Matrix calls. They are independent options; enabling one does not automatically enable the other.

Set the reachable IPv4 address of this node for the enabled media services. Behind NAT, forward the allocated public media ports shown on the Status page **without changing their port numbers**. The node firewall is updated automatically. coturn uses authenticated UDP/TCP TURN and 64 UDP relay ports; TURN over TLS is not configured. LiveKit uses one UDP mux port and one TCP fallback port.

The module reserves 20 TCP and 66 UDP ports to avoid fixed-port conflicts. Only enabled media services and the optional Postmoogle SMTP listener are opened publicly. Database, appservice callbacks and administrative backend ports listen on `127.0.0.1`; web applications use NS8 Traefik. Containers use rootless Podman with `slirp4netns`; LiveKit uses the host network for its media candidates.

## Backups and maintenance

Configure backups from the standard NS8 backup screen. The dump hook stops active writers, takes PostgreSQL dumps and archives persistent volumes together with configuration, secrets and the signing key, then resumes the services. Backups include disabled extensions' existing data. PostgreSQL live storage files are excluded. Restore recreates databases and ports, rediscovers the account provider/smarthost and preserves Matrix identity and sessions.

The weekly cleanup removes only stopped containers belonging to this module. It never prunes host-wide containers/images/volumes or deletes messages/media. The optional state compressor runs daily with bounded batches.

## Development

```sh
python3 tests/validate_repo.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
cd ui
corepack yarn install --immutable
corepack yarn lint --no-fix
corepack yarn build
```

`build-images.sh` creates the Synapse/maubot runtime images and the NS8 module image using Buildah. CI builds branch images and tests installation, all component starts, idempotent configuration, backup/restore, password rotation and removal on Rocky 9 and Debian 13. It does not sign in to real Discord/Telegram/WhatsApp/Signal/Steam accounts or prove end-to-end calls.

References: [NethServer/ns8-matrix](https://github.com/NethServer/ns8-matrix), [matrix-docker-ansible-deploy](https://github.com/spantaleev/matrix-docker-ansible-deploy). License and attribution details are in [THIRD_PARTY.md](THIRD_PARTY.md).
