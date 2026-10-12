# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure configuration, registrations and container plans (no NS8 imports)."""
import copy
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
IMAGES = json.loads((ROOT / "images.json").read_text())
BRIDGES = ("discord", "telegram", "whatsapp", "signal", "heisenbridge", "hookshot", "steam")
EXTENSIONS = BRIDGES + ("postmoogle", "maubot", "draupnir", "buscarron", "ketesa")
DATABASES = ("synapse", "discord", "telegram", "whatsapp", "signal", "steam", "postmoogle", "buscarron")
BOT_NAMES = {k: k + "bot" for k in BRIDGES}
BOT_NAMES.update(heisenbridge="heisenbridge", hookshot="hookshot")
PREFIXES = {k: k + "_" for k in BRIDGES}
PREFIXES["heisenbridge"] = "hbirc_"
TCP_NAMES = ("gateway", "element", "ketesa", "maubot", "hookshot", "buscarron", "jwt", "livekit", "turn", "livekit_tcp", "postmoogle", "postgres", "synapse", "discord", "telegram", "whatsapp", "signal", "heisenbridge", "hookshot_as", "steam")
HOST_EXTENSIONS = ("ketesa", "maubot", "hookshot", "buscarron")
RESERVED_SYNAPSE = {"server_name", "public_baseurl", "listeners", "database", "media_store_path", "signing_key_path", "log_config", "app_service_config_files", "modules", "password_providers", "password_config", "enable_registration", "registration_requires_token", "enable_registration_without_verification", "registration_shared_secret", "macaroon_secret_key", "form_secret", "turn_uris", "turn_shared_secret", "matrix_rtc", "extra_well_known_client_content"}


def defaults():
    return {
        "server_name": "", "synapse_domain_name": "", "element_domain_name": "",
        "lets_encrypt": False, "federation": True, "enable_registration": False,
        "ldap_domain": "", "ldap_filter": "", "use_smarthost": False,
        "mail_from": "", "shared_secret_auth": True, "bridge_admin": "",
        "jitsi_domain_name": "", "synapse_extra": {}, "auto_compressor": False,
        "turn": {"enabled": False, "domain_name": "", "public_ip": ""},
        "rtc": {"enabled": False, "domain_name": "", "public_ip": ""},
        "extensions": {k: {"enabled": False, "host": "", "config": {}} for k in EXTENSIONS},
    }


def merge(base, extra):
    result = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def hostname(value, field, required=False):
    if not isinstance(value, str) or (required and not value):
        raise ValueError(field + ": a DNS name is required")
    if not value:
        return
    if len(value) > 253 or "." not in value or any(
        not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", p)
        for p in value.split(".")
    ):
        raise ValueError(field + ": enter a DNS name without scheme, port or path")


def validate(request, old=None):
    if not isinstance(request, dict) or set(request) - set(defaults()):
        raise ValueError("configuration: unknown field or invalid object")
    config = merge(old or defaults(), request)
    for field in ("server_name", "synapse_domain_name", "element_domain_name", "jitsi_domain_name"):
        hostname(config[field], field, required=field in ("server_name", "synapse_domain_name"))
    if old and old.get("server_name") and old["server_name"] != config["server_name"]:
        raise ValueError("server_name: cannot change the identity of an existing homeserver")
    for field in ("lets_encrypt", "federation", "enable_registration", "use_smarthost", "shared_secret_auth", "auto_compressor"):
        if not isinstance(config[field], bool):
            raise ValueError(field + ": expected a boolean")
    for field in ("ldap_domain", "ldap_filter", "mail_from", "bridge_admin"):
        if not isinstance(config[field], str) or len(config[field]) > 4096 or "\x00" in config[field]:
            raise ValueError(field + ": invalid text")
    if config["mail_from"] and not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", config["mail_from"]):
        raise ValueError("mail_from: enter a sender email address")
    if not isinstance(config["synapse_extra"], dict) or set(config["synapse_extra"]) & RESERVED_SYNAPSE:
        raise ValueError("synapse_extra: infrastructure and authentication keys are managed by NS8")
    if len(json.dumps(config["synapse_extra"])) > 262144:
        raise ValueError("synapse_extra: configuration exceeds 256 KiB")
    for name in ("turn", "rtc"):
        part = config[name]
        if not isinstance(part, dict) or set(part) != {"enabled", "domain_name", "public_ip"} or not isinstance(part["enabled"], bool):
            raise ValueError(name + ": invalid configuration")
        hostname(part["domain_name"], name + ".domain_name", part["enabled"])
        if part["public_ip"]:
            try:
                ipaddress.IPv4Address(part["public_ip"])
            except (ValueError, TypeError):
                raise ValueError(name + ".public_ip: enter the node's reachable IPv4 address") from None
        if part["enabled"] and not part["public_ip"]:
            raise ValueError(name + ".public_ip: required for advertised media candidates")
    if not isinstance(config["extensions"], dict) or set(config["extensions"]) != set(EXTENSIONS):
        raise ValueError("extensions: unknown extension")
    for name, part in config["extensions"].items():
        if not isinstance(part, dict) or set(part) != {"enabled", "host", "config"} or not isinstance(part["enabled"], bool) or not isinstance(part["config"], dict):
            raise ValueError("extensions." + name + ": invalid configuration")
        if len(json.dumps(part["config"])) > 262144:
            raise ValueError("extensions." + name + ": configuration exceeds 256 KiB")
        hostname(part["host"], name + ".host", part["enabled"] and name in HOST_EXTENSIONS)
        if part["enabled"]:
            if name in BRIDGES and not re.fullmatch(r"@[^:\s]+:" + re.escape(config["server_name"]), config["bridge_admin"]):
                raise ValueError("bridge_admin: a local Matrix user ID is required for bridges")
            if name == "telegram":
                network = part["config"].get("network", {})
                if not isinstance(network, dict) or not isinstance(network.get("api_id"), int) or isinstance(network.get("api_id"), bool) or network["api_id"] <= 0 or not re.fullmatch(r"[a-fA-F0-9]{32}", str(network.get("api_hash", ""))):
                    raise ValueError("telegram.config.network: api_id and api_hash from my.telegram.org are required")
            if name == "draupnir" and not re.fullmatch(r"[!#][^:\s]+:[^\s]+", str(part["config"].get("managementRoom", ""))):
                raise ValueError("draupnir.config.managementRoom: a management room ID or alias is required")
            if name == "buscarron" and not part["config"].get("BUSCARRON_LIST"):
                raise ValueError("buscarron.config.BUSCARRON_LIST: configure at least one form")
        if name in ("postmoogle", "buscarron"):
            prefix = name.upper() + "_"
            for key, val in part["config"].items():
                if not re.fullmatch(prefix + r"[A-Z0-9_]+", key) or not isinstance(val, (str, int, bool)) or any(c in str(val) for c in "\r\n\x00"):
                    raise ValueError(name + ".config: invalid environment key or multiline value")
    hosts = [config[k] for k in ("synapse_domain_name", "element_domain_name") if config[k]]
    hosts += [p["host"] for k, p in config["extensions"].items() if k in HOST_EXTENSIONS and p["enabled"]]
    if config["rtc"]["enabled"]:
        hosts.append(config["rtc"]["domain_name"])
    if len({h.lower() for h in hosts}) != len(hosts):
        raise ValueError("host: each web application requires a different DNS name")
    return config


def ports(environ):
    def get(name, count):
        try:
            # NS8 only provides the comma-separated form for up to eight
            # ports. Larger allocations are exposed as inclusive ranges.
            if environ.get(name + "_RANGE"):
                first, last = (int(v) for v in environ[name + "_RANGE"].split("-"))
                if last - first + 1 != count or first < 1024 or last > 65535:
                    raise ValueError("Invalid allocated range")
                result = list(range(first, last + 1))
            else:
                result = [int(v) for v in environ.get(name, "").split(",")]
        except ValueError:
            raise ValueError(name + ": NS8 did not allocate the required ports") from None
        if len(result) != count or len(set(result)) != count or any(v < 1024 or v > 65535 for v in result):
            raise ValueError(name + ": NS8 did not allocate the required ports")
        return result
    tcp = get("TCP_PORTS", len(TCP_NAMES))
    udp = get("UDP_PORTS", 66)
    if udp != list(range(udp[0], udp[0] + len(udp))):
        raise ValueError("UDP_PORTS: TURN relay ports must be contiguous")
    return dict(zip(TCP_NAMES, tcp), turn_udp=udp[0], relay_start=udp[1], relay_end=udp[64], livekit_udp=udp[65])


def write(path, data, mode=0o600):
    """Atomic private files; caller controls the enclosing module state directory."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        data = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text() == data:
        path.chmod(mode)
        return False
    fd, temporary = tempfile.mkstemp(prefix=".matrix-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def secret_store(state):
    path = Path(state) / "secrets.json"
    values = json.loads(path.read_text()) if path.exists() else {}
    for key in ("postgres", "registration", "macaroon", "form", "shared_auth", "double_puppet", "double_puppet_hs", "turn", "livekit_key", "livekit_secret", "recovery_admin", "maubot_admin", "maubot_signing", "postmoogle_data"):
        values.setdefault(key, secrets.token_urlsafe(48))
    for name in DATABASES:
        values.setdefault("db_" + name, secrets.token_urlsafe(48))
    for name in BRIDGES:
        for suffix in ("as", "hs", "pickle", "provisioning"):
            values.setdefault(name + "_" + suffix, secrets.token_urlsafe(48))
    for name in ("postmoogle", "draupnir", "buscarron"):
        values.setdefault(name + "_password", secrets.token_urlsafe(48))
    write(path, values)
    return values


def db_url(name, values, portmap):
    return "postgresql://{}:{}@host.containers.internal:{}/{}?sslmode=disable".format(name, quote(values["db_" + name], safe=""), portmap["postgres"], name)


def stock(name):
    path = ROOT / "defaults" / (name + ".json")
    return json.loads(path.read_text()) if path.exists() else {}


def registration(name, config, values, portmap):
    domain = re.escape(config["server_name"])
    prefix = PREFIXES[name]
    namespaces = {"users": [
        {"regex": "@" + re.escape(prefix) + ".*:" + domain + "$", "exclusive": True},
        {"regex": "@" + BOT_NAMES[name] + ":" + domain + "$", "exclusive": True},
    ], "aliases": [], "rooms": []}
    result = {
        "id": name, "url": "http://host.containers.internal:{}".format(portmap["hookshot_as" if name == "hookshot" else name]),
        "as_token": values[name + "_as"], "hs_token": values[name + "_hs"],
        "sender_localpart": BOT_NAMES[name], "namespaces": namespaces,
        "rate_limited": False, "de.sorunome.msc2409.push_ephemeral": True,
        "push_ephemeral": True,
    }
    if name == "hookshot":
        result["namespaces"]["users"].extend({"regex": "@_" + p + "_.*:" + domain + "$", "exclusive": True} for p in ("github", "gitlab", "jira", "feeds", "webhooks"))
    return result


def extension_config(name, config, values, portmap):
    extra = config["extensions"][name]["config"]
    result = merge(stock(name), extra)
    server = config["server_name"]
    url = "http://host.containers.internal:" + str(portmap["synapse"])
    if name in ("discord", "telegram", "whatsapp", "signal", "steam"):
        result["homeserver"] = merge(result.get("homeserver", {}), {"address": url, "domain": server})
        app = {"address": "http://host.containers.internal:" + str(portmap[name]), "hostname": "0.0.0.0", "port": 8080, "id": name,
               "as_token": values[name + "_as"], "hs_token": values[name + "_hs"], "bot": {"username": BOT_NAMES[name]}}
        if name == "discord":
            app["database"] = {"type": "postgres", "uri": db_url(name, values, portmap), "max_open_conns": 10, "max_idle_conns": 2}
            result["bridge"] = merge(result.get("bridge", {}), {
                "username_template": "discord_{{.}}", "permissions": {"*": "relay", server: "user", config["bridge_admin"]: "admin"},
                "double_puppet_server_map": {}, "login_shared_secret_map": {server: "as_token:" + values["double_puppet"]},
                "encryption": {"allow": True, "default": True, "pickle_key": values[name + "_pickle"]},
            })
        else:
            app["username_template"] = PREFIXES[name] + "{{.}}"
            result["database"] = merge(result.get("database", {}), {"type": "postgres", "uri": db_url(name, values, portmap)})
            result["bridge"] = merge(result.get("bridge", {}), {"permissions": {"*": "relay", server: "user", config["bridge_admin"]: "admin"}})
            result["matrix"] = merge(result.get("matrix", {}), {"federate_rooms": config["federation"]})
            result["double_puppet"] = {"servers": {}, "allow_discovery": False, "secrets": {server: "as_token:" + values["double_puppet"]}}
            result["encryption"] = merge(result.get("encryption", {}), {"allow": True, "default": True, "pickle_key": values[name + "_pickle"]})
        result["appservice"] = merge(result.get("appservice", {}), app)
        result["provisioning"] = merge(result.get("provisioning", {}), {"shared_secret": values[name + "_provisioning"]})
        if name == "steam":
            result["network"]["steam_bridge_path"] = "/app/"
    elif name == "heisenbridge":
        result = registration(name, config, values, portmap)
        result["heisenbridge"] = merge({"displayname": "Heisenbridge", "media_url": "https://" + config["synapse_domain_name"], "media_path": "/heisenbridge/media/{server}/{media_id}/{checksum}{filename}", "media_key": values[name + "_hs"]}, extra.get("heisenbridge", {}))
    elif name == "hookshot":
        result["bridge"] = {"domain": server, "url": url, "mediaUrl": url, "port": 9993, "bindAddress": "0.0.0.0"}
        result["passFile"] = "/data/passkey.pem"
        result["permissions"] = [{"actor": config["bridge_admin"], "services": [{"service": "*", "level": "admin"}]}]
        result["listeners"] = [{"port": 9000, "bindAddress": "0.0.0.0", "resources": ["webhooks"]}]
        result["generic"] = merge(result.get("generic", {}), {"enabled": True, "urlPrefix": "https://" + config["extensions"][name]["host"] + "/webhook/", "userIdPrefix": "_webhooks_", "allowJsTransformationFunctions": False})
    elif name == "maubot":
        result["database"] = "sqlite:////data/maubot.db"
        result["admins"] = {"root": "", "recovery-admin": values["maubot_admin"]}
        result["homeservers"] = {server: {"url": "https://" + config["synapse_domain_name"], "secret": values["registration"]}}
        result["server"] = merge(result.get("server", {}), {"hostname": "0.0.0.0", "port": 29316, "public_url": "https://" + config["extensions"][name]["host"], "ui_base_path": "/_matrix/maubot", "plugin_base_path": "/_matrix/maubot/plugin/", "unshared_secret": values["maubot_signing"]})
    elif name == "draupnir":
        result.update(homeserverUrl=url, rawHomeserverUrl=url, dataPath="/data", accessToken=extra.get("accessToken") or values.get("draupnir_token", ""))
    elif name == "ketesa":
        result.update(restrictBaseUrl="https://" + config["synapse_domain_name"], externalAuthProvider=False, wellKnownDiscovery=True)
    elif name in ("postmoogle", "buscarron"):
        prefix = name.upper() + "_"
        result = dict(extra)
        result.update({prefix + "HOMESERVER": url, prefix + "LOGIN": name, prefix + "PASSWORD": values[name + "_password"], prefix + "DB_DIALECT": "postgres", prefix + "DB_DSN": db_url(name, values, portmap)})
        if name == "postmoogle":
            result.update(POSTMOOGLE_DOMAINS=extra.get("POSTMOOGLE_DOMAINS", server), POSTMOOGLE_PORT="2525", POSTMOOGLE_TLS_PORT="0", POSTMOOGLE_DATA_SECRET=values["postmoogle_data"])
    return result


def envfile(values):
    lines = []
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or any(c in str(value) for c in "\r\n\x00"):
            raise ValueError("environment: invalid key or multiline value")
        lines.append(key + "=" + (str(value).lower() if isinstance(value, bool) else str(value)))
    return "\n".join(lines) + "\n"


def synapse_config(config, values, portmap, ldap=None, smtp=None):
    server = config["server_name"]
    result = {
        "server_name": server, "public_baseurl": "https://" + config["synapse_domain_name"] + "/",
        "pid_file": "/data/homeserver.pid", "report_stats": False,
        "listeners": [{"port": 8008, "type": "http", "tls": False, "bind_addresses": ["0.0.0.0"], "x_forwarded": True,
                       "resources": [{"names": ["client", "federation" if config["federation"] else "openid"], "compress": False}]}],
        "database": {"name": "psycopg2", "args": {"user": "synapse", "password": values["db_synapse"], "database": "synapse", "host": "host.containers.internal", "port": portmap["postgres"], "cp_min": 5, "cp_max": 10}},
        "media_store_path": "/data/media", "signing_key_path": "/data/signing.key", "log_config": "/config/log.config",
        "registration_shared_secret": values["registration"], "macaroon_secret_key": values["macaroon"], "form_secret": values["form"],
        "enable_registration": config["enable_registration"], "registration_requires_token": True,
        "enable_registration_without_verification": False, "enable_metrics": False,
        "password_config": {"enabled": True, "localdb_enabled": True}, "modules": [],
        "app_service_config_files": ["/config/registrations/" + name + ".yaml" for name in BRIDGES if config["extensions"][name]["enabled"]],
    }
    if any(config["extensions"][name]["enabled"] for name in ("discord", "telegram", "whatsapp", "signal", "steam")):
        result["app_service_config_files"].append("/config/registrations/double-puppet.yaml")
    if config["shared_secret_auth"]:
        result["modules"].append({"module": "shared_secret_authenticator.SharedSecretAuthProvider", "config": {"shared_secret": values["shared_auth"], "m_login_password_support_enabled": False}})
    if config["ldap_domain"]:
        if not ldap:
            raise ValueError("ldap_domain: selected NS8 account provider is unavailable")
        schema = ldap.get("schema", "rfc2307")
        ldapconf = {"enabled": True, "uri": "ldap://{}:{}".format("host.containers.internal" if ldap["host"] == "127.0.0.1" else ldap["host"], ldap["port"]), "start_tls": False,
                    "base": ldap["base_dn"], "bind_dn": ldap["bind_dn"], "bind_password": ldap["bind_password"],
                    "attributes": {"uid": "sAMAccountName" if schema == "ad" else "uid", "mail": "mail", "name": "displayName" if schema == "ad" else "cn"}}
        # Local management/bot identities must never authenticate with an AD
        # account of the same name, in particular the local server administrator.
        uid = ldapconf["attributes"]["uid"]
        reserved = ["recovery-admin", "postmoogle", "buscarron", "draupnir", "doublepuppet"] + list(BOT_NAMES.values())
        exclusions = "".join("(!({}={}))".format(uid, name) for name in sorted(set(reserved)))
        ldapconf["filter"] = "(&" + exclusions + config["ldap_filter"] + ")"
        result["modules"].append({"module": "ldap_auth_provider.LdapAuthProviderModule", "config": ldapconf})
    if config["use_smarthost"]:
        if not smtp or not smtp.get("enabled") or not smtp.get("host") or not config["mail_from"]:
            raise ValueError("use_smarthost: an enabled NS8 smarthost and mail_from are required")
        transport = smtp.get("encrypt_smtp", "starttls")
        result["email"] = {"smtp_host": smtp["host"], "smtp_port": int(smtp["port"]), "notif_from": config["mail_from"], "enable_notifs": True,
                           "require_transport_security": transport in ("starttls", "tls"), "enable_tls": transport != "none", "force_tls": transport == "tls"}
        if smtp.get("username"):
            result["email"].update(smtp_user=smtp["username"], smtp_pass=smtp.get("password", ""))
    return merge(result, config["synapse_extra"])


def render(state, config, values, portmap, ldap=None, smtp=None):
    state = Path(state)
    generated = state / "generated"
    synapse = synapse_config(config, values, portmap, ldap, smtp)
    for name in BRIDGES:
        if config["extensions"][name]["enabled"]:
            reg = extension_config(name, config, values, portmap) if name == "heisenbridge" else registration(name, config, values, portmap)
            write(generated / "synapse/registrations" / (name + ".yaml"), reg)
    double_reg = {"id": "double-puppet", "url": None, "as_token": values["double_puppet"], "hs_token": values["double_puppet_hs"], "sender_localpart": "doublepuppet", "rate_limited": False,
                  "namespaces": {"users": [{"regex": "@(?!recovery-admin:).*:" + re.escape(config["server_name"]) + "$", "exclusive": False}], "aliases": [], "rooms": []}}
    double_path = generated / "synapse/registrations/double-puppet.yaml"
    write(double_path, double_reg)
    well_known = {"m.homeserver": {"base_url": "https://" + config["synapse_domain_name"]}}
    if config["turn"]["enabled"]:
        turn = config["turn"]
        synapse.update(turn_uris=["turn:{}:{}?transport=udp".format(turn["domain_name"], portmap["turn_udp"]), "turn:{}:{}?transport=tcp".format(turn["domain_name"], portmap["turn"])], turn_shared_secret=values["turn"], turn_user_lifetime="1h", turn_allow_guests=False)
        write(generated / "turn.conf", "\n".join([
            "listening-port=3478", "listening-ip=0.0.0.0", "external-ip=" + turn["public_ip"],
            "min-port=" + str(portmap["relay_start"]), "max-port=" + str(portmap["relay_end"]),
            "realm=" + config["server_name"], "use-auth-secret", "static-auth-secret=" + values["turn"],
            "fingerprint", "no-cli", "no-tls", "no-dtls", "no-tcp-relay", "no-multicast-peers", "no-loopback-peers",
            "denied-peer-ip=0.0.0.0-0.255.255.255", "denied-peer-ip=127.0.0.0-127.255.255.255", "denied-peer-ip=169.254.0.0-169.254.255.255", "log-file=stdout", "simple-log",
        ]) + "\n")
    if config["rtc"]["enabled"]:
        rtc = config["rtc"]
        rtc_url = "https://" + rtc["domain_name"]
        well_known["org.matrix.msc4143.rtc_foci"] = [{"type": "livekit", "livekit_service_url": rtc_url}]
        synapse.update(matrix_rtc={"transports": [{"type": "livekit", "livekit_service_url": rtc_url}]}, max_event_delay_duration="24h", rc_delayed_event_mgmt={"per_second": 1, "burst_count": 20})
        synapse["experimental_features"] = merge(synapse.get("experimental_features", {}), {"msc3266_enabled": True, "msc4143_enabled": True, "msc4222_enabled": True})
        write(generated / "livekit.yaml", {"port": portmap["livekit"], "bind_addresses": ["0.0.0.0"], "room": {"auto_create": False}, "rtc": {"tcp_port": portmap["livekit_tcp"], "udp_port": portmap["livekit_udp"], "node_ip": rtc["public_ip"], "use_external_ip": False}, "keys": {values["livekit_key"]: values["livekit_secret"]}, "logging": {"level": "info"}})
        write(generated / "jwt.env", envfile({"LIVEKIT_JWT_BIND": ":8080", "LIVEKIT_KEY": values["livekit_key"], "LIVEKIT_SECRET": values["livekit_secret"], "LIVEKIT_URL": "wss://" + rtc["domain_name"] + "/livekit/", "LIVEKIT_FULL_ACCESS_HOMESERVERS": config["server_name"]}))
    synapse["extra_well_known_client_content"] = {k: v for k, v in well_known.items() if k != "m.homeserver"}
    write(generated / "synapse/homeserver.yaml", synapse)
    write(generated / "synapse/log.config", {"version": 1, "formatters": {"normal": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}}, "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "normal", "stream": "ext://sys.stdout"}}, "root": {"level": "INFO", "handlers": ["console"]}, "disable_existing_loggers": False})
    write(generated / "postgres.env", envfile({"POSTGRES_USER": "matrix", "POSTGRES_PASSWORD": values["postgres"], "POSTGRES_DB": "postgres", "POSTGRES_INITDB_ARGS": "--encoding=UTF8 --lc-collate=C --lc-ctype=C", "PGDATA": "/var/lib/postgresql/data"}))
    element = {"default_server_config": well_known, "disable_custom_urls": False, "disable_guests": True, "brand": "Element", "default_country_code": "DE", "show_labs_settings": True}
    if config["jitsi_domain_name"]:
        element["jitsi"] = {"preferredDomain": config["jitsi_domain_name"]}
    write(generated / "element.json", element, 0o644)
    for name in EXTENSIONS:
        if not config["extensions"][name]["enabled"]:
            continue
        part = extension_config(name, config, values, portmap)
        if name in ("postmoogle", "buscarron"):
            write(generated / name / "config.env", envfile(part))
        elif name == "ketesa":
            write(generated / name / "config.json", part, 0o644)
        else:
            write(generated / name / "config.yaml", part)
            if name in BRIDGES:
                write(generated / name / "registration.yaml", part if name == "heisenbridge" else registration(name, config, values, portmap))
    write(generated / "compressor.env", envfile({"POSTGRES_LOCATION": db_url("synapse", values, portmap)}))
    write(generated / "nginx.conf", gateway_config(config, well_known, portmap), 0o644)


def gateway_config(config, well_known, portmap):
    client = json.dumps(well_known).replace("'", "\\u0027")
    server = json.dumps({"m.server": config["synapse_domain_name"] + ":443"})
    extra = ""
    if config["extensions"]["heisenbridge"]["enabled"]:
        extra = "location /heisenbridge/media/ { proxy_pass http://host.containers.internal:%d; }" % portmap["heisenbridge"]
    return """server {
      listen 8080;
      server_name _;
      client_max_body_size 50m;
      location = /.well-known/matrix/client { default_type application/json; add_header Access-Control-Allow-Origin *; return 200 '%s'; }
      location = /.well-known/matrix/server { default_type application/json; return 200 '%s'; }
      %s
      location / {
        proxy_pass http://host.containers.internal:%s;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 600s;
      }
    }
    """ % (client, server, extra, portmap["synapse"])


def enabled_services(config):
    result = ["postgres", "synapse", "gateway"]
    if config["element_domain_name"]:
        result.append("element")
    result += [name for name in EXTENSIONS if config["extensions"][name]["enabled"]]
    if config["turn"]["enabled"]:
        result.append("turn")
    if config["rtc"]["enabled"]:
        result += ["livekit", "jwt"]
    return result


def firewall_ports(config, portmap):
    result = []
    if config["turn"]["enabled"]:
        result += [str(portmap["turn"]) + "/tcp", str(portmap["turn_udp"]) + "/udp", "{}-{}/udp".format(portmap["relay_start"], portmap["relay_end"])]
    if config["rtc"]["enabled"]:
        result += [str(portmap["livekit_tcp"]) + "/tcp", str(portmap["livekit_udp"]) + "/udp"]
    if config["extensions"]["postmoogle"]["enabled"]:
        result.append(str(portmap["postmoogle"]) + "/tcp")
    return result


def routes(config, portmap):
    result = {"synapse": {"host": config["synapse_domain_name"], "port": portmap["gateway"]}}
    if config["server_name"] != config["synapse_domain_name"]:
        result["discovery"] = {"host": config["server_name"], "port": portmap["gateway"], "path": "/.well-known/matrix", "strip_prefix": False}
    if config["element_domain_name"]:
        result["element"] = {"host": config["element_domain_name"], "port": portmap["element"]}
    for name in HOST_EXTENSIONS:
        if config["extensions"][name]["enabled"]:
            result[name] = {"host": config["extensions"][name]["host"], "port": portmap[name]}
    if config["rtc"]["enabled"]:
        result["jwt"] = {"host": config["rtc"]["domain_name"], "port": portmap["jwt"]}
        result["livekit"] = {"host": config["rtc"]["domain_name"], "port": portmap["livekit"], "path": "/livekit", "strip_prefix": True}
    return result


def public_config(config):
    result = copy.deepcopy(config)
    for part in result["extensions"].values():
        part["has_config"] = bool(part.pop("config"))
    result.pop("synapse_extra", None)
    return result
