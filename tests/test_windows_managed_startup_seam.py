"""Offline startup seam checks; stdlib-only, no real Agent or application imports.

Run directly with Python (not pytest); no dependency/bootstrap installation needed.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")


class ManagedStartupSeamTests(unittest.TestCase):
    def setUp(self):
        # Honor Hermes scratch routing, including when the caller overrides TMPDIR.
        self.temp = tempfile.TemporaryDirectory(prefix="managed-startup-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "webui with spaces"
        self.agent = self.root / "agent with spaces"
        self.repo.mkdir()
        self.agent.mkdir()
        (self.agent / "hermes_cli").mkdir()
        (self.agent / "run_agent.py").write_text("raise AssertionError('premature Agent application import')\n", encoding="utf-8")
        for name in ("server.py", "managed_agent_startup.py", "start.ps1"):
            shutil.copy2(ROOT / name, self.repo / name)
        api = self.repo / "api"
        api.mkdir()
        (api / "__init__.py").write_text("", encoding="utf-8")
        # Execute the real server startup through its first application import,
        # then stop before config, credentials, providers, binding or threads.
        (api / "request_logging.py").write_text(
            "import json, os, sys\n"
            "assert 'run_agent' not in sys.modules\n"
            "print('SEAM=' + json.dumps({'python': sys.executable, "
            "'export': os.environ.get('HERMES_WEBUI_PYTHON'), "
            "'agent': os.environ['HERMES_WEBUI_AGENT_DIR'], "
            "'bootstrap': 'hermes_bootstrap' in sys.modules, "
            "'relaunch': os.environ.get('SEAM_RELAUNCHED'), "
            "'path': sys.path, 'argv': sys.argv}))\n"
            "raise SystemExit(int(os.environ.get('SEAM_EXIT', '0')))\n",
            encoding="utf-8",
        )
        # Allow-list rather than inherit live HERMES_* / Python overrides.
        keys = ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "TMPDIR", "TEMP", "TMP")
        self.env = {key: os.environ[key] for key in keys if key in os.environ}
        self.env.update({
            "HOME": str(self.root / "user"), "USERPROFILE": str(self.root / "user"),
            "LOCALAPPDATA": str(self.root / "local"),
            "HERMES_HOME": str(self.root / "home"),
            "HERMES_WEBUI_STATE_DIR": str(self.root / "state"),
            "HERMES_WEBUI_AGENT_DIR": str(self.agent),
            "HERMES_WEBUI_PYTHON": "stale-launcher-python",
            "HERMES_WEBUI_TEST_MODE": "1", "PYTHONDONTWRITEBYTECODE": "1",
        })

    def bootstrap(self, text):
        (self.agent / "hermes_bootstrap.py").write_text(text, encoding="utf-8")

    def run_server(self):
        return subprocess.run([sys.executable, "-I", str(self.repo / "server.py")],
                              cwd=self.agent, env=self.env, capture_output=True, text=True, timeout=30)

    def seam(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        records = [json.loads(line[5:]) for line in result.stdout.splitlines() if line.startswith("SEAM=")]
        self.assertEqual(len(records), 1, result.stdout + result.stderr)
        return records[0]

    def test_success_exports_actual_runtime_before_application_imports(self):
        self.bootstrap("import sys\nassert not any(n.startswith('api.') for n in sys.modules)\n")
        data = self.seam(self.run_server())
        self.assertTrue(data["bootstrap"])
        self.assertEqual(data["export"], data["python"])
        self.assertIn(str(self.repo), data["path"])

    def test_relaunch_run_path_restores_webui_path_and_runtime_export(self):
        # Agent-style isolated relaunch has no WebUI path: real server.py owns
        # restoring that path, and activation owns publishing the final runtime.
        code = (
            "import runpy, sys; "
            f"sys.path.insert(0, {str(self.agent)!r}); "
            f"sys.argv = [{str(self.repo / 'server.py')!r}]; "
            f"runpy.run_path({str(self.repo / 'server.py')!r}, run_name='__main__')"
        )
        self.bootstrap(
            "import os, subprocess, sys\n"
            "assert not any(n.startswith('api.') for n in sys.modules)\n"
            "if not os.environ.get('SEAM_RELAUNCHED'):\n"
            "    os.environ['SEAM_RELAUNCHED'] = '1'\n"
            f"    raise SystemExit(subprocess.call([sys.executable, '-I', '-c', {code!r}]))\n"
        )
        data = self.seam(self.run_server())
        self.assertEqual(data["relaunch"], "1")
        self.assertEqual(data["export"], data["python"])
        self.assertIn(str(self.repo), data["path"])
        self.assertEqual(data["argv"], [str(self.repo / "server.py")])

    def test_bootstrap_failure_warns_without_publishing_success(self):
        self.bootstrap("raise ImportError('offline bootstrap failure')\n")
        result = self.run_server()
        data = self.seam(result)
        self.assertIn("Hermes Agent dependency activation failed", result.stderr)
        self.assertEqual(data["export"], "stale-launcher-python")

    def test_bootstrap_system_exit_propagates(self):
        self.bootstrap("raise SystemExit(7)\n")
        result = self.run_server()
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertNotIn("SEAM=", result.stdout)

    def test_legacy_agent_keeps_runtime_override_and_path_placement(self):
        data = self.seam(self.run_server())
        self.assertFalse(data["bootstrap"])
        self.assertEqual(data["export"], "stale-launcher-python")
        self.assertNotIn(str(self.agent), data["path"])

    @unittest.skipUnless(POWERSHELL, "PowerShell required for actual launcher execution")
    def test_launcher_returns_to_direct_supervisor_for_retry_and_restores_location(self):
        self.bootstrap("import sys\nassert not any(n.startswith('api.') for n in sys.modules)\n")
        self.env["HERMES_WEBUI_PYTHON"] = sys.executable
        self.env["SEAM_EXIT"] = "7"
        wrapper = self.root / "supervisor.ps1"
        wrapper.write_text(
            "$before = (Get-Location).Path\n"
            f"$first = & '{self.repo / 'start.ps1'}'\n"
            "$firstExit = $LASTEXITCODE\n"
            "$env:SEAM_EXIT = '0'\n"
            f"$second = & '{self.repo / 'start.ps1'}'\n"
            "$secondExit = $LASTEXITCODE\n"
            "$first | ForEach-Object { Write-Output $_ }\n"
            "$second | ForEach-Object { Write-Output $_ }\n"
            "if ($first[-1] -ne 7 -or $firstExit -ne 7) { throw 'first exit lost' }\n"
            "if ($second[-1] -ne 0 -or $secondExit -ne 0) { throw 'retry exit lost' }\n"
            "if ((Get-Location).Path -ne $before) { throw 'caller location changed' }\n"
            "Write-Output 'SUPERVISOR_RETRY_OK'\n",
            encoding="utf-8",
        )
        result = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper)],
                                cwd=self.root, env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SUPERVISOR_RETRY_OK", result.stdout)
        records = [json.loads(line[5:]) for line in result.stdout.splitlines() if line.startswith("SEAM=")]
        self.assertEqual(len(records), 2, result.stdout + result.stderr)
        for data in records:
            self.assertEqual(data["export"], data["python"])
            self.assertEqual(data["agent"], str(self.agent))
            self.assertEqual(data["argv"], [str(self.repo / "server.py")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
