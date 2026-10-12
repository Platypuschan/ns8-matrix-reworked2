# SPDX-License-Identifier: AGPL-3.0-or-later
import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "imageroot/pypkg"))
import matrix_config as m
from matrix_runtime import Runtime

ENV = {"TCP_PORTS_RANGE": "20000-20019", "UDP_PORTS_RANGE": "21000-21065", "MODULE_ID": "matrix-reworked21"}


def configured():
    return m.validate({"server_name": "example.com", "synapse_domain_name": "matrix.example.com", "element_domain_name": "chat.example.com", "bridge_admin": "@alice:example.com"})


def everything():
    cfg = configured()
    for name, part in cfg["extensions"].items():
        part.update(enabled=True, host=name + ".example.com")
    cfg["extensions"]["telegram"]["config"] = {"network": {"api_id": 12345, "api_hash": "a" * 32}}
    cfg["extensions"]["draupnir"]["config"] = {"managementRoom": "!moderation:example.com"}
    cfg["extensions"]["buscarron"]["config"] = {"BUSCARRON_LIST": "contact", "BUSCARRON_CONTACT_ROOM": "!forms:example.com"}
    for name in ("turn", "rtc"):
        cfg[name].update(enabled=True, domain_name=name + ".example.com", public_ip="203.0.113.10")
    return m.validate(cfg)


class Configuration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.values = m.secret_store(self.state)
        self.portmap = m.ports(ENV)

    def test_matrix_identity_is_immutable_but_web_hostname_can_change(self):
        cfg = configured()
        with self.assertRaisesRegex(ValueError, "server_name"):
            m.validate({"server_name": "other.example.com"}, cfg)
        changed = m.validate({"synapse_domain_name": "new.example.com"}, cfg)
        self.assertEqual(changed["server_name"], cfg["server_name"])
        self.assertEqual(changed["synapse_domain_name"], "new.example.com")

    def test_partial_save_preserves_extension_credentials(self):
        cfg = everything()
        cfg["extensions"]["postmoogle"]["config"]["POSTMOOGLE_RELAY_PASSWORD"] = "unchanged"
        saved = m.validate({"extensions": {"postmoogle": {"host": ""}}}, cfg)
        self.assertEqual(saved["extensions"]["postmoogle"]["config"]["POSTMOOGLE_RELAY_PASSWORD"], "unchanged")

    def test_unsafe_environment_lines_and_unknown_names_are_rejected(self):
        cfg = configured()
        for key, value in (("POSTMOOGLE_RELAY_PASSWORD", "secret\nOTHER=bad"), ("POSTMOOGLE_X\nOTHER", "bad"), ("UNRELATED", "bad")):
            cfg["extensions"]["postmoogle"]["config"] = {key: value}
            with self.assertRaises(ValueError):
                m.validate(cfg)
        with self.assertRaises(ValueError):
            m.validate({"extensions": {"untrusted": {"enabled": True}}}, configured())

    def test_required_credentials_are_checked_before_enabling(self):
        for name in ("telegram", "draupnir", "buscarron"):
            cfg = configured()
            cfg["extensions"][name].update(enabled=True, host=name + ".example.com")
            with self.assertRaisesRegex(ValueError, name):
                m.validate(cfg)

    def test_media_ip_and_allocated_port_ranges_are_validated(self):
        cfg = configured()
        cfg["turn"].update(enabled=True, domain_name="turn.example.com")
        with self.assertRaisesRegex(ValueError, "public_ip"):
            m.validate(cfg)
        with self.assertRaises(ValueError):
            m.ports(dict(ENV, TCP_PORTS_RANGE="20000-20000"))
        with self.assertRaises(ValueError):
            m.ports(dict(ENV, UDP_PORTS_RANGE="21000-22000"))

    def test_ns8_range_environment_matches_explicit_port_lists(self):
        lists = {"TCP_PORTS": ",".join(str(x) for x in range(20000, 20020)),
                 "UDP_PORTS": ",".join(str(x) for x in range(21000, 21066))}
        self.assertEqual(m.ports(lists), self.portmap)
        with self.assertRaises(ValueError):
            m.ports(dict(lists, UDP_PORTS=lists["UDP_PORTS"].replace("21003", "22000")))

    def test_web_hosts_do_not_silently_override_each_other(self):
        cfg = configured()
        cfg["element_domain_name"] = cfg["synapse_domain_name"]
        with self.assertRaisesRegex(ValueError, "different DNS"):
            m.validate(cfg)

    def test_infrastructure_cannot_be_overridden_in_synapse_extra(self):
        overrides = {"database": {}, "server_name": "other.example.com", "modules": [],
                     "registration_shared_secret": "other-secret", "password_config": {"localdb_enabled": False},
                     "enable_registration": True, "registration_requires_token": False,
                     "enable_registration_without_verification": True}
        for key, value in overrides.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate({"synapse_extra": {key: value}}, configured())

    def test_full_stack_render_is_idempotent_and_all_json_is_readable(self):
        cfg = everything()
        m.render(self.state, cfg, self.values, self.portmap)
        first = {str(p.relative_to(self.state)): p.read_bytes() for p in self.state.rglob("*") if p.is_file()}
        m.render(self.state, cfg, m.secret_store(self.state), self.portmap)
        second = {str(p.relative_to(self.state)): p.read_bytes() for p in self.state.rglob("*") if p.is_file()}
        self.assertEqual(first, second)
        for p in (self.state / "generated").rglob("*"):
            if p.suffix in (".yaml", ".json", ".config"):
                json.loads(p.read_text())

    def test_maubot_defaults_match_the_sqlite_backend_and_pinned_image(self):
        cfg = everything()
        result = m.extension_config("maubot", cfg, self.values, self.portmap)
        self.assertEqual(result["crypto_database"], "default")
        self.assertIsNone(result["plugin_databases"]["postgres"])
        self.assertEqual(result["plugin_databases"]["sqlite"], "/data/dbs")
        self.assertEqual(result["plugin_directories"]["load"], ["/data/plugins"])
        self.assertNotEqual(result["crypto_db_pickle_key"], "mau.crypto")
        self.assertEqual(result["crypto_db_pickle_key"], m.secret_store(self.state)["maubot_crypto"])
        cfg["extensions"]["maubot"]["config"] = {"plugin_databases": {"postgres": "default"}}
        self.assertIsNone(m.extension_config("maubot", cfg, self.values, self.portmap)["plugin_databases"]["postgres"])

    def test_tokens_are_distinct_private_and_survive_reconfiguration(self):
        self.assertEqual(self.values, m.secret_store(self.state))
        tokens = [self.values[k + "_as"] for k in m.BRIDGES] + [self.values[k + "_hs"] for k in m.BRIDGES]
        self.assertEqual(len(tokens), len(set(tokens)))
        self.assertEqual((self.state / "secrets.json").stat().st_mode & 0o777, 0o600)
        m.render(self.state, everything(), self.values, self.portmap)
        for p in (self.state / "generated/synapse").rglob("*"):
            if p.is_file():
                self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_appservices_claim_only_their_own_ghosts(self):
        cfg = everything()
        for name in m.BRIDGES:
            reg = m.registration(name, cfg, self.values, self.portmap)
            patterns = [p["regex"] for p in reg["namespaces"]["users"]]
            self.assertTrue(any(re.fullmatch(p, "@" + m.BOT_NAMES[name] + ":example.com") for p in patterns))
            self.assertFalse(any(re.fullmatch(p, "@ordinary:example.com") for p in patterns))
            self.assertFalse(any(re.fullmatch(p, "@" + m.PREFIXES[name] + "123:exampleXcom") for p in patterns))

    def test_new_bridges_use_appservice_double_puppeting(self):
        cfg = everything()
        for name in ("telegram", "whatsapp", "signal", "steam"):
            rendered = m.extension_config(name, cfg, self.values, self.portmap)
            self.assertEqual(rendered["double_puppet"]["secrets"]["example.com"], "as_token:" + self.values["double_puppet"])
        cfg["shared_secret_auth"] = False
        rendered = m.synapse_config(cfg, self.values, self.portmap)
        self.assertEqual(rendered["modules"], [])
        self.assertIn("/config/registrations/double-puppet.yaml", rendered["app_service_config_files"])

    def test_ns8_ldap_uses_local_proxy_and_ad_samaccountname(self):
        cfg = configured()
        cfg["ldap_domain"] = "ad.example.com"
        cfg["ldap_filter"] = "(memberOf=CN=matrix-user,DC=example,DC=com)"
        provider = {"host": "127.0.0.1", "port": 20099, "schema": "ad", "base_dn": "DC=example,DC=com", "bind_dn": "CN=ldapservice,DC=example,DC=com", "bind_password": "escaped\npassword"}
        rendered = m.synapse_config(cfg, self.values, self.portmap, provider)
        ldap = next(p["config"] for p in rendered["modules"] if p["module"].startswith("ldap_"))
        self.assertEqual(ldap["uri"], "ldap://host.containers.internal:20099")
        self.assertFalse(ldap["start_tls"])
        self.assertEqual(ldap["attributes"]["uid"], "sAMAccountName")
        self.assertEqual(ldap["bind_password"], provider["bind_password"])
        self.assertIn("memberOf", ldap["filter"])
        self.assertIn("(!(sAMAccountName=recovery-admin))", ldap["filter"])
        with self.assertRaisesRegex(ValueError, "unavailable"):
            m.synapse_config(cfg, self.values, self.portmap)

    def test_smarthost_transport_is_respected_and_disabled_settings_fail(self):
        cfg = configured()
        cfg.update(use_smarthost=True, mail_from="matrix@example.com")
        smtp = {"enabled": True, "host": "smtp.example.com", "port": 465, "encrypt_smtp": "tls", "username": "sender", "password": "value"}
        rendered = m.synapse_config(cfg, self.values, self.portmap, smtp=smtp)
        self.assertTrue(rendered["email"]["force_tls"])
        self.assertTrue(rendered["email"]["require_transport_security"])
        smtp.update(port=25, encrypt_smtp="none")
        self.assertFalse(m.synapse_config(cfg, self.values, self.portmap, smtp=smtp)["email"]["enable_tls"])
        smtp["enabled"] = False
        with self.assertRaisesRegex(ValueError, "smarthost"):
            m.synapse_config(cfg, self.values, self.portmap, smtp=smtp)

    def test_no_passwords_or_raw_user_secrets_in_general_configuration(self):
        cfg = everything()
        cfg["extensions"]["draupnir"]["config"]["accessToken"] = "PRIVATE_VALUE"
        cfg["synapse_extra"] = {"some_setting": "PRIVATE_VALUE"}
        self.assertNotIn("PRIVATE_VALUE", json.dumps(m.public_config(cfg)))

    def test_double_puppet_cannot_impersonate_recovery_administrator(self):
        m.render(self.state, everything(), self.values, self.portmap)
        reg = json.loads((self.state / "generated/synapse/registrations/double-puppet.yaml").read_text())
        pattern = reg["namespaces"]["users"][0]["regex"]
        self.assertIsNotNone(re.fullmatch(pattern, "@alice:example.com"))
        self.assertIsNone(re.fullmatch(pattern, "@recovery-admin:example.com"))

    def test_restore_to_new_node_rebinds_database_and_appservice_ports(self):
        cfg = everything()
        first = m.extension_config("whatsapp", cfg, self.values, self.portmap)
        new_ports = {k: v + 1000 for k, v in self.portmap.items()}
        second = m.extension_config("whatsapp", cfg, self.values, new_ports)
        self.assertNotEqual(first["database"]["uri"], second["database"]["uri"])
        self.assertNotEqual(first["appservice"]["address"], second["appservice"]["address"])
        self.assertEqual(first["appservice"]["as_token"], second["appservice"]["as_token"])
        self.assertEqual(first["homeserver"]["domain"], second["homeserver"]["domain"])

    def test_container_plans_publish_only_media_and_smtp_publicly(self):
        cfg = everything()
        m.write(self.state / "config.json", cfg)
        runtime = Runtime(self.state, ENV)
        for name in m.enabled_services(cfg):
            plan = runtime.container_plan(name)
            self.assertNotIn(self.values["postgres"], " ".join(plan))
            if name == "synapse":
                self.assertIn("UID=0", plan)
                self.assertIn("GID=0", plan)
            if name in ("discord", "telegram", "whatsapp", "signal", "steam"):
                self.assertIn("--entrypoint", plan)
                self.assertEqual(plan[plan.index("--entrypoint") + 1], "/app/steam" if name == "steam" else "/usr/bin/mautrix-" + name)
            if name not in ("turn", "postmoogle", "livekit"):
                for i, arg in enumerate(plan):
                    if arg == "--publish":
                        self.assertTrue(plan[i + 1].startswith("127.0.0.1:"), name)
        self.assertNotIn(str(self.portmap["postgres"]) + "/tcp", m.firewall_ports(cfg, self.portmap))


if __name__ == "__main__":
    unittest.main()
