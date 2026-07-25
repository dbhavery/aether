# Module 10: Android

Native Android client for Aether — full chat on the user's Samsung Galaxy S24.

## Responsibility

This Python package is a placeholder. The Android client is a Kotlin/Jetpack
Compose application and lives in its own repository (`aether-avatar` or a
dedicated Android repo), not in this Python codebase. This `src/android/`
directory exists to reserve the module namespace and to document the interface
contract that the Kotlin app must fulfill.

## Key Files

- `__init__.py` — empty; no Python code exists here yet.

## Interface Contract

The Kotlin app connects to the Aether Core WebSocket on port 8765. Over
Tailscale (IP: 100.105.108.18) when off the home network.

- Sends: `{"type": "message", "text": str, "timestamp": str}`
- Receives: `{"type": "response", "text": str, "emotion": str}`
- FCM: registers its device token with the server on first launch so
  `src/notifications/fcm_notify.py` can deliver push notifications.

The server side has no Python code specific to Android. The Notifications module
(`src/notifications/fcm_notify.py`) handles FCM push delivery. Authentication uses
the same bearer token scheme as the desktop client.

## Dependencies

- No Python dependencies (module is a placeholder).
- Android app stack: Kotlin, Jetpack Compose, Material 3, OkHttp (WebSocket),
  Navigation 2, Firebase Cloud Messaging.

## Status

[NOT IMPLEMENTED] — Python side has no code. Android Kotlin app is the
deliverable for this module. See `.claude/rules/module-10-android.md` for the
full done-when criteria.
