# Windows managed-runtime startup seam

## Contract Routing

Task type: native Windows managed-runtime compatibility.
Touched state: the child server process's `HERMES_WEBUI_PYTHON` environment value.
Relevant guidance: `AGENTS.md`, `CONTRIBUTING.md`, `docs/CONTRACTS.md`,
`docs/GUIDELINES.md`, and `docs/onboarding-agent-checklist.md`.
Scope excludes provider configuration, profile selection, core repair/install,
service configuration and live deployment.

## Ownership

- `start.ps1` retains stable Agent discovery, selected-Agent venv preference,
  environment defaults and direct foreground `server.py` invocation.
- `server.py` already restores the WebUI directory before local imports when
  an isolated managed-runtime relaunch uses `runpy.run_path()`.
- `managed_agent_startup.activate_managed_agent()` imports the selected source
  checkout's `hermes_bootstrap` before application imports. After that import
  returns successfully, it exports `sys.executable` as `HERMES_WEBUI_PYTHON`
  for children. This replaces a stale initial-launcher interpreter value with
  the actual activated runtime, without changing initial interpreter discovery.
- A bootstrap exception still warns and continues without publishing successful
  activation. `SystemExit` still propagates for relaunch/repair outcomes.
  Missing, browser-only and older Agent layouts retain their existing no-op
  behavior and runtime overrides; legacy Agent paths are not promoted.

A separate PowerShell `python -c` bootstrap/runpy wrapper is unnecessary: these
responsibilities belong to the existing server/helper seam. Do not import the
Agent application before profile selection or copy a local launcher over the
stable discovery implementation.

Keep the existing launcher `Continue` error preference, `try/finally` location
restoration, `$LASTEXITCODE` capture and final `return`. In particular, an outer
PowerShell supervisor invoking `& $StartScript` must resume and be able to retry
when the child exits. Returning a value and terminating the supervising shell
are not interchangeable.

## Deterministic offline verification

```bash
python tests/test_windows_managed_startup_seam.py
```

This is a stdlib `unittest` entry point, not a pytest invocation. It needs no
packages and does not run the dependency-installing pytest runner. Native
PowerShell is required for the launcher case; otherwise that case is skipped.
Fixtures use disposable directories under `TMPDIR` when set. The child
environment is allow-listed, with isolated home, state and Agent paths and no
inherited credentials or Hermes configuration overrides.

The checks execute a copied real `server.py` and `managed_agent_startup.py`,
with a fixture `hermes_bootstrap.py`. A fixture first application-import module
records the seam and exits before real application/config/provider imports or
socket binding. Cases cover:

1. Successful activation publishes the actual interpreter before application
   imports, despite a deliberately stale launcher value.
2. A bootstrap stub launches isolated Python with only the Agent path and uses
   `runpy.run_path(server.py)`; the real server restores WebUI importability,
   preserves script argv and publishes the relaunched interpreter.
3. Import failure warns and continues without replacing the runtime override.
4. Bootstrap `SystemExit(7)` propagates before application imports.
5. Legacy source without bootstrap preserves runtime override and path placement.
6. Real PowerShell invokes the actual launcher twice from a supervisor, observes
   child exit 7 followed by retry exit 0, confirms both returned values and
   `$LASTEXITCODE`, restores caller location and reaches both startup seams.

These checks prove WebUI-owned startup wiring with offline bootstrap stubs.
They do not prove a particular installed core's dependency resolution/repair,
selection of a different installed managed environment, full server health,
provider access, or production scheduled-task behavior. Those require separately
authorized environment/integration validation; do not run core bootstrap against
real home just to extend these checks.
