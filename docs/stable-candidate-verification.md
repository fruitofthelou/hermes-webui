# Stable customization candidate

## Source and scope

Stable base: v0.52.458, commit fd0141fa196fe832171c9c0551bbb8205b6412d4.
Preserves voice integration b42f9043440fb06070d8a23400f85bcaa8a3bd41 and existing supervisor restart behavior. Upstream server import-path restoration and managed bootstrap replace the bespoke launcher wrapper. After successful activation, managed_agent_startup exports the actual interpreter for children. See windows-managed-startup.md.

## Verification

- 24 extension JavaScript suites passed.
- 174 targeted Python voice/control/helper checks passed; one POSIX signal test skipped on Windows.
- Six dedicated stdlib startup tests passed, including native PowerShell retry and location restoration.
- Python checks used managed Python 3.14.7 against adapted core commit 5e5ce8220d4b3c3ff097cd02716ccd8e413e010f, with existing pytest loaded from a separate test environment. No dependency installations.
- Bootstrap/recovery deliberately stubbed for offline checks. Actual core methods exercised via control fixtures, not a complete AIAgent constructor/provider invocation. Repository conftest bypassed because it rejects 3.14 and enables broader fixtures.

These are bounded offline verification results, not full repository CI or live acceptance. Production activation, provider calls, remote browser/WebRTC, scheduled logon and reboot remain rollout checks.

## Rollout boundary

Do not deploy from an active WebUI conversation without independent remote access. Before deployment preserve exact live working files (including uncommitted launcher/server fixes), startup scripts, task definition and state backups. Keep the scheduled task in the logged-in user's Interactive desktop with existing privileges; never switch to SYSTEM/session 0. Preserve console-free supervision and network binding. Do not restore old core customization stashes or downgrade the core as WebUI rollback.

Deploy only an exact reviewed commit during an idle window. If verification fails restore the pre-update working source and startup chain, not merely the old upstream HEAD. State migration rollback requires an appropriate state backup. Source snapshots alone are not encrypted/full-state backups.

Future updates target published stable tags, integrated and tested on the customization branch before publication/deployment. This document does not change update-channel settings.
