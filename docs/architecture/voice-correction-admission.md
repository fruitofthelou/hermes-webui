# Interactive correction admission

## Contract Routing

Runtime control ownership and terminal settlement: `api/streaming.py`,
`api/voice_correction.py`; related contracts are
`../rfcs/webui-run-state-consistency-contract.md`,
`../rfcs/hermes-run-adapter-contract.md`, and
`../rfcs/webui-pending-intent-controls.md`.

## Contract Change

Previously local Steer only enqueued the Agent's pending-steer slot under the
stream ownership lock. WebUI-created, redirect-capable Agents now use a narrow
subclass admission API. During a supported interactive model request it sets the
native pending-redirect slot and interruption flag under the native redirect
lock. Native request workers observe that flag and cancel their own request;
the native conversation loop rebuilds the same logical turn with the correction.
No provider callback, native `redirect()` call, thread-signal mutation, or native
Codex request is invoked by admission. Preparation and tool execution retain
native Steer at a safe boundary, without killing tools.

The source-of-truth is the Agent's native control slots, not a parallel queue.
The stream registry owns session/backend/phase admission. The stream-bound
Agent remains authoritative across compression identity rotation. Cache-only
compatibility retains positive stream/run/backend ownership checks. Starting
and running admit input; finalizing closes admission before outside-lock final
settlement drains **both** slots and merges returned pending-Steer leftovers.

Stop publishes native redirect cancellation under the same stream ownership
edge before detach, then performs native interrupt, provider abort, tool fanout
and session persistence outside registry locks. Stop-first rejects correction;
correction-first can be accepted and then superseded by explicit Stop. No
outside-lock correction wake can accidentally interrupt a subsequent request:
interactive workers already poll the flag, so the adapter needs no external wake.

## Explicit limitations

Supported model-request modes are `chat_completions`, `codex_responses`, and
`anthropic_messages` on interactive workers. Codex **app-server** mode is distinct:
its blocking native `request_steer()` lacks safe admission/settlement and returns
`accepted=false, fallback=immediate_redirect_unsupported`, including when the
native method is missing. Inline cron/delegation contexts, an active inline abort
callback, unknown modes, and unadapted redirect-capable objects also fail closed.
No silent downgrade to a next-turn queue or claim of applied guidance is made.
A future Agent request-scoped asynchronous native control contract is required
to support those modes. Legacy Agents without redirect retain existing Steer.

## Verification boundaries

`tests/test_voice_correction_adaptation.py` uses the installed actual AIAgent
control methods, native redirect message consumer, and native interruptible
request worker with offline transport dispatch. It covers registered/cache-only
Stop/Steer orderings using barriers, finalizing, rotated identity, blocking and
throwing abort callbacks, native app-server refusal, and safe tool boundaries.
Neighboring ownership, cancellation, worker and settlement tests remain required.
These are offline control-plane proofs, not live provider or browser proofs.
No new dependencies, provider settings, security changes, or service switch are
part of this change.
