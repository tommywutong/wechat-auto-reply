# DESIGN.md

## Visual Theme & Atmosphere

TraceMemo AutoReply is a quiet operations console for a personal Mac. The user looks at it under ordinary office or home lighting while checking whether automation is healthy. The interface is native, compact, and confident: a calm neutral canvas with one restrained signal color for active automation and warm amber/red only for attention states.

## Color Palette & Roles

Use semantic SwiftUI colors so the app follows macOS light/dark appearance.

| Token | Light role | Dark role | Usage |
| --- | --- | --- | --- |
| `canvas` | `#F5F6F8` | `#17181B` | Window background |
| `surface` | `#FFFFFF` | `#222428` | Panels and controls |
| `surfaceMuted` | `#ECEEF1` | `#2B2E33` | Secondary rows and selected navigation |
| `ink` | `#17191C` | `#F3F4F6` | Primary text |
| `inkMuted` | `#626973` | `#A9AFB9` | Supporting text |
| `signal` | `#157A5B` | `#51C99B` | Running state and primary action |
| `warning` | `#A86200` | `#F2B65B` | Degraded state |
| `danger` | `#B42318` | `#FF8178` | Stopped/error state |
| `divider` | `#D9DDE3` | `#3A3E45` | Subtle separation |

Avoid gradients, decorative blur, and large saturated regions. Use color with a symbol and a text label.

## Typography Rules

- Use the system `SF Pro` through native SwiftUI fonts.
- Page title: `.title2` or `.title`, semibold.
- Section title: `.headline`.
- Body: `.body` with standard leading.
- Supporting text: `.subheadline` or `.caption`, never below the system caption size for essential information.
- Logs: monospaced `.system(.body, design: .monospaced)`.

## Component Stylings

- Prefer native `Button`, `Toggle`, `Picker`, `Form`, `List`, and `Table` controls.
- Primary actions use a filled signal tint and a verb-first label, such as “启动服务” or “停止服务”.
- Destructive stop actions require a confirmation when the service is actively processing a message.
- Status rows pair an SF Symbol, text, and color. Never use a colored dot alone.
- Use compact bordered panels for repeated operational information, with modest corner radii no larger than 12pt.
- Tooltips name unfamiliar icon-only actions.

## Layout Principles

- Use a `NavigationSplitView`: navigation, current screen, and optional inspector content.
- The overview should put service state and latest activity above configuration.
- Keep controls aligned to a predictable 8pt spacing rhythm.
- Use a minimum window size around 980x650 and allow the log view to expand.
- Do not nest panels inside panels without a clear ownership relationship.

## Depth & Elevation

Use native macOS material and one-pixel dividers sparingly. A selected row can use a tinted surface; avoid broad shadows and ornamental floating cards.

## Do's and Don'ts

- Do show the last update time and the source of each health state.
- Do keep API credentials masked and out of copied logs.
- Do give empty, loading, and permission-error states their own concise explanation.
- Do support Reduce Motion.
- Don't show raw YAML or require terminal commands for normal operation.
- Don't imply a message was sent until the backend confirms the attempt.

## Agent Prompt Guide

Build a native macOS utility for controlling a local WeChat AI auto-reply service. Use a calm neutral canvas, system typography, compact operational density, green running state, amber degraded state, and red stopped/error state. Prioritize status, logs, and guarded controls. Avoid gradients, marketing layout, decorative cards, and secret exposure.
