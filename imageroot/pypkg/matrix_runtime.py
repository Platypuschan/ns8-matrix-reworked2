# SPDX-License-Identifier: AGPL-3.0-or-later
"""NS8 lifecycle and bounded Podman/systemd operations."""
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import matrix_config as configlib

ALL_SERVICES = ("postgres", "synapse", "gateway", "element") + configlib.EXTENSIONS + ("turn", "livekit", "jwt")
ALL_ROUTES = ("synapse", "discovery", "element", "ketesa", "maubot", "hookshot", "buscarron", "jwt", "livekit")
VOLUMES = ("synapse",) + tuple(k for k in configlib.EXTENSIONS if k != "ketesa")


class Runtime:
    def __init__(self, state=None, environ=None):
        self.environ = dict(os.environ if environ is None else environ)
        self.state = Path(state or self.environ.get("AGENT_STATE_DIR") or Path.cwd()).resolve()
        self.state.mkdir(parents=True, exist_ok=True)
        self.portmap = configlib.ports(self.environ)

    @contextmanager
    def lock(self):
        with (self.state / ".matrix.lock").open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def command(self, args, input=None, stdout=subprocess.PIPE, check=True, timeout=240):
        result = subprocess.run(args, input=input, stdout=stdout, stderr=subprocess.PIPE, text=True, timeout=timeout)
        if check and result.returncode:
            # Commands may consume passwords through stdin/env files: never echo them.
            raise RuntimeError("{} failed (exit {}); see the module journal".format(args[0], result.returncode))
        return result

    def systemd(self, *args, check=True):
        return self.command(["systemctl", "--user", *args], check=check, timeout=300)

    def active(self, name):
        return self.systemd("is-active", "matrix-" + name + ".service", check=False).stdout.strip() in ("active", "activating")

    def read_config(self):
        path = self.state / "config.json"
        return json.loads(path.read_text()) if path.exists() else configlib.defaults()

    def values(self):
        return configlib.secret_store(self.state)

    def image(self, name):
        if name == "synapse":
            return self.environ.get("MATRIX_REWORKED2_SYNAPSE_RUNTIME_IMAGE", configlib.IMAGES[name])
        return configlib.IMAGES[name]

    def container_plan(self, name):
        if name not in ALL_SERVICES and name != "compressor":
            raise ValueError("Unknown Matrix service")
        cfg = self.read_config()
        if name != "compressor" and name not in configlib.enabled_services(cfg):
            raise ValueError("Service is disabled")
        gen = self.state / "generated"
        args = ["podman", "run", "--rm", "--replace", "--name", "matrix-" + name,
                "--label", "ns8.matrix.service=" + name, "--security-opt", "no-new-privileges", "--user", "0:0",
                "--network", "host" if name == "livekit" else "slirp4netns:allow_host_loopback=true"]
        if name != "livekit":
            args += ["--add-host", "host.containers.internal:10.0.2.2"]
        args += ["--log-driver", "journald", "--log-opt", "tag=matrix-" + name]

        def publish(host, inner, proto="tcp", public=False):
            args.extend(["--publish", ("" if public else "127.0.0.1:") + str(host) + ":" + str(inner) + "/" + proto])

        def mount(source, target, options="ro,Z"):
            args.extend(["--volume", str(source) + ":" + target + ":" + options])

        def data(target):
            mount("matrix-" + name + "-data", target, "z")

        tail = []
        if name == "postgres":
            args += ["--env-file", str(gen / "postgres.env")]
            data("/var/lib/postgresql")
            publish(self.portmap["postgres"], 5432)
        elif name == "synapse":
            mount(gen / "synapse", "/config")
            data("/data")
            # The upstream entrypoint defaults to UID 991 even with --user 0.
            # Namespace UID 0 maps to the unprivileged NS8 module user, which
            # owns the private configuration and signing key.
            args += ["--env", "UID=0", "--env", "GID=0", "--env", "SYNAPSE_CONFIG_PATH=/config/homeserver.yaml"]
            publish(self.portmap["synapse"], 8008)
        elif name == "gateway":
            mount(gen / "nginx.conf", "/etc/nginx/conf.d/default.conf")
            publish(self.portmap[name], 8080)
        elif name == "element":
            mount(gen / "element.json", "/app/config.json")
            publish(self.portmap[name], 80)
        elif name in ("discord", "telegram", "whatsapp", "signal", "steam"):
            data("/app/data" if name == "steam" else "/data")
            mount(gen / name / "config.yaml", "/app/config/config.yaml" if name == "steam" else "/data/config.yaml")
            mount(gen / name / "registration.yaml", "/app/config/registration.yaml" if name == "steam" else "/data/registration.yaml")
            publish(self.portmap[name], 8080)
            if name == "steam":
                args += ["--entrypoint", "/app/steam"]
                tail = ["-c", "/app/config/config.yaml", "-r", "/app/config/registration.yaml", "--no-update"]
            else:
                # These images have a default CMD rather than ENTRYPOINT.
                # Their wrapper also edits config files and switches UID;
                # launch the bridge against the complete NS8-managed config.
                args += ["--entrypoint", "/usr/bin/mautrix-" + name, "--workdir", "/data"]
                tail = ["-c", "/data/config.yaml", "-r", "/data/registration.yaml", "--no-update"]
        elif name == "heisenbridge":
            data("/config")
            mount(gen / name / "registration.yaml", "/config/registration.yaml", "z")
            publish(self.portmap[name], 9898)
            tail = ["--config", "/config/registration.yaml", "--listen-address", "0.0.0.0", "--listen-port", "9898", "-o", cfg["bridge_admin"], "http://host.containers.internal:" + str(self.portmap["synapse"])]
        elif name == "hookshot":
            data("/data")
            mount(gen / name / "config.yaml", "/data/config.yml")
            mount(gen / name / "registration.yaml", "/data/registration.yml")
            mount(self.state / "hookshot-passkey.pem", "/data/passkey.pem")
            publish(self.portmap["hookshot_as"], 9993)
            publish(self.portmap[name], 9000)
        elif name == "maubot":
            data("/data")
            mount(gen / name / "config.yaml", "/config/config.yaml")
            publish(self.portmap[name], 29316)
            args += ["--entrypoint", "/bin/sh"]
            tail = ["-c", "mkdir -p /data/plugins /data/trash /data/dbs && exec python3 -m maubot -c /config/config.yaml --no-update"]
        elif name == "ketesa":
            mount(gen / name / "config.json", "/var/public/config.json")
            publish(self.portmap[name], 80)
        elif name == "draupnir":
            data("/data")
            mount(gen / name / "config.yaml", "/data/config/production.yaml")
            tail = ["bot", "--draupnir-config", "/data/config/production.yaml"]
        elif name in ("postmoogle", "buscarron"):
            data("/data")
            args += ["--env-file", str(gen / name / "config.env")]
            publish(self.portmap[name], 2525 if name == "postmoogle" else 8080, public=name == "postmoogle")
        elif name == "turn":
            mount(gen / "turn.conf", "/etc/coturn/turnserver.conf")
            publish(self.portmap[name], 3478, public=True)
            publish(self.portmap["turn_udp"], 3478, "udp", True)
            relay = "{}-{}".format(self.portmap["relay_start"], self.portmap["relay_end"])
            publish(relay, relay, "udp", True)
            tail = ["-c", "/etc/coturn/turnserver.conf"]
        elif name == "livekit":
            mount(gen / "livekit.yaml", "/etc/livekit.yaml")
            tail = ["--config", "/etc/livekit.yaml"]
        elif name == "jwt":
            args += ["--env-file", str(gen / "jwt.env")]
            publish(self.portmap[name], 8080)
        elif name == "compressor":
            args += ["--env-file", str(gen / "compressor.env"), "--entrypoint", "/bin/sh"]
            tail = ["-c", 'exec synapse_auto_compressor -p "$POSTGRES_LOCATION" -c 500 -n 100']
        return args + [self.image(name)] + tail

    def run_container(self, name):
        os.execvp("podman", self.container_plan(name))

    def stop_container(self, name):
        if name not in ALL_SERVICES and name != "compressor":
            raise ValueError("Unknown Matrix service")
        self.command(["podman", "stop", "--ignore", "-t", "30", "matrix-" + name], timeout=60)

    def prepare_synapse(self):
        source = """import os
from signedjson.key import generate_signing_key, encode_signing_key_base64
path = '/data/signing.key'
if not os.path.exists(path):
    key = generate_signing_key('a_' + os.urandom(3).hex())
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as file:
        file.write('%s %s %s\\n' % (key.alg, key.version, encode_signing_key_base64(key)))
"""
        self.command(["podman", "run", "--rm", "--network", "none", "--user", "0:0", "--volume", "matrix-synapse-data:/data:z", "--entrypoint", "python", self.image("synapse"), "-c", source])

    def sql(self, text, db="postgres"):
        return self.command(["podman", "exec", "-i", "matrix-postgres", "psql", "-U", "matrix", "-d", db, "-v", "ON_ERROR_STOP=1", "-At"], input=text).stdout.strip()

    def wait_database(self):
        for _ in range(60):
            result = self.command(["podman", "exec", "matrix-postgres", "pg_isready", "-U", "matrix", "-d", "postgres"], check=False, timeout=10)
            if result.returncode == 0:
                return
            time.sleep(2)
        raise RuntimeError("PostgreSQL did not become ready within 120 seconds")

    def ensure_databases(self):
        self.wait_database()
        values = self.values()
        for name in configlib.DATABASES:
            if not self.sql("SELECT 1 FROM pg_roles WHERE rolname='" + name + "';"):
                self.sql("CREATE ROLE " + name + " LOGIN PASSWORD '" + values["db_" + name] + "';")
            if not self.sql("SELECT 1 FROM pg_database WHERE datname='" + name + "';"):
                self.sql("CREATE DATABASE " + name + " OWNER " + name + " ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0;")

    def http(self, path, data=None, token=None, method=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = Request("http://127.0.0.1:" + str(self.portmap["synapse"]) + path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
        try:
            with urlopen(req, timeout=10) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                result = json.load(error)
            except ValueError:
                result = {}
            if result.get("errcode") == "M_USER_IN_USE":
                return result
            raise RuntimeError("Synapse API request failed (HTTP {})".format(error.code)) from None

    def wait_synapse(self):
        for _ in range(90):
            try:
                self.http("/_matrix/client/versions")
                return
            except (OSError, URLError, RuntimeError):
                time.sleep(2)
        raise RuntimeError("Synapse did not become ready within 180 seconds")

    def register(self, username, password, admin=False):
        nonce = self.http("/_synapse/admin/v1/register")["nonce"]
        content = "\0".join((nonce, username, password, "admin" if admin else "notadmin"))
        mac = hmac.new(self.values()["registration"].encode(), content.encode(), hashlib.sha1).hexdigest()
        return self.http("/_synapse/admin/v1/register", {"nonce": nonce, "username": username, "password": password, "admin": admin, "mac": mac})

    def login(self, username, password):
        return self.http("/_matrix/client/v3/login", {"type": "m.login.password", "identifier": {"type": "m.id.user", "user": username}, "password": password, "initial_device_display_name": "NS8 Matrix management"})["access_token"]

    def bootstrap(self):
        cfg, values = self.read_config(), self.values()
        self.register("recovery-admin", values["recovery_admin"], admin=True)
        for name in ("postmoogle", "buscarron", "draupnir"):
            if not cfg["extensions"][name]["enabled"]:
                continue
            self.register(name, values[name + "_password"])
            if name == "draupnir" and not cfg["extensions"][name]["config"].get("accessToken") and not values.get("draupnir_token"):
                values["draupnir_token"] = self.login(name, values[name + "_password"])
                configlib.write(self.state / "secrets.json", values)
                configlib.write(self.state / "generated/draupnir/config.yaml", configlib.extension_config(name, cfg, values, self.portmap))
        if cfg["extensions"]["hookshot"]["enabled"] and not (self.state / "hookshot-passkey.pem").exists():
            temporary = self.state / (".hookshot-key-" + secrets.token_hex(8))
            try:
                self.command(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:4096", "-out", str(temporary)])
                temporary.chmod(0o600)
                os.replace(temporary, self.state / "hookshot-passkey.pem")
            finally:
                temporary.unlink(missing_ok=True)

    def discover(self, cfg):
        import agent
        from agent.ldapproxy import Ldapproxy
        agent.bind_user_domains([cfg["ldap_domain"]] if cfg["ldap_domain"] else [])
        ldap = Ldapproxy().get_domain(cfg["ldap_domain"]) if cfg["ldap_domain"] else None
        smtp = agent.get_smarthost_settings(agent.redis_connect(use_replica=True)) if cfg["use_smarthost"] else None
        return ldap, smtp

    def remove_firewall(self):
        import agent.tasks
        name = self.environ["MODULE_ID"]
        result = agent.tasks.run(
            agent_id="node/" + self.environ["NODE_ID"], action="remove-public-service",
            data={"service": name}, extra={"isNotificationHidden": True})
        # Core's remove action fails if no public ports were ever enabled.
        # Treat only this service's explicit not-found result as success.
        missing = re.search(r"\bINVALID_SERVICE:\s*" + re.escape(name) + r"(?![\w.-])", result.get("error", ""))
        return result["exit_code"] == 0 or bool(missing)

    def setup_routes(self, cfg):
        import agent
        import agent.tasks
        traefik = agent.resolve_agent_id("traefik@node")
        if traefik is None:
            raise RuntimeError("NS8 Traefik is unavailable on this node")
        wanted = configlib.routes(cfg, self.portmap)
        for name in ALL_ROUTES:
            data = {"instance": self.environ["MODULE_ID"] + "-" + name}
            action = "delete-route"
            if name in wanted:
                item = dict(wanted[name])
                port = item.pop("port")
                data.update(item, url="http://127.0.0.1:" + str(port), http2https=True, lets_encrypt=cfg["lets_encrypt"])
                action = "set-route"
            result = agent.tasks.run(agent_id=traefik, action=action, data=data)
            if result["exit_code"]:
                raise RuntimeError("Traefik route operation failed: " + name)
        public = configlib.firewall_ports(cfg, self.portmap)
        ok = agent.add_public_service(self.environ["MODULE_ID"], public, replace_ports=True) if public else self.remove_firewall()
        if ok is False:
            raise RuntimeError("NS8 firewall update failed")

    def reconcile(self):
        cfg = self.read_config()
        desired = configlib.enabled_services(cfg)
        self.systemd("daemon-reload")
        self.systemd("enable", "matrix.target", "matrix-cleanup.timer")
        if (self.state / "restart-required").exists():
            for name in reversed(ALL_SERVICES):
                if name != "postgres" and self.active(name):
                    self.systemd("stop", "matrix-" + name + ".service")
        for name in ALL_SERVICES:
            if name not in desired:
                self.systemd("disable", "--now", "matrix-" + name + ".service")
        self.systemd("enable", "--now", "matrix-postgres.service")
        self.ensure_databases()
        for name in ("synapse", "gateway"):
            self.systemd("enable", "--now", "matrix-" + name + ".service")
        self.wait_synapse()
        self.bootstrap()
        for name in desired:
            if name not in ("postgres", "synapse", "gateway"):
                self.systemd("enable", "--now", "matrix-" + name + ".service")
        self.systemd("enable" if cfg["auto_compressor"] else "disable", "--now", "matrix-compressor.timer")
        self.systemd("start", "matrix-cleanup.timer", "matrix.target")
        (self.state / "restart-required").unlink(missing_ok=True)

    def configure(self, request):
        with self.lock():
            old = self.read_config()
            cfg = configlib.validate(request, old)
            ldap, smtp = self.discover(cfg)
            values = self.values()
            with tempfile.TemporaryDirectory(prefix=".matrix-render-", dir=self.state) as temporary:
                configlib.render(temporary, cfg, values, self.portmap, ldap, smtp)
                changed = old != cfg
                for source in sorted((Path(temporary) / "generated").rglob("*")):
                    if source.is_file():
                        target = self.state / source.relative_to(temporary)
                        changed = configlib.write(target, source.read_text(), source.stat().st_mode & 0o777) or changed
                if changed:
                    configlib.write(self.state / "restart-required", "configuration changed\n")
                configlib.write(self.state / "config.json", cfg)
            self.setup_routes(cfg)
            self.reconcile()
        return {"configured": True, "changed": changed}

    def recovery(self, rotate=False):
        with self.lock():
            cfg, values = self.read_config(), self.values()
            if not cfg["server_name"]:
                raise ValueError("Configure the homeserver first")
            user = "@recovery-admin:" + cfg["server_name"]
            if rotate:
                token = self.login(user, values["recovery_admin"])
                password = secrets.token_urlsafe(36)
                self.http("/_synapse/admin/v1/reset_password/" + quote(user, safe=""), {"new_password": password, "logout_devices": True}, token=token)
                values["recovery_admin"] = password
                configlib.write(self.state / "secrets.json", values)
            return {"user": user, "password": values["recovery_admin"], "maubot_user": "recovery-admin", "maubot_password": values["maubot_admin"] if cfg["extensions"]["maubot"]["enabled"] else ""}

    def snapshot(self):
        """Freeze all writers, dump PG databases and copy data before resuming."""
        with self.lock():
            if not self.read_config()["server_name"]:
                configlib.write(self.state / "backup/manifest.json", {"configured": False})
                return
            running = [name for name in ALL_SERVICES if name != "postgres" and self.active(name)]
            compressor = self.active("compressor")
            timer = self.systemd("is-active", "matrix-compressor.timer", check=False).returncode == 0
            temporary = Path(tempfile.mkdtemp(prefix=".matrix-backup-", dir=self.state))
            try:
                self.systemd("stop", "matrix-compressor.timer", "matrix-compressor.service")
                for name in reversed(running):
                    self.systemd("stop", "matrix-" + name + ".service")
                databases = []
                for name in configlib.DATABASES:
                    if self.sql("SELECT 1 FROM pg_database WHERE datname='" + name + "';"):
                        with (temporary / (name + ".pgdump")).open("w") as stream:
                            self.command(["podman", "exec", "matrix-postgres", "pg_dump", "-U", "matrix", "-Fc", "-d", name], stdout=stream)
                        databases.append(name)
                volumes = []
                for name in VOLUMES:
                    volume = "matrix-" + name + "-data"
                    if self.command(["podman", "volume", "exists", volume], check=False).returncode:
                        continue
                    self.command(["podman", "run", "--rm", "--network", "none", "--user", "0:0", "--volume", volume + ":/source:ro,z", "--volume", str(temporary) + ":/backup:z", self.image("utility"), "tar", "czf", "/backup/" + name + ".tgz", "-C", "/source", "."], timeout=3600)
                    volumes.append(name)
                configlib.write(temporary / "manifest.json", {"configured": True, "format": 1, "databases": databases, "volumes": volumes})
                for filename in ("config.json", "secrets.json", "hookshot-passkey.pem"):
                    source = self.state / filename
                    if source.exists():
                        shutil.copy2(source, temporary / filename)
                backup = self.state / "backup"
                if backup.exists():
                    shutil.rmtree(backup)
                os.replace(temporary, backup)
            finally:
                shutil.rmtree(temporary, ignore_errors=True)
                resume_errors = []
                for name in running:
                    try:
                        self.systemd("start", "matrix-" + name + ".service")
                    except RuntimeError:
                        resume_errors.append(name)
                if timer:
                    try:
                        self.systemd("start", "matrix-compressor.timer")
                    except RuntimeError:
                        resume_errors.append("compressor timer")
                if resume_errors:
                    raise RuntimeError("Backup services could not resume: " + ", ".join(resume_errors))
                # Interrupted compressor jobs retry at the next daily timer, not during resume.
                if compressor:
                    print("Compressor was stopped for the backup; its daily timer will retry.", file=__import__("sys").stderr)

    def cleanup_snapshot(self):
        with self.lock():
            shutil.rmtree(self.state / "backup", ignore_errors=True)

    def restore(self):
        backup = self.state / "backup"
        manifest = json.loads((backup / "manifest.json").read_text()) if (backup / "manifest.json").exists() else None
        if manifest is None:
            raise RuntimeError("The Matrix backup manifest is missing")
        if not manifest.get("configured"):
            return {"configured": False}
        if manifest.get("format") != 1 or set(manifest["volumes"]) - set(VOLUMES) or set(manifest["databases"]) - set(configlib.DATABASES):
            raise ValueError("Unsupported Matrix backup format")
        for name, suffix in [(name, ".tgz") for name in manifest["volumes"]] + [(name, ".pgdump") for name in manifest["databases"]]:
            if not (backup / (name + suffix)).is_file():
                raise RuntimeError("The Matrix backup is incomplete: " + name)
        with self.lock():
            self.systemd("stop", "matrix-compressor.timer", "matrix-compressor.service")
            for filename in ("config.json", "secrets.json", "hookshot-passkey.pem"):
                source = backup / filename
                if source.exists():
                    configlib.write(self.state / filename, source.read_text())
            cfg = self.read_config()
            for name in reversed(ALL_SERVICES):
                if self.active(name):
                    self.systemd("stop", "matrix-" + name + ".service")
            for name in manifest["volumes"]:
                volume = "matrix-" + name + "-data"
                if self.command(["podman", "volume", "exists", volume], check=False).returncode == 0:
                    self.command(["podman", "volume", "rm", volume])
                self.command(["podman", "volume", "create", volume])
                self.command(["podman", "run", "--rm", "--network", "none", "--user", "0:0", "--volume", volume + ":/dest:z", "--volume", str(backup) + ":/backup:ro,z", self.image("utility"), "tar", "xzf", "/backup/" + name + ".tgz", "-C", "/dest"], timeout=3600)
            # Regenerate node-specific ports and LDAP/SMTP bindings before opening traffic.
            ldap, smtp = self.discover(cfg)
            configlib.render(self.state, cfg, self.values(), self.portmap, ldap, smtp)
            self.systemd("daemon-reload")
            self.systemd("start", "matrix-postgres.service")
            self.wait_database()
            for name in manifest["databases"]:
                self.sql("DROP DATABASE IF EXISTS " + name + ";")
            self.ensure_databases()
            for name in manifest["databases"]:
                with (backup / (name + ".pgdump")).open("rb") as stream:
                    result = subprocess.run(["podman", "exec", "-i", "matrix-postgres", "pg_restore", "-U", "matrix", "-d", name, "--clean", "--if-exists", "--exit-on-error"], stdin=stream, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=3600)
                if result.returncode:
                    raise RuntimeError("PostgreSQL restore failed for " + name)
            configlib.write(self.state / "restart-required", "restored\n")
        self.configure(cfg)
        self.cleanup_snapshot()
        return {"restored": True}

    def destroy(self):
        import agent
        import agent.tasks
        errors = []
        # Firewall cleanup still runs if Traefik or one of the routes is unavailable.
        try:
            if self.remove_firewall() is False:
                errors.append("firewall")
        except Exception:
            errors.append("firewall")
        traefik = agent.resolve_agent_id("traefik@node")
        if traefik:
            for name in ALL_ROUTES:
                try:
                    result = agent.tasks.run(agent_id=traefik, action="delete-route", data={"instance": self.environ["MODULE_ID"] + "-" + name})
                    if result["exit_code"]:
                        errors.append(name)
                except Exception:
                    errors.append(name)
        if errors:
            raise RuntimeError("NS8 cleanup failed: " + ", ".join(errors))

    def cleanup(self):
        with self.lock():
            containers = self.command(["podman", "ps", "--all", "--format", "json"]).stdout
            known = {"matrix-" + name for name in ALL_SERVICES + ("compressor",)}
            for item in json.loads(containers):
                names = item.get("Names", [])
                if isinstance(names, str):
                    names = [names]
                for name in set(names) & known:
                    if item.get("State", "").lower() in ("exited", "created", "stopped"):
                        self.command(["podman", "rm", "--ignore", name])
            # No global prune, volume removal, media deletion or DB manipulation.
        return {"cleaned": True}

    def get_configuration(self):
        cfg = self.read_config()
        result = configlib.public_config(cfg)
        result.update(configured=bool(cfg["server_name"]), ports=self.portmap)
        try:
            from agent.ldapproxy import Ldapproxy
            result["domains_list"] = [{"name": n, "label": n, "value": n} for n in Ldapproxy().get_domains_list()]
        except Exception:
            result["domains_list"] = []
        return result

    def extension_settings(self, name):
        if name == "synapse":
            return {"config": self.read_config()["synapse_extra"], "defaults": {}}
        if name not in configlib.EXTENSIONS:
            raise ValueError("Unknown extension")
        return {"config": self.read_config()["extensions"][name]["config"], "defaults": configlib.stock(name)}

    def status(self):
        cfg = self.read_config()
        links = [{'name': name, 'url': 'https://' + data['host']} for name, data in configlib.routes(cfg, self.portmap).items() if name not in ('discovery', 'livekit') and data['host']]
        return {'configured': bool(cfg['server_name']), 'services': [{'name': name, 'state': self.systemd('is-active', 'matrix-' + name + '.service', check=False).stdout.strip()} for name in configlib.enabled_services(cfg)] if cfg['server_name'] else [], 'links': links, 'ports': configlib.firewall_ports(cfg, self.portmap), 'restart_pending': (self.state / 'restart-required').exists()}
