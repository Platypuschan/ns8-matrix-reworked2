# Component choices

These choices resolve the alternatives/question marks in the initial request. Optional extensions are disabled until configured.

| Candidate | Choice and reason |
| --- | --- |
| Synapse | Included, with the requested authentication providers. |
| Element Web | Included and optional if another Matrix client is used. |
| PostgreSQL | Included. Synapse and database-backed bridges get separate databases and login roles. |
| Traefik / Let's Encrypt | Use NS8's existing reverse proxy and certificate manager. A second instance would compete for the same HTTP ports. |
| Exim | Synapse uses the NS8 smarthost. Postmoogle accepts an existing SMTP relay for incoming/outgoing mail. No additional mail server is installed. |
| coturn | Optional for classic calls. Authenticated UDP/TCP TURN; no embedded TLS certificate management. |
| MatrixRTC | Optional LiveKit Server + JWT service, discovery/configuration for current Element clients, host-network media transport. |
| Jitsi | Integration with an existing Jitsi deployment through Element's preferred domain. A second hosted conferencing stack was not selected. |
| matrix-media-repo | Not included in this first implementation. Synapse's persistent media store already covers the single-homeserver setup. |
| Shared Secret Auth | Included as a separate optional Synapse password-provider module. Its secret is kept private; ordinary password login uses LDAP/local credentials. |
| LDAP3 | Included, using the NS8 local LDAP proxy. AD uses sAMAccountName and supports a custom LDAP filter. |
| Discord alternatives | mautrix-discord selected for account puppeting. This is a text bridge; the separately existing Discord voice bridge remains a different project. |
| Telegram / WhatsApp / Signal | Current mautrix bridges. Modern automatic double-puppeting uses a shared, non-exclusive appservice registration, independent of Shared Secret Auth. |
| IRC alternatives | Heisenbridge selected for its bouncer-style operation and configuration through Matrix. |
| Hookshot | Included for feeds/webhooks and additional upstream integrations. |
| Steam alternatives | The current Matrix Steam Bridge selected over the older mx-puppet implementation. |
| Postmoogle | Included as an email bot/SMTP listener with an allocated public port. It is not an appservice. |
| maubot | Included, including the plugin-library additions of the existing maubot module. |
| Draupnir / Mjolnir / Meowlnir | Draupnir selected. Room membership and moderation permissions are an administrator's setup step. |
| Buscarron | Included, configured with its environment variables and a public HTTPS endpoint. |
| MAS | Not included in this first implementation. MAS replaces the authentication flow and cannot simply be enabled alongside the requested direct Synapse LDAP/password-provider setup. |
| Ketesa | Included as an optional administrator web application, restricted to this homeserver. |
| System cleanup | A weekly timer removes stopped module containers, with an explicit list of names. It does not prune volumes or host-wide resources. |
| Borg | Use standard NS8/Restic backups instead of a second backup scheduler. |
| synapse_auto_compressor | Optional daily bounded state compression. The backup hook stops it before snapshotting. |
| Matrix Corporal | Not included in this first implementation; no external policy authority or automated membership policy was specified. |

## Stable state

The Matrix identity domain, server signing key, appservice tokens, database credentials, bot passwords and Hookshot passkey persist across configuration changes and backups. Web hostnames can change; Matrix identity cannot. Data is retained when an extension is disabled.

Only registration IDs and namespaces from the chosen adapters are installed into Synapse. Bridge processes and callback listeners are stopped when disabled. Reconfiguring the same settings does not restart services. Failed configuration leaves a restart marker so the next save can finish the operation.

## Limits of the initial tests

Automated tests use a local homeserver and disposable NS8 nodes. They can verify image/config compatibility, HTTP endpoints, token registration, persistence and lifecycle behavior. Authenticating actual remote accounts, IRC networks, GitHub apps, SMTP routing and NAT/firewall behavior require the corresponding real accounts and network setup. The Steam/mautrix bridges inherit any remote-service restrictions of their upstream projects.
