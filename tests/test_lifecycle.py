# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_config import ENV, configured
from matrix_runtime import Runtime
import matrix_config as m


class FakeRuntime(Runtime):
    def __init__(self, state):
        super().__init__(state, ENV)
        self.events = []
        self.running = {"synapse", "gateway", "maubot"}
        self.fail_dump = False
        self.fail_tar = False
        self.fail_start = set()
        self.fail_restore = False

    def command(self, args, **kwargs):
        self.events.append(tuple(args))
        if "pg_dump" in args and self.fail_dump:
            raise RuntimeError("dump failed")
        if "tar" in args and self.fail_tar:
            raise RuntimeError("archive failed")
        if args[:3] == ["podman", "volume", "exists"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["podman", "ps"]:
            return subprocess.CompletedProcess(args, 0, json.dumps([{"Names": ["matrix-maubot"], "State": "exited"}, {"Names": ["unrelated"], "State": "exited"}, {"Names": ["matrix-synapse"], "State": "running"}]), "")
        return subprocess.CompletedProcess(args, 0, "", "")

    def systemd(self, *args, check=True):
        self.events.append(tuple(args))
        if args[0] == "start" and args[1].removeprefix("matrix-").removesuffix(".service") in self.fail_start:
            raise RuntimeError("start failed")
        return subprocess.CompletedProcess(args, 1 if args[0] == "is-active" else 0, "inactive", "")

    def active(self, name):
        return name in self.running

    def sql(self, text, db="postgres"):
        self.events.append(("sql", text))
        return "1" if "datname='synapse'" in text else ""

    def discover(self, cfg):
        return None, None

    def ensure_databases(self):
        self.events.append(("ensure_databases",))

    def setup_routes(self, cfg):
        self.events.append(("routes",))

    def reconcile(self):
        self.events.append(("reconcile",))


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        m.write(self.state / "config.json", configured())
        self.values = m.secret_store(self.state)
        self.runtime = FakeRuntime(self.state)

    def test_dump_failure_resumes_all_previous_writers(self):
        self.runtime.fail_dump = True
        with self.assertRaisesRegex(RuntimeError, "dump failed"):
            self.runtime.snapshot()
        for name in self.runtime.running:
            self.assertIn(("start", "matrix-" + name + ".service"), self.runtime.events)
        self.assertFalse((self.state / "backup/manifest.json").exists())
        self.assertNotIn(("stop", "matrix-postgres.service"), self.runtime.events)

    def test_archive_failure_does_not_publish_partial_backup(self):
        self.runtime.fail_tar = True
        with self.assertRaisesRegex(RuntimeError, "archive failed"):
            self.runtime.snapshot()
        self.assertFalse((self.state / "backup/manifest.json").exists())
        self.assertIn(("start", "matrix-synapse.service"), self.runtime.events)

    def test_one_resume_failure_does_not_skip_other_services(self):
        self.runtime.fail_start = {"synapse"}
        with self.assertRaisesRegex(RuntimeError, "could not resume"):
            self.runtime.snapshot()
        for name in self.runtime.running:
            self.assertIn(("start", "matrix-" + name + ".service"), self.runtime.events)

    def test_copy_and_database_dump_finish_before_services_resume(self):
        self.runtime.snapshot()
        events = self.runtime.events
        first_resume = next(i for i, event in enumerate(events) if event[0] == "start")
        archive_events = [i for i, event in enumerate(events) if "tar" in event]
        dump_events = [i for i, event in enumerate(events) if "pg_dump" in event]
        self.assertTrue(archive_events and dump_events)
        self.assertLess(max(archive_events + dump_events), first_resume)
        self.assertEqual(json.loads((self.state / "backup/secrets.json").read_text()), self.values)
        self.assertEqual(json.loads((self.state / "backup/config.json").read_text()), configured())

    def test_cleanup_leaves_running_containers_and_every_volume_alone(self):
        self.runtime.cleanup()
        self.assertIn(("podman", "rm", "--ignore", "matrix-maubot"), self.runtime.events)
        self.assertFalse(any("unrelated" in event or "matrix-synapse" in event or "prune" in event or "volume" in event for event in self.runtime.events))

    def test_restore_rejects_unknown_volume_without_running_commands(self):
        m.write(self.state / "backup/manifest.json", {"configured": True, "format": 1, "databases": ["synapse"], "volumes": ["unrelated"]})
        with self.assertRaises(ValueError):
            self.runtime.restore()
        self.assertFalse(self.runtime.events)

    def test_invalid_configuration_does_not_replace_working_state(self):
        original = (self.state / "config.json").read_bytes()
        with self.assertRaises(ValueError):
            self.runtime.configure({"server_name": "different.example.com"})
        self.assertEqual((self.state / "config.json").read_bytes(), original)
        self.assertFalse(self.runtime.events)

    def test_repeated_save_does_not_schedule_restarts(self):
        self.runtime.configure(configured())
        (self.state / "restart-required").unlink()
        result = self.runtime.configure(configured())
        self.assertFalse(result["changed"])
        self.assertFalse((self.state / "restart-required").exists())


if __name__ == "__main__":
    unittest.main()
