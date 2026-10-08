# Subscription voice — isolated release candidate

## Current scope
This development package has been exercised in an authenticated **isolated** WebUI on customization baseline `ee3f4840e26488f091268ec2741c4f576457e0ee`, based on upstream `exp-v0.52.401`. It has not been deployed into the actual WebUI. The backend also requires `api/voice_correction.py`; see `docs/architecture/voice-correction-admission.md` for supported transports and explicit limitations. See `DEPLOYMENT.md` for portable helper lifecycle and explicit private state configuration.

The package now includes task integration through `bridge.js`. **Two core API patches are required**: structured task-outcome projection in `api/routes.py`, and error classification/active-turn redirect support in `api/streaming.py`. Without those patches, the bridge deliberately treats completion as unconfirmed.

## Architecture
- `manifest.json`: scripts `panel.js`, `bridge.js`, `app.js`; stylesheet `voice.css`; loopback token-v1 helper on port 8767.
- `panel.js`: Start, Mute and End call; diagnostic views remain development aids.
- `app.js`: WebRTC, 500-byte UTF-8 context chunks, delivery receipts, local barge-in suppression, bounded cleanup and sanitized evidence.
- `bridge.js`: selected-session/profile targeting; native action validation and FIFO execution; exact clarification response with readback; approval UI stays chat-only; positive correction-consumption evidence; structured failure notices and no automatic retries.
- `helper.py`/`transport.py`: bounded negotiation jobs; provider transport and session instructions. Default auth is disabled. Optional auth adapters are explicitly selected by launcher; this directory contains no credential files.
- `sidecar_base.py`: canonical scaffold version 2, pinned extensions source `9e08e3bd5e13ca3ff5479d5bf6263f0e6b116be1`. No vendor installer used.
- `voice_audit.py`/`diagnostics.py`: local evidence; runtime diagnostic files are private and excluded from release packaging.

Browser traffic uses the authenticated same-origin extension proxy. No browser credential or sidecar token is included in JavaScript. A shared proxy token is not per-user identity; per-job capabilities protect negotiation polling/release. This is not a certified multi-user deployment.

## Acceptance and limitations
The operator has confirmed successful desktop and phone calls, including correction, interruption, shortened answers and returned forecasts in the isolated instance. Missing exact receipts are delivery uncertainty, not backend task failure; audible user confirmation remains separate evidence. Independent additions have succeeded, but native structured queue/status/rephrase routing is not consistently proven. Offline JSON/action fixtures do not establish live provider compliance.

Local failures, unknown outcomes, quota/rate limits, stale targets, approvals, steering races and cleanup have regression tests. Test counts and current candidate hashes belong in the generated release-readiness report, not a permanently claimed acceptance count here.

Negotiation release discards a local job but cannot guarantee cleanup of a provider operation already in progress. Desktop microphone evidence does not establish phone/mobile/remote acceptance.

## Packaging and deployment
Use `../..` source only through an explicit release allowlist. Do not recursively package this directory: diagnostic logs and caches can exist locally. Exploratory probes and deprecated secondary interpreter code must not be activated by deployment.

The local release-preparation builder under workspace `voice-release-prep` packages source/tests plus a backend patch and per-file SHA-256 manifest. It does **not** install, configure, upload, create tokens, start a provider call or mutate the live WebUI.

Before deployment: review the exact artifact; verify the live baseline and effective non-secret extension settings; choose a versioned asset/state location and helper ownership; preserve launcher customizations; back up exact original bytes; obtain approval for production configuration/security changes and restart. Do not copy test sessions, configs, consent/token files or credentials into production.

Rollback must restore exact pre-deployment files and narrowly reverse extension configuration. Reverse-patching alone can change Windows line endings. Do not reset unrelated local modifications, delete sessions, or replace the agent dependency.
