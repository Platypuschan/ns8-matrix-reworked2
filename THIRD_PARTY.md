# Sources and licenses

The new module implementation is licensed under **AGPL-3.0-or-later** (see LICENSE).

- The UI shell, public logo, styles and NS8 build/lifecycle conventions derive from [NethServer/ns8-matrix](https://github.com/NethServer/ns8-matrix), commit `7ec27859cc023f66169f238448ac7dcdb1f2b185`, GPL-3.0-or-later. Original source notices are retained; the GPL text is in LICENSE.NethServer.
- The bundled JSON configuration defaults derive from component templates in [matrix-docker-ansible-deploy](https://github.com/spantaleev/matrix-docker-ansible-deploy), commit `87fcbb8aa59a02f73a89b09d0c304cc3c11ab85d`, AGPL-3.0-or-later. The templates were rendered with disabled relay modes, local development addresses and no credentials, then adapted by the module at runtime. Credits include Slavi Pantaleev, Nikita Chernyi, Julian-Samuel Gebühr, Stuart Mumford, Suguru Hirahara and the component-role contributors.
- `runtime/synapse/shared_secret_authenticator.py` is an unmodified copy from [devture/matrix-synapse-shared-secret-auth](https://github.com/devture/matrix-synapse-shared-secret-auth), version 2.0.2, commit `6e959f3073d9a3d6a4bc65215f186d3b519dec84`. Its upstream license is retained in `runtime/synapse/LICENSE.shared-secret-auth`.
- The maubot runtime recipe and version-check script derive from [Platypuschan/ns8-maubot](https://github.com/Platypuschan/ns8-maubot), commit `814617bd3491a6a45a6ce339b011304908d58d22`, GPL-3.0-or-later. The runtime image source label was changed to this repository.
- maubot's bundled defaults are converted from its [v0.6.0 example configuration](https://github.com/maubot/maubot/blob/v0.6.0/maubot/example-config.yaml), AGPL-3.0-or-later, matching the pinned runtime image. Deployment paths and credentials are overlaid by this module.

Containerized applications remain under their upstream licenses. Their source repositories and documentation are linked from the component list and the reference playbook. The module does not bundle their source code or change their application licenses.
