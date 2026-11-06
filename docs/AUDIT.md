# UI Visual Audit & Inconsistency Report (Item 1)

This visual audit evaluates the visual consistency, responsive responsiveness, accessibility, and cybernetic identity across Project Libra's Web UI (PWA) and Desktop GUI (PyQt6).

## Evidence Collected
64 pixel-accurate screenshots have been generated and archived in `docs/screenshots/audit/`:
- **Web UI (390px - Mobile)**: 19 screens covering main chat (empty/hero), active conversation, expanded thinking trace, drawer navigation, and all 15 modals/sub-views.
- **Web UI (820px - Tablet/iPad)**: 19 screens covering the same operational states in tablet viewport.
- **Web UI (1280px - Desktop/Laptop)**: 19 screens covering wide-screen desktop viewport.
- **Desktop GUI (PyQt6)**: 7 screen states covering `idle`, `listening`, `thinking`, `speaking`, `vault` (`MemoryVaultWidget`), `floating_pill` (`FloatingHUDPill`), and `spotlight` (`SpotlightBar`).

---

## 1. Discovered Inconsistencies

### A. Spacing & Padding
- **Modals**: Extreme padding divergence. `#briefing-modal` uses `padding: 14px`, `#options-modal` uses `padding: 16px`, `#vault-modal` uses `padding: 16px`, `#artifact-preview-modal` sets `padding: 0`, and `#bug-report-modal` uses `padding: 20px`. No unified modal padding token exists.
- **Card Elements**: `.briefing-vital-card` (8px padding), `.vault-card` (10px padding), `.token-card` (12px padding), `.user-row-item` (10px padding).
- **Header Elements**: Web header has varying button gaps (8px vs 10px vs 12px).
- **Desktop GUI**: `FuturisticVoiceAssistantUI` sets outer margin to `(20, 16, 20, 16)` and spacing to `12`, while `MemoryVaultWidget` uses margins `(16, 16, 16, 16)` and spacing `10`, and `FactCard` uses margins `(12, 10, 12, 10)`.

### B. Typography & Font Hierarchy
- **Web Font Stack**: Defined as `--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", Helvetica, Arial, sans-serif;`. However, numerous modal elements override this with ad-hoc inline styles: `font-size: 11.5px`, `font-size: 13px; font-weight: 700`, `font-family: monospace; font-size: 11px`.
- **Erratic Size Steps**: Font sizes jump between 7px, 8px, 9px, 10px, 11px, 11.5px, 12px, 13px, 14px, 15px, 16px, and 18px without a standardized type scale.
- **Desktop GUI Fonts**: Hardcoded `"Segoe UI", 7`, `"Segoe UI", 8`, `"Segoe UI", 9`, `"Segoe UI", 10`, `"Segoe UI", 16`, but `SpotlightBar` and `FloatingHUDPill` use different font weights and sizes for equivalent labels.

### C. Color Palette & Cybernetic Identity
- **Modal Accent Fragmentation**: Every modal arbitrarily picks a different neon accent with no semantic logic:
  - Daily Briefing: `#f59e0b` (amber)
  - Memory Vault: `#00ffcc` (cyan-green)
  - AirDrop Bridge: `#38bdf8` (sky blue)
  - Guest Invites: `#a855f7` (purple)
  - Users: `#00f2fe` (neon cyan)
  - Bug Report: `#fb7185` (rose/red)
  - Artifact Preview: `var(--neon-cyan)`
- **Background Inconsistencies**: Surface backgrounds jump between `#09090b` (zinc-950), `#0d0d11`, `#121215`, `#18181b` (zinc-900), `#202024`, `#091220` (navy-blue), `#050b14`, `#020617` (slate-950), and `#0f172a`.
- **Desktop GUI State Colors**:
  - `SPEAKING`: `#160f29` / `#c084fc` / `#9333ea`
  - `RECORDING/LISTENING`: `#092019` / `#34d399` / `#059669`
  - `THINKING/PROCESSING`: `#231608` / `#fbbf24` / `#d97706`
  - `IDLE`: Linear gradient `#091322` to `#13243d` with border `#00e5ff`
  - System metrics and space bar badge use ad-hoc amber/emerald transparencies that clash with the dark slate background.

### D. Corner Radii
- **Web Radii**:
  - Inputs use `border-radius: 4px`, `6px`, `8px`, or `24px` interchangeably.
  - Buttons use `border-radius: 4px`, `6px`, `8px`, `12px`, `20px`, `9999px`.
  - Cards use `border-radius: 4px`, `6px`, `8px`, `12px`, `16px`.
- **Desktop GUI Radii**:
  - Main window container uses `12px`.
  - Buttons use `6px` or `8px`.
  - Status banner uses `6px` or `8px`.
  - Floating HUD Pill uses `24px`.
  - Memory Vault fact cards use `8px`.

### E. Touch Tap Targets & Mobile Ergonomics (<44px violations)
- **Small Mobile Buttons**:
  - `#close-drawer-btn`: 28x28px (<44px).
  - `#remove-attachment-btn`: 24x24px (<44px).
  - Modal close buttons (`.modal-close-btn`): 32x32px (<44px).
  - Sub-action buttons (e.g. `#restart-cf-btn` `padding: 4px 8px; font-size: 10px`, `#refresh-bugs-btn` `padding: 3px 10px; font-size: 11px`) have heights ~22px (<44px target).
- **Floating Scroll Button**: `#scroll-to-bottom-btn` has 32px height and lacks adequate thumb padding on mobile.

### F. Layout, Viewport & Responsive Flaws
- **390px Mobile Viewport**:
  - Options modal has a rigid 2-column input row (`Preferred Name` flex: 1 and `Location` fixed 170px) which squishes or clips on narrow phones.
  - Header actions wrap or overflow when title is long.
  - Fixed-height modals with `max-height: 440px` do not adapt well to mobile screen height (dvh) or virtual on-screen keyboards.
  - Bottom input bar needs `env(safe-area-inset-bottom)` and dynamic viewport height handling so it remains anchored above mobile software keyboards.
- **820px iPad Viewport**:
  - Content stretches excessively horizontally without balanced max-widths or column balancing for multi-column modals (Vault cards, Token cards).

### G. Host-Only Information Leakage to Remote Users
- While `#vitals-container` and `#token-hud-btn` have `display: none` for non-hosts, Daily Tactical Briefing modal and Options modal still display or allow remote navigation to GPU telemetry, NVMe storage stats, and host deck controls. Remote scopes must strictly hide host hardware internals.

### H. Chat Thinking Trace
- **Accordion Label**: Shows chevron text characters (`▾`, `>`).
- **Step Items**: Some steps display raw action text (`Ran click (320, 480)`) or technical debug strings rather than polished natural-language steps.
- **Timer Behavior**: Needs strict freeze on stream completion, and a clean collapsed "Thought for Ns" pill.

### I. Desktop GUI Settings
- Desktop GUI currently lacks an integrated settings dialog, relying entirely on the web interface or direct `config.json` modification.
