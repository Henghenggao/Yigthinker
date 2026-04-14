# Historical Dashboard Design Tokens

Archived design tokens and component specifications for the removed web dashboard.
Source: CEO Plan 2026-04-07 (Web Dashboard Design Spec section).

The shipped product is headless (`CLI + Gateway + TUI + IM channels`), so this
document is retained only as historical reference for earlier terminology.

## CSS Custom Properties

```css
:root {
  /* Light theme (default) */
  --bg-primary:    #ffffff;  /* white, main background */
  --bg-surface:    #f8fafc;  /* light gray, elevated surfaces */
  --bg-input:      #f1f5f9;  /* input fields */
  --bg-hover:      #e2e8f0;  /* hover state */
  --text-primary:  #0f172a;  /* navy, main text */
  --text-secondary:#475569;  /* labels, timestamps */
  --text-muted:    #94a3b8;  /* placeholders */
  --accent:        #3b82f6;  /* blue, links, active states */
  --success:       #16a34a;  /* green, connected, done */
  --error:         #dc2626;  /* red, errors, disconnected */
  --warning:       #ca8a04;  /* yellow, connecting */
  --border:        #e2e8f0;  /* subtle borders */
  --font-sans:     "Inter", system-ui, sans-serif;
  --font-mono:     "JetBrains Mono", "Fira Code", monospace;
  --radius-sm:     4px;      /* inputs, small cards */
  --radius-md:     8px;      /* panels, modals */
}

[data-theme="dark"] {
  --bg-primary:    #0f172a;
  --bg-surface:    #1e293b;
  --bg-input:      #334155;
  --bg-hover:      #475569;
  --text-primary:  #f8fafc;
  --text-secondary:#94a3b8;
  --text-muted:    #64748b;
  --border:        #334155;
  /* accent, success, error, warning stay the same */
}
```

## Color Palette

Palette: Tailwind Slate. Light theme default for corporate finance users. Dark toggle available. Both themes use CSS custom properties so switching is a single attribute change.

| Token | Light Value | Dark Value | Usage |
|-------|-------------|------------|-------|
| `--bg-primary` | `#ffffff` | `#0f172a` | Main background |
| `--bg-surface` | `#f8fafc` | `#1e293b` | Elevated surfaces (cards, panels) |
| `--bg-input` | `#f1f5f9` | `#334155` | Input fields |
| `--bg-hover` | `#e2e8f0` | `#475569` | Hover state |
| `--text-primary` | `#0f172a` | `#f8fafc` | Main text |
| `--text-secondary` | `#475569` | `#94a3b8` | Labels, timestamps |
| `--text-muted` | `#94a3b8` | `#64748b` | Placeholders |
| `--accent` | `#3b82f6` | `#3b82f6` | Links, active states |
| `--success` | `#16a34a` | `#16a34a` | Connected, done |
| `--error` | `#dc2626` | `#dc2626` | Errors, disconnected |
| `--warning` | `#ca8a04` | `#ca8a04` | Connecting |
| `--border` | `#e2e8f0` | `#334155` | Subtle borders |

## Typography

- `--font-sans`: "Inter", system-ui, sans-serif (body text, labels, headings)
- `--font-mono`: "JetBrains Mono", "Fira Code", monospace (SQL, code blocks, tool output)

## Border Radius

- `--radius-sm`: 4px (inputs, small cards)
- `--radius-md`: 8px (panels, modals)

## Component States

| Component | Loading | Empty | Error | Success | Streaming |
|---|---|---|---|---|---|
| Conversation | Skeleton bubbles | Welcome + samples | "Connection lost" + retry | Messages with Markdown | Token-by-token + cursor |
| Inline chart | Shimmer placeholder | -- | "Chart failed" + data table | Interactive Plotly | -- |
| Tool card | Spinner + name | -- | Red dot + error msg | Green dot + "done" | Running + elapsed timer |
| DataFrame table | Skeleton rows | "No rows returned" | "Query error" + message | Rich table with sort | Progressive rows |
| Vars panel | -- | "No data loaded yet" | -- | Variable list + shapes | Updates live |
| Connection | "Connecting..." yellow | "No DB connected" | "DB unreachable" red | "oracle" green | -- |
| Input bar | Disabled during response | Placeholder text | Disabled + error tooltip | Active | Disabled during stream |

## Screen Layout

```
+-------------------------------------------------+
| HEADER: [Yigthinker] [Session: v] [Model v] [DB]|
+----------------------+--------------------------+
| CONVERSATION (70%)   | CONTEXT PANEL (30%)      |
| +----------------+   | +- DataFrames ----------+|
| | Chat messages   |   | | revenue_q2  (500x12)  ||
| | + inline charts |   | | anomalies   (47x3)    ||
| | + tool cards    |   | +----------------------+|
| +----------------+   | +- Connections ---------+|
| +----------------+   | | oracle-prod  * Online ||
| | Input bar       |   | +----------------------+|
| +----------------+   |                          |
+----------------------+--------------------------+
| STATUS: Connected | Session: 12 msgs | 3 vars   |
+-------------------------------------------------+
```

Visual hierarchy: Conversation (1st) > Input bar (2nd) > Context panel (3rd) > Header (4th) > Status bar (5th)

## Responsive Breakpoints

- **Desktop (1280px+):** Full 70/30 split layout
- **Laptop (1024-1279px):** Vars panel collapses to icon-only sidebar or overlay
- **Tablet (768-1023px):** Vars panel becomes bottom sheet or toggle drawer
- **Mobile (<768px):** Deferred -- show "Open on desktop for the best experience" message

## Accessibility Requirements

- Keyboard: Tab through input > chat > vars panel > header actions
- Focus indicators: Blue outline visible on dark background
- ARIA landmarks: main (chat), complementary (vars), banner (header)
- Color contrast: All text meets WCAG 2.1 AA (#f8fafc on #0f172a = 15.4:1)
- Touch targets: 44px minimum for buttons and interactive elements
- Reduced motion: Streaming cursor respects prefers-reduced-motion

## Tool Call Display

Tool cards: slim accordion bars, collapsed by default. Icon + tool name + status indicator.
Styling: subtle background (--bg-surface), no colored left borders.

## Not in Scope

- Mobile viewport support (<768px)
- Full user accounts + SSO (deferred to external customer deployment)
- PDF/Excel/PPT export UI (deferred per CEO review)
- Scheduled reports UI (deferred per CEO review)
- Multi-language UI / i18n (deferred per CEO review)
- Full design system / component library (minimal tokens only)
- Dark/light theme toggle (dark theme only for now)
