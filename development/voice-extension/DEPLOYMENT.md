# Portable helper deployment (candidate; no deployment performed)

## Boundaries and state ownership

The canonical `sidecar_base.py` is unchanged. Its token-v1 dispatch guard,
loopback-only bind, token rotation, health exception and buffered HTTP envelope
remain authoritative. No shutdown HTTP route is added. WebUI authentication and
explicit Settings → Extensions proxy consent are still required. This helper
never creates consent or a proxy token and never executes agent tasks.

Choose **different absolute private directories** for test and production state.
Keep both outside the source/served extension directory. Set
`HERMES_VOICE_STATE_DIR` for the legacy foreground `helper.py` launcher or pass
`--state-dir` explicitly. There is no source-relative persistence fallback.
Library `make_app()` without configured state is non-persistent. If a launcher
already has a private test-state location, explicitly pass that same location;
never reuse it as the production default.

The state directory owns:

- `diagnostic-trace.jsonl` (bounded metadata view) and its metadata history;
- `voice-audit/` (text audit remains off unless the operator independently creates
  `voice-audit/enabled`; deployment never creates/copies that marker);
- supervisor status/readiness/stop files and a persistent kernel-lock inode.

Metadata history and consented text audit rotate but are not a retention service;
operators must choose retention and securely remove old history when appropriate.
Do not package logs, state, enabled markers, caches, tokens or credentials.
POSIX new directories use mode 0700. On Windows, provision an operator-only ACL;
Python's mode argument does not establish a Windows security boundary. Treat the
state directory and all parent directories as private, trusted, non-symlinked
operator storage. Same-UID hostile code is outside the token-v1 trust boundary.

## Preflight and launch

Use an existing supported Python environment; there are no new dependencies.
These examples use POSIX paths; on Windows use absolute `C:/...` paths. Replace
the paths with operator-chosen locations, not state copied from a test install.

```bash
python /opt/voice-extension/helper_lifecycle.py preflight \
  --manifest /opt/voice-extension/manifest.json \
  --state-dir /private/voice-production \
  --port 8767 \
  --token-file /private/webui-production/sidecar-auth/subscription-voice.token

python /opt/voice-extension/helper_lifecycle.py start \
  --manifest /opt/voice-extension/manifest.json \
  --state-dir /private/voice-production \
  --port 8767 \
  --token-file /private/webui-production/sidecar-auth/subscription-voice.token
```

`preflight` checks static manifest origin/port, token-v1 and health path agreement,
absolute file references and state containment. It may create the private state
directory but does not read credentials/tokens, bind a port, create consent,
change WebUI configuration or prove runtime/provider readiness. A missing token
is permitted: canonical non-health requests fail closed until WebUI provisions
it. Manifest origin **must** match the explicit helper port. To use another port,
prepare an operator-reviewed deployment manifest and configure WebUI to use that
same manifest; the CLI does not rewrite assets or WebUI settings.

`start` runs **in the foreground** for a platform service manager or terminal.
No auto-install, detaching, restart policy or process-table scan is implemented.
The supervisor holds the only child process handle; a kernel lock prevents two
supervisors owning the same state. Readiness is published by the worker only
after the canonical server binds successfully. Running status additionally
requires a bounded loopback HTTP health response; health alone never substitutes
for the owned instance's bind marker. Child exit/startup timeout fails startup. stdout/stderr of
the helper are discarded to avoid raw tracebacks/secret output; failure is
reported with a fixed credential-safe JSON failure category and nonzero exit status (not raw exception text). Configure supervision around this
foreground process, not around a stored PID.

No credential option means **DisabledAuth**, suitable for offline checks.
The optional existing `--lb-key-file /private/credentials/voice-key` selects the
existing LocalLBAuth route; it references rather than copies the file. No implicit
Codex/home credential discovery is enabled by this supervisor. The existing
`helper.py --readonly-codex-login` remains available separately, not selected by
production defaults. The LB endpoint remains the existing local transport
contract; this wiring does not introduce provider API flags.

## Status, stop and failure recovery

```bash
python /opt/voice-extension/helper_lifecycle.py status --state-dir /private/voice-production
python /opt/voice-extension/helper_lifecycle.py stop --state-dir /private/voice-production
```

Status reports only state/port. Fresh supervisor heartbeat means locally owned
running/starting, not provider readiness. Missing status is stopped; stale status
is unknown and stop refuses. Stop requests are private, instance-scoped local
files. The supervisor observes the request and terminates/reaps **its own child
handle**; it never signals a stored PID or kills a port occupant. SIGINT/SIGTERM
on the supervisor follows the same cleanup path when Python receives the signal.
On Windows, process-manager TerminateProcess is a hard kill, not SIGTERM; use the
local `stop` command before stopping the supervisor. Graceful application draining
is not provided by the canonical server; pending voice work can be lost on stop.

An OS hard kill/power loss cannot execute Python cleanup. A child may remain if
the supervisor alone is hard-killed. Recovery does not guess ownership or kill
that listener: a fresh start fails its bind. The operator/service manager must
resolve that process using its independently verified ownership. Do not delete
the lock file during a live run (the lock inode is deliberately retained).

## Verification and release gates

The dedicated `test_portable_helper.py` uses disposable directories, random
loopback ports, synthetic tokens, DisabledAuth and real supervisor/worker
subprocesses. It covers token rejection, health, disabled negotiation, diagnostics
outside assets, unchanged audit consent, duplicate owner, unrelated port occupant,
static manifest mismatch, stale status, stop/reaping and port reuse. Run with the
repository `scripts/test.sh` runner alongside existing helper/audit tests.

These checks do not prove provider negotiation, microphone/browser behavior,
mobile/remote operation, production ACLs or platform service-manager behavior.
Keep production configuration, credentials, consent and restart approval as
separate human release gates. Back up exact original bytes and launcher settings;
rollback restores them and uses the same owned stop path. Do not deploy or push
this development candidate without explicit approval.
