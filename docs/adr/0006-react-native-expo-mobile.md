# 0006 — React Native (Expo) for the mobile client

**Status**: Accepted
**Date**: 2026-06-02

## Context

[0004](0004-multi-user-production-pivot.md) adds a mobile app for login, document upload, and chat. The two realistic choices are **React Native** and **Flutter**. The app's surface is forms, lists, text, citation cards, a file picker, and Google sign-in — nothing graphics- or animation-heavy. There is already a web client in **React + TypeScript + Next.js**.

## Decision

Build the mobile app with **React Native using Expo** (managed workflow + dev client + EAS Build).

Why RN over Flutter, *for this project specifically*:

- It shares language and model with the existing Next.js web app — one TS/React skill set, and reuse of API-client code, request/response **types**, and validation schemas across web and mobile. Flutter (Dart) shares none of this.
- Flutter's real strengths — custom rendering, high-fps animation, pixel-identical UI — buy nothing for a text-chat + upload app, while its costs (new language, separate ecosystem) are paid in full.
- Abundant TS/React talent; the team already writes it.

Why Expo over bare RN: Google Sign-In, file picker, and secure storage are all first-class Expo modules, and EAS gives cloud builds plus over-the-air updates. No exotic native module justifies ejecting.

## Consequences

- Session/refresh tokens live in **`expo-secure-store`** (Keychain/Keystore), never `AsyncStorage` — they are credentials to a multi-user system.
- If a future feature needs a native capability Expo can't reach, we adopt an Expo dev client / config plugin before considering bare RN.
- Shared TS types across the backend contract, web, and mobile become worth formalizing (a shared types package or a generated client).
