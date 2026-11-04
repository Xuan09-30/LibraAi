# Project Libra Design System (DESIGN.md)

## 1. Identity & Philosophy
Project Libra pairs a high-performance local AI assistant (CUDA, Kokoro-82M, Faster-Whisper, Qwen/Hermes) with a responsive mobile-first Web/PWA interface and a local PyQt6 desktop GUI.

The design language balances **cybernetic futurism** (tactical neon accents, subtle luminescence, precision typography) with **high-class minimalist ergonomics** (zinc/slate surfaces, hairline borders, ample touch margins, clean contrast).

---

## 2. Shared Design Tokens

### A. Color Palette

#### Surfaces & Backgrounds
| Token | Value | Role |
| :--- | :--- | :--- |
| `bg-app` | `#09090b` | App root background (deepest zinc) |
| `bg-surface` | `#121215` | Secondary surface, sidebars, main panels |
| `bg-card` | `#18181b` | Elevated cards, modal dialogs, chat inputs |
| `bg-card-hover` | `#222226` | Card and list item interactive hover |
| `bg-bubble-user` | `#27272a` | User chat bubble surface |
| `bg-scrim` | `rgba(0, 0, 0, 0.75)` | Backdrop dimming for modals and mobile drawer |

#### Borders & Hairlines
| Token | Value | Role |
| :--- | :--- | :--- |
| `border-subtle` | `rgba(255, 255, 255, 0.08)` | Default hairline dividers and card outlines |
| `border-medium` | `rgba(255, 255, 255, 0.14)` | Interactive element boundaries (buttons, inputs) |
| `border-hover` | `rgba(255, 255, 255, 0.24)` | Hover highlight state |
| `border-focus` | `rgba(56, 189, 248, 0.6)` | Active/focus ring state (cyan accent) |

#### Cybernetic Accents
| Token | Hex | Muted / Glow (`0.15`) | Semantic Purpose |
| :--- | :--- | :--- | :--- |
| `accent-cyan` | `#38bdf8` | `rgba(56, 189, 248, 0.15)` | Primary brand, active selection, links, host tools |
| `accent-emerald`| `#34d399` | `rgba(52, 211, 153, 0.15)` | Online status, success, verified memory, vault |
| `accent-amber`  | `#fbbf24` | `rgba(251, 191, 36, 0.15)` | Thinking, processing, tactical alerts, warnings |
| `accent-purple` | `#c084fc` | `rgba(192, 132, 252, 0.15)`| Neural reasoning, speech playback, cognitive router |
| `accent-rose`   | `#fb7185` | `rgba(251, 113, 133, 0.15)`| Bug reporting, destructive actions, stop/interrupt |

#### Text & Contrast Hierarchy
| Token | Value | Role |
| :--- | :--- | :--- |
| `text-primary` | `#f8fafc` | Primary high-contrast text (contrast ratio > 12:1) |
| `text-secondary`| `#cbd5e1` | Secondary descriptions, subheadings |
| `text-muted`    | `#94a3b8` | Metadata, timestamps, helper descriptions |
| `text-dim`      | `#64748b` | Placeholders, inactive hints, subtle keyboard shortcuts |

---

### B. Typography Scale
- **Primary Typeface**: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", sans-serif`
- **Monospace Typeface**: `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`

| Scale Token | Font Size | Line Height | Letter Spacing | Typical Usage |
| :--- | :--- | :--- | :--- | :--- |
| `font-2xs` | 10px | 14px | +0.5px | Status indicators, micro tags |
| `font-xs`  | 11px | 16px | +0.3px | Kbd hints, telemetry labels |
| `font-sm`  | 13px | 18px | 0px | Secondary labels, timestamps |
| `font-base`| 14px | 20px | -0.1px | Input fields, body text, assistant replies |
| `font-md`  | 16px | 24px | -0.2px | Card headers, section subheadings |
| `font-lg`  | 18px | 26px | -0.3px | Modal titles, drawer brand title |
| `font-xl`  | 22px | 28px | -0.4px | Hero header, gateway title |

---

### C. Spacing System
Standard 4px-based grid for visual harmony:
- `space-1`: 4px
- `space-2`: 8px
- `space-3`: 12px
- `space-4`: 16px
- `space-5`: 20px
- `space-6`: 24px
- `space-8`: 32px

---

### D. Corner Radii
- `radius-xs`: 4px (tags, keyboard shortcut badges)
- `radius-sm`: 6px (compact controls, tab pills)
- `radius-md`: 8px (standard buttons, form inputs, fact cards)
- `radius-lg`: 12px (modals, container frames, chat bubbles)
- `radius-xl`: 16px (large surface drawers, preview sheets)
- `radius-full`: 9999px (circular action icons, capsule pills)

---

### E. Shadows & Cybernetic Glow
- `shadow-sm`: `0 1px 3px rgba(0, 0, 0, 0.3)`
- `shadow-md`: `0 4px 14px rgba(0, 0, 0, 0.45)`
- `shadow-lg`: `0 12px 32px rgba(0, 0, 0, 0.65)`
- `shadow-modal`: `0 24px 60px rgba(0, 0, 0, 0.85)`
- `glow-cyan`: `0 0 16px rgba(56, 189, 248, 0.25)`
- `glow-emerald`: `0 0 16px rgba(52, 211, 153, 0.25)`
- `glow-amber`: `0 0 16px rgba(251, 191, 36, 0.25)`

---

### F. Motion & Transition Durations
- `motion-fast`: `150ms cubic-bezier(0.4, 0, 0.2, 1)` (hover states, tap feedback)
- `motion-normal`: `250ms cubic-bezier(0.4, 0, 0.2, 1)` (accordion collapse, tab switches)
- `motion-slow`: `350ms cubic-bezier(0.4, 0, 0.2, 1)` (drawer open/close, modal fade)

---

### G. Mobile & Touch Ergonomics
- **Minimum Tap Target**: `44px` height and width for every touch interactive control.
- **Dynamic Viewports**: Standardize on `dvh` (Dynamic Viewport Height) to prevent clipping under browser URL bars.
- **Safe Area Insets**: Respect `env(safe-area-inset-top)` and `env(safe-area-inset-bottom)` on iOS Safari/PWA standalone.
- **Keyboard Docking**: `#input-stage-wrapper` anchored directly above the virtual keyboard.
- **No Hover-Only Affordances**: Touch devices cannot hover; edit/delete/copy actions must always be discoverable via tap.
- **No Horizontal Scroll**: Strict `overflow-x: hidden` with word-break on long tokens.

---

### H. Information Architecture & Host Privacy
- **Host vs. Remote Scope**:
  - Remote users (guests/testers) must **NEVER** receive or see host hardware vitals (GPU temp, VRAM bars, NVMe disk metrics, or host control deck).
  - Telemetry buttons and host tool grids remain strictly hidden unless authenticated as host.

---

### I. Chat Thinking Trace Specification
- **Pill Header**: A clean, compact pill displaying `"Thought for Ns ▾"` when collapsed, pulsing indicator when thinking.
- **Natural Language Step Labels**: Step items must read as human-comprehensible sentences (e.g. `"Queried memory vault for user preferences"`, `"Researched live web for documentation"`).
- **Zero Raw JSON**: Raw model JSON blobs and technical stack traces must never appear in thought items.
- **Timer Freeze**: When text generation finishes or the turn completes, the timer interval freezes immediately and retains the exact duration.
