"""Behavioral regression coverage for start.ps1 called by a Windows supervisor."""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = pathlib.Path(__file__).resolve().parent.parent
POWERSHELL = shutil.which("powershell.exe") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


@unittest.skipUnless(os.name == "nt" and pathlib.Path(POWERSHELL).is_file(), "requires Windows PowerShell")
class StartPs1SupervisorTests(unittest.TestCase):
    def test_child_warning_and_nonzero_exit_return_control_to_supervisor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="webui-start-ps1-test-") as temp_dir:
            temp = pathlib.Path(temp_dir)
            repo = temp / "webui"
            agent_dir = temp / "agent"
            home_dir = temp / "hermes-home"
            state_dir = temp / "webui-state"
            repo.mkdir()
            (agent_dir / "hermes_cli").mkdir(parents=True)
            shutil.copy2(REPO / "start.ps1", repo / "start.ps1")
            (repo / "server.py").write_text(
                "import sys\n"
                "print('synthetic shutdown warning', file=sys.stderr)\n"
                "raise SystemExit(23)\n",
                encoding="utf-8",
            )

            log_path = temp / "launcher.log"
            harness_path = temp / "supervisor-harness.ps1"
            harness_path.write_text(
                "$ErrorActionPreference = 'Stop'\n"
                "$startScript = $env:TEST_START_SCRIPT\n"
                "$logPath = $env:TEST_LAUNCH_LOG\n"
                "& $startScript -Port 18787 >> $logPath 2>&1\n"
                "$supervisedExitCode = $LASTEXITCODE\n"
                "Write-Output ('SUPERVISOR_RESUMED:{0}' -f $supervisedExitCode)\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "HERMES_HOME": str(home_dir),
                    "HERMES_WEBUI_AGENT_DIR": str(agent_dir),
                    "HERMES_WEBUI_PYTHON": sys.executable,
                    "HERMES_WEBUI_STATE_DIR": str(state_dir),
                    "HERMES_WEBUI_HOST": "127.0.0.1",
                    "TEST_START_SCRIPT": str(repo / "start.ps1"),
                    "TEST_LAUNCH_LOG": str(log_path),
                }
            )
            completed = subprocess.run(
                [
                    POWERSHELL,
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(harness_path),
                ],
                capture_output=True,
                text=True,
                timeout=20,
                env=env,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("SUPERVISOR_RESUMED:23", completed.stdout)
            log_bytes = log_path.read_bytes()
            log_encoding = "utf-16" if log_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8"
            self.assertIn("synthetic shutdown warning", log_bytes.decode(log_encoding))


if __name__ == "__main__":
    unittest.main()
