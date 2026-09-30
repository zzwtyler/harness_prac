---
name: "任务清样"
description: "A proof-desk workbench for compressing fuzzy requests into inspectable task specifications."
colors:
  paper: "#f3f5f7"
  sheet: "#ffffff"
  ink: "#111820"
  muted-ink: "#596674"
  faint-ink: "#64717f"
  rule: "#cbd2d9"
  rule-strong: "#9ca8b3"
  registration-blue: "#1557ff"
  registration-blue-deep: "#0c3db9"
  process-chartreuse: "#b9f227"
  process-chartreuse-ink: "#243600"
  proof-error: "#b82b36"
  proof-error-paper: "#fff0f1"
  focus-blue: "#6b8dff"
typography:
  display:
    fontFamily: 'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'
    fontSize: "clamp(38px, 5.2vw, 76px)"
    fontWeight: 820
    lineHeight: 0.98
    letterSpacing: "-0.04em"
  headline:
    fontFamily: 'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'
    fontSize: "clamp(23px, 3vw, 38px)"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.035em"
  title:
    fontFamily: 'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'
    fontSize: "13px"
    fontWeight: 800
    lineHeight: 1.5
  body:
    fontFamily: 'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.7
  body-input:
    fontFamily: 'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.75
  label:
    fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", monospace'
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: "0.08em"
  mono-body:
    fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", monospace'
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.7
rounded:
  square: "0"
  control: "2px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  control: "18px"
  lg: "24px"
  panel: "28px"
  section: "40px"
  frame: "48px"
components:
  button-primary:
    backgroundColor: "{colors.registration-blue}"
    textColor: "{colors.sheet}"
    typography: "{typography.title}"
    rounded: "{rounded.square}"
    padding: "0 18px"
    height: "60px"
  button-primary-hover:
    backgroundColor: "{colors.registration-blue-deep}"
    textColor: "{colors.sheet}"
    rounded: "{rounded.square}"
  button-primary-disabled:
    backgroundColor: "#ccd2d7"
    textColor: "#69747f"
    rounded: "{rounded.square}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.square}"
    padding: "0 12px"
    height: "34px"
  button-secondary-hover:
    backgroundColor: "transparent"
    textColor: "{colors.registration-blue-deep}"
    rounded: "{rounded.square}"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.registration-blue-deep}"
    typography: "{typography.label}"
    rounded: "{rounded.square}"
    padding: "0"
  composer-input:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.body-input}"
    rounded: "{rounded.square}"
    padding: "22px 20px"
  field-control:
    backgroundColor: "rgb(255 255 255 / 62%)"
    textColor: "{colors.ink}"
    typography: "{typography.mono-body}"
    rounded: "{rounded.control}"
    padding: "0 10px"
    height: "40px"
  toggle-track:
    backgroundColor: "{colors.rule-strong}"
    rounded: "{rounded.square}"
    width: "38px"
    height: "22px"
  toggle-track-checked:
    backgroundColor: "{colors.registration-blue}"
    rounded: "{rounded.square}"
    width: "38px"
    height: "22px"
  process-step:
    backgroundColor: "transparent"
    textColor: "{colors.faint-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.square}"
    padding: "12px 0 0"
  thinking-panel:
    backgroundColor: "#e9edf1"
    textColor: "{colors.muted-ink}"
    typography: "{typography.mono-body}"
    rounded: "{rounded.square}"
    padding: "24px 20px 48px"
  result-panel:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.square}"
    padding: "28px"
---

# Design System: 任务清样

## Overview

**Creative North Star: "The Typesetter's Proof Desk"**

The Typesetter's Proof Desk treats task normalization as production work: the prompt is source copy, reasoning is a ruled margin annotation, and the four-field result is the signed-off proof. The interface is one continuous sheet with a narrow settings rail, not a stack of floating cards or chat bubbles.

The system feels procedural but not sterile. Near-black ink and cool paper establish editorial authority; registration blue marks action and progress; chartreuse appears only as a live process signal. Crisp rules carry most of the structure, while short, physical-feeling transitions confirm state changes without turning model latency into spectacle.

**Key Characteristics:**

- Continuous proof-sheet topology with a sticky settings rail and one bordered working surface.
- Cool paper, white stock, near-black ink, registration blue, and a rare chartreuse process signal.
- Heavy Chinese-first sans headlines paired with true monospace labels, counts, traces, and JSON.
- Square geometry, dense production labels, and crisp one-pixel rules instead of soft card chrome.
- Explicit waiting, thinking, output, failure, disabled, and copied states, with reduced-motion support.

## Colors

The palette reads like a cool production proof: quiet blue-gray stock and rules, dense ink, one saturated registration color, and one narrowly assigned process signal.

### Primary

- **Registration Blue:** The only broad action color. It fills the submit control, advances the process rule, marks list bullets, and identifies checking or interactive states.
- **Deep Registration Blue:** The legible interaction companion used for text actions, field indices, summaries, and primary hover states.
- **Focus Blue:** A lighter, unmistakable keyboard-focus outline kept distinct from both borders and hover color.

### Secondary

- **Process Chartreuse:** A sparse live-state signal used for successful local availability, active reasoning, and the “still unknown” proof marker.
- **Process Chartreuse Ink:** Dark text reserved for content placed directly on the chartreuse signal.

### Tertiary

- **Proof Error:** Failure status and error emphasis.
- **Proof Error Paper:** The pale error notice surface; it keeps recovery guidance readable without competing with the main action.

### Neutral

- **Cool Paper:** The application canvas and page ground.
- **Clean Sheet:** The composer and result stock.
- **Proof Ink:** Primary copy, heavy rules, stamps, and field markers.
- **Muted Ink:** Supporting copy, captions, and descriptive status.
- **Faint Ink:** Inactive progress steps and disabled secondary labels.
- **Fine Rule:** Internal dividers and ledger lines.
- **Strong Rule:** Panel edges, field borders, and structural separations.

### Named Rules

**The Registration Rule.** Blue means action, progress, or focus; chartreuse means a live or exceptional process condition. Neither color is decorative fill.

## Typography

**Display Font:** System sans with Chinese-native platform fallbacks.
**Body Font:** The same system sans stack for compact, dependable local rendering.
**Label/Mono Font:** SFMono-Regular with Consolas and Liberation Mono fallbacks.

**Character:** The sans stack supplies assertive editorial mass without a font download; the mono stack turns system content, state labels, counters, metrics, reasoning, and JSON into production evidence. Weight, spacing, and column structure create the hierarchy.

### Hierarchy

- **Display** (820, `clamp(38px, 5.2vw, 76px)`, 0.98): The two-line page thesis; it tightens to `clamp(36px, 11vw, 48px)` on mobile.
- **Headline** (700, `clamp(23px, 3vw, 38px)`, 1.25): The generated goal, kept to a readable maximum of about 28 characters per line.
- **Title** (800, 13px, 1.5): Panel headings, field titles, and primary action copy.
- **Body** (400, 15px, 1.7): Introductory explanation; compact result copy steps down to 13px with a 1.65 line-height.
- **Input Body** (400, 17px, 1.75): The source-task composer, large enough for sustained Chinese text entry.
- **Label** (700, 11px, 0.08em tracking): Uppercase production stamps, field indices, and settings labels.
- **Mono Body** (400, 11px, 1.7): Reasoning, JSON, model metadata, counters, and footer metrics.

### Named Rules

**The Evidence Is Mono Rule.** Use monospace for machine-originated or machine-adjacent material; keep instructions, goals, and human-readable outcomes in sans.

## Layout

The desktop shell uses a fixed 290px settings rail beside a fluid workbench capped at 1380px. The workbench begins with 48px vertical padding and horizontal padding that scales from 28px to 72px. Its content flows as one sequence: thesis, compact expandable project-background strip, composer, three-step process rule, then an asymmetric proof grid with a narrow reasoning column (`minmax(250px, 0.36fr)`) and a wider structured-result column.

Spacing follows an 8–12–16–18–24–28–40–48px working rhythm. Borders, padding shifts, and changes in background stock define regions; avoid adding independent outer margins that make the page read as detached cards.

At 1040px the rail narrows to 250px, the reasoning column tightens to `minmax(220px, 0.32fr)`, and the result’s constraint/unknown columns stack. At 760px the rail becomes a static top band with collapsible settings, the workbench uses 16px side gutters, the schema stamp disappears, the primary action spans the composer, and the proof columns stack vertically. At 480px result actions become two equal-width 44px controls and error notices collapse to one column. The layout remains usable at the implemented 320px minimum width.

**The One Continuous Sheet Rule.** Preserve the rail-plus-proof relationship and shared borders; do not recast the workbench as a dashboard of unrelated cards.

## Elevation & Depth

The system is flat by default. Depth comes from tonal stock changes, ruled subdivisions, and occasional heavier ink rules; it does not use ambient shadows on primary surfaces. Shadows appear only on transient or tiny state affordances: the toggle thumb, online/live dots, and the toast.

### Shadow Vocabulary

- **Online Status:** `0 3px 8px rgb(86 140 0 / 24%)` gives the availability dot a faint operational glow.
- **Toggle Thumb:** `0 2px 5px rgb(17 24 32 / 18%)` separates the white switch thumb from its track.
- **Live Reasoning:** `0 2px 9px rgb(113 157 0 / 35%)` makes the chartreuse live dot legible without lifting its panel.
- **Toast:** `0 10px 28px rgb(17 24 32 / 20%)` is the sole pronounced overlay shadow.

### Named Rules

**The Flat Proof Rule.** Structural surfaces stay flat; reserve shadow for ephemeral feedback and small physical controls.

## Shapes

The form language is almost entirely square. Panels, buttons, stamps, progress marks, and result indices use hard corners; select and system-prompt fields alone soften to a restrained 2px radius. One-pixel cool-gray rules define ordinary partitions, while 3–4px near-black rules mark the composer and signed-off goal hierarchy.

**The No Soft Card Rule.** Do not introduce pills, floating rounded cards, or oversized corner radii; this world is cut paper, rules, and registration marks.

## Components

### Buttons

- **Primary:** A full-height registration-blue slab attached directly to the composer action band, with 18px horizontal padding and a minimum 220px desktop width. Hover deepens the blue; loading replaces the label, changes to a neutral disabled stock, and keeps the action visibly anchored.
- **Secondary:** Transparent, square, one-pixel outlined controls at 34px desktop height; hover shifts text and border to blue. At the narrow breakpoint they grow to 44px touch targets.
- **Text:** Small deep-blue underlined actions with no container fill. Use for low-risk recovery and examples, never as the page’s main action.
- **Focus:** Every keyboard-focusable control receives the same 3px focus-blue outline with a 3px offset; the composer uses an inset offset so the ring is not clipped.

### Cards / Containers

- **Composer:** White stock with a strong 4px ink top rule, a labeled header, an unboxed writing area, and an attached gray action band.
- **Thinking Panel:** A cool ledger surface with 28px horizontal ruling, a separated heading, monospace streamed content, and a chartreuse live indicator.
- **Result Panel:** Clean white stock. The generated goal ends in a 3px ink rule; constraints and unknowns share a ruled two-column proof; acceptance rows use numbered blue markers; raw JSON stays behind a disclosure.
- **Error Notice:** Pale error stock, a one-pixel error-tinted border, and explicit recovery copy in a two-column strip that stacks on narrow screens.

### Inputs / Fields

- **Composer Input:** Borderless within its parent sheet, with 22px × 20px padding, a 148px minimum height, a blue caret, and a visible inset focus ring.
- **Settings Fields:** Translucent white stock, one-pixel strong rule, and 2px corners. Focus turns the stock opaque and the border blue.
- **Switch:** A square 38px × 22px track with a 14px white thumb. Checked state turns registration blue; the accessible native checkbox remains the source of truth.

### Navigation

- **Progress Rule:** Three equally distributed steps sit above a one-pixel rule. A 3px blue fill grows from the left as state advances; only current and completed labels use proof ink.
- **Settings Rail:** Sticky for desktop scanning, then converted into a top band below 760px. Mobile settings are closed by default behind a 44px disclosure control with synchronized `aria-expanded` state.

### Motion and Feedback

- Use 160ms ease-out for switches and the settings disclosure, 180ms ease-out for toast opacity/translation, and 420ms `cubic-bezier(0.22, 1, 0.36, 1)` for the progress fill.
- Checking and live-reasoning dots pulse at roughly one second; the pulse conveys activity, not decoration.
- When `prefers-reduced-motion: reduce` is active, scrolling becomes immediate and all animations/transitions collapse to 0.01ms with a single iteration.
- Status and error text update independently from decorative dots. Thinking and toast regions use polite live announcements; errors use an alert role.

**The State Must Read Twice Rule.** Every important state uses both text and a visual treatment, so color or motion is never the only signal.

## Do's and Don'ts

### Do:

- **Do** preserve the composer → progress rule → reasoning/result proof sequence on every viewport.
- **Do** keep reasoning and final JSON in separate semantic and visual layers.
- **Do** use chartreuse only for live, available, or unresolved process signals.
- **Do** maintain visible keyboard focus, a skip link, polite live regions, and 44px mobile targets where implemented.
- **Do** keep future Chinese copy compact enough for the 320px layout and let long model output wrap anywhere.

### Don't:

- **Don't** introduce chat bubbles, detached floating cards, or a conversation transcript layout.
- **Don't** use blue or chartreuse as broad decoration; their rarity makes process state legible.
- **Don't** round panels and actions beyond the established square or 2px control geometry.
- **Don't** merge thinking, streamed JSON, parsed fields, and failure feedback into one undifferentiated output area.
- **Don't** add motion without the reduced-motion collapse or rely on animation alone to communicate progress.
