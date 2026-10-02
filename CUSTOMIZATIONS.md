# Maintained local customizations

This file records the purpose and verification for changes carried on this fork.

## Windows launcher closeout and restart handling

**File:** `start.ps1`

**Upstream base:** `exp-v0.52.401`

**Rationale:** In the local Windows setup, a server closeout warning/error was
reported to interrupt normal restart handling. The two launcher edits are
intended to let the existing PowerShell supervisor continue after the child
server exits, log its exit, and make its configured restart attempt. The
original failure log was not retained, so this records the reported symptom
and intended fix, not a definitive diagnosis of every possible failure cause.

The edits are:

- Set `$ErrorActionPreference` to `Continue` so child-process stderr does not unexpectedly become a terminating PowerShell error and short-circuit closeout handling.
- `return` the server's captured exit code after `finally` instead of terminating the PowerShell host with `exit`. This permits the calling supervisor to continue and inspect the native process's `$LASTEXITCODE`.

**Verification:** `python tests/test_start_ps1_supervisor.py` runs a Windows PowerShell 5.1 harness with isolated temporary directories and a fake `server.py` that writes a synthetic shutdown warning to stderr and exits with code 23. The check asserts the caller resumes and still observes exit code 23. It does not start the real WebUI, invoke the real Scheduled Task, or verify a live restart cycle.

When updating this branch from upstream, retain or deliberately revise these edits and rerun the focused launcher test before relying on the customization.
