# Product

## Register

product

## Users

The primary user is the owner of a personal WeChat account running on a local Mac.
The user needs to inspect and control an AI auto-reply workflow without opening a terminal.

## Product Purpose

TraceMemo AutoReply is a local macOS control app for the existing TraceMemo -> DeepSeek -> WeChat workflow.
It provides a trustworthy way to start, stop, configure, and observe the automation while keeping credentials in macOS Keychain and personal conversation data on the local machine.
Success means the owner can understand the current state, adjust safe settings, and diagnose a failed reply from one window.

## Brand Personality

Calm, precise, trustworthy.
The app should feel like a focused macOS utility used during a real workday, with clear state, restrained motion, and direct language.

## Anti-references

- No marketing landing page or oversized hero treatment.
- No neon cyberpunk dashboard, decorative gradients, or dense visual noise.
- No generic stack of identical cards that hides the most important service state.
- No secret values, raw API tokens, or private message bodies in UI logs or source control.

## Design Principles

1. State before settings: show whether the automation is safe and running before exposing controls.
2. Local by default: keep credentials, logs, and message-derived data on the Mac.
3. Guarded actions: make start, stop, and send-related failures explicit and reversible.
4. Practical density: optimize for scanning a status, a log line, or a whitelist entry quickly.
5. Open-source clarity: separate the reusable app shell from machine-specific configuration and secrets.

## Accessibility & Inclusion

Use native macOS controls and keyboard navigation, support Dynamic Type where practical, preserve readable contrast in both appearance modes, and honor Reduce Motion. Status must not rely on color alone; pair colors with text and symbols.
