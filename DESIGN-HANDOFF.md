# SawtAI Product Experience — Design Handoff

## 1. Creative vision

SawtAI is a **living signal field** for government communication teams. It does not begin with modules or metrics; it begins with the decision that matters now, explains why it matters, and lets a human inspect evidence before acting.

The experience follows four principles:

1. **Priority before inventory** — the home surface presents one ranked focus, not a wall of KPIs.
2. **Evidence before automation** — every signal can be traced to source messages, model details, and confidence.
3. **Preview before action** — AI work is generated in a reviewable workspace and never silently published.
4. **Context before navigation** — tools appear around the current intention; the compact signal dock remains available everywhere.

## 2. Three design directions

### A. Living Signal Field — recommended

A calm editorial canvas with an asymmetric priority stage, live signal narratives, contextual workspaces, and a floating intent dock. Deep civic green conveys trust; warm parchment reduces dashboard fatigue; coral is reserved for risk; brass identifies AI assistance.

**Why:** immediately communicates focus, supports evidence-led decisions, scales to complex workflows, and remains understandable without a tutorial.

### B. Civic Constellation

Topics, cases, policies, and channels appear as spatial nodes around a selected public issue. Users move between related evidence by expanding clusters or invoking a radial command menu.

**Why:** makes relationships memorable and is powerful for exploration. It was not selected because dense operational workflows and keyboard accessibility become harder to maintain.

### C. Evidence Timeline

The product is organized as a continuous temporal narrative: what changed, what the AI inferred, what humans approved, and what happened afterward. Workspaces open as layers anchored to moments in time.

**Why:** excellent for crisis reconstruction, accountability, and executive storytelling. It was not selected as the sole model because drafting and database exploration are not naturally time-first tasks.

The final system uses Living Signal Field as its foundation and borrows the Evidence Timeline model inside crisis replay and audit history.

## 3. Information architecture

The product is organized around user intentions rather than departments:

| Intention | Current workspace | Outcome |
| --- | --- | --- |
| Orient | Mission brief | Know what needs attention now |
| Understand | Citizen voice | Inspect messages, classifications, sentiment, and lineage |
| Respond | Draft studio | Produce a grounded, reviewable response |
| Intervene | Crisis room | Understand risk drivers and execute a playbook |
| Verify | Data explorer | Inspect safe, tenant-scoped source records |

Global access is provided by the floating signal dock and `Cmd/Ctrl + K` natural-language command layer. Secondary functions such as settings, history, permissions, activity, and help should open as contextual layers rather than permanent navigation.

## 4. Primary journeys

### Morning decision

`Mission brief → priority signal → why this matters → evidence → crisis room → approve playbook`

The user receives one ranked focus, sees confidence and lead time, reviews the underlying messages, then chooses whether to intervene.

### Grounded response

`Mission brief or crisis room → draft studio → generate → inspect citation and checks → edit → approve`

Generation remains visibly in progress; policy grounding, safety checks, and abstention are explicit. Approval should create a versioned audit event and expose undo where the downstream action permits it.

### Investigate a metric

`Mission brief narrative → citizen voice → search/filter → select message → model evidence`

The detail layer explains sentiment, confidence, classification, dialect, model version, and lineage without separating the user from the source text.

### Verify source data

`Data explorer → choose schema table → preview rows → inspect safe fields`

The interface clearly identifies read-only mode, tenant scope, hidden restricted fields, and the record limit.

## 5. Wireframes

### Desktop mission brief

```text
 Brand                 Current entity                  Privacy  Alerts  User

 Good morning, Maryam                         Live
 One signal deserves attention now

 ┌───────────────────────────────────────┐ ┌──────────────────┐
 │ FOCUS NOW                             │ │ SAWTAI SUGGESTS  │
 │ Waste complaints rising              │ │ Grounded reply   │
 │ explanation + confidence       73     │ │ Preview first →  │
 │ [Open response] [Review evidence]     │ └──────────────────┘
 └───────────────────────────────────────┘

 Messages  |  Satisfaction  |  Cases  |  Alerts

 ┌────────────────────────────┐ ┌─────────────────┐
 │ Weekly signal narrative    │ │ Public mood     │
 └────────────────────────────┘ └─────────────────┘
 ┌────────────────────────────────────────────────┐
 │ Emerging topics as a prioritized stream        │
 └────────────────────────────────────────────────┘

       [Home] [Voice] [Draft] [Crisis] [Data] [Ask SawtAI]
```

### Mobile mission brief

```text
 Brand                                  EN  User
 Good morning, Maryam
 One signal needs attention

 ┌───────────────────────────┐
 │ FOCUS NOW                 │
 │ Waste complaints rising  │
 │                      73   │
 │ [Open] [Evidence]         │
 └───────────────────────────┘
 ┌───────────────────────────┐
 │ Suggested grounded reply  │
 └───────────────────────────┘
  Messages | Satisfaction
  Cases    | Alerts
  Signal story
  Public mood
  Topic stream

 [AI] [Home] [Voice] [Draft] [Crisis] [Data]
```

## 6. High-fidelity specification

### Color

| Token | Value | Purpose |
| --- | --- | --- |
| Canvas | `#F2EFE7` | Warm, low-fatigue environment |
| Paper | `#FFFDF8` | Focus surfaces and layers |
| Ink deep | `#0F302B` | Primary text, priority stage, navigation dock |
| Ink | `#173D37` | Body text |
| Muted | `#6F7D78` | Secondary information |
| Teal | `#176F65` | Evidence, positive state, interaction |
| Coral | `#D36152` | Risk, error, urgent negative change |
| Brass | `#C99C3D` | AI assistance and guided action |

Color is semantic. Coral must never decorate neutral content. Brass identifies AI help, not success. Text and controls must retain WCAG AA contrast in both themes if dark mode is later added.

### Type and spacing

- Primary: Manrope; Arabic: IBM Plex Sans Arabic; system fallbacks remain mandatory.
- Display: `34–64px`, medium weight, tight tracking.
- Body: `12–16px` depending on viewport and reading density.
- Metadata: `8–10px` only when nonessential; never use it for core instructions.
- Spacing follows a `4px` base with common steps `8, 12, 16, 24, 32, 48`.

### Shape and depth

- Priority surfaces use asymmetric `46px / 12px` corners to establish identity and direction.
- Standard contextual surfaces use `24–38px` corners; compact controls use `8–16px`.
- One restrained shadow level is used for floating layers. Hierarchy relies primarily on color, spacing, and placement.

## 7. Component and interaction rules

- **Signal dock:** fixed, compact, keyboard reachable, current workspace uses `aria-current`. Mobile scrolls horizontally without hiding destinations.
- **Command layer:** opens with `Cmd/Ctrl + K`, focuses its input, closes with Escape or backdrop, and routes natural-language intentions. Future AI actions must show a proposed plan before execution.
- **Priority signal:** one primary action and one evidence action. It must state magnitude, confidence, and expected value of intervention.
- **Evidence item:** source text is primary; model metadata is secondary. Selecting an item opens evidence in the adjacent context layer.
- **AI draft:** stream content progressively, retain the user prompt, show grounding citation, explain abstention, and require explicit approval.
- **Risk driver:** name, value, and proportional contribution appear together. Color cannot be the only indicator.
- **Data preview:** remains read-only, limits rows, hides restricted fields, and preserves table semantics for assistive technology.

## 8. Motion

- Page reveal: `380ms`, `translateY(10px)`, ease-out.
- Command layer: `250ms`, small upward movement and scale; backdrop `180ms` fade.
- Hover/focus feedback: `180–200ms`; never delay input.
- AI generation uses a text cursor and explicit status, not a decorative indefinite animation.
- Rearrangement should use direct manipulation with a visible destination and provide undo.
- `prefers-reduced-motion` reduces all motion to near-instant state changes.

## 9. AI interaction contract

Every proactive recommendation must expose:

1. **Action:** what SawtAI proposes.
2. **Reason:** evidence, rule, or user behavior behind the proposal.
3. **Impact:** what changes if approved.
4. **Control:** preview, edit, approve, reject, and undo when possible.

AI states are: `idle → understanding → retrieving evidence → generating → ready for review → approved/rejected`. Confidence is shown only where it is calibrated and meaningful. Low confidence triggers clarification or abstention rather than confident output.

## 10. System states

- **Loading:** skeletons preserve final layout and use non-blocking status text.
- **Empty:** explains why the space is empty and offers one relevant next action.
- **Error:** plain-language cause when known, safe retry, and no data loss.
- **Success:** confirms the completed outcome and provides the next step or undo.
- **AI processing:** names the current stage and lets the user cancel safely.
- **Offline/stale:** timestamps the last valid data and prevents misleading live labels.

## 11. Accessibility and localization

- Use semantic headings, landmarks, forms, tables, and buttons; all workflows are keyboard operable.
- Maintain visible `3px` focus rings and a skip link.
- Do not communicate sentiment or risk using color alone.
- Target WCAG 2.2 AA, `44px` touch targets, and 200% zoom without loss of function.
- Arabic and English share logical CSS properties and mirrored reading order; charts and codes preserve deliberate direction.
- Dialogs require focus containment and focus restoration as the command layer gains more controls.
- Dynamic generation and alerts should use polite live regions; emergencies must not rely on repeated audio.

## 12. Clickable prototype map

| Route | Prototype target |
| --- | --- |
| `?page=overview` | Adaptive mission brief and priority actions |
| `?page=voice` | Search, sentiment filtering, evidence selection |
| `?page=draft` | Prompt, streamed generation, citation, safety checks |
| `?page=crisis` | Risk replay, drivers, response playbook |
| `?page=data` | Schema catalog and safe row preview |
| `Cmd/Ctrl + K` | Universal command layer from every route |

## 13. Developer handoff

- Design tokens live in `services/web/src/styles.css`; database-specific layout lives in `services/web/src/data.css`.
- Shared icon geometry lives in `services/web/src/components/Icon.tsx`; use it instead of emoji or mixed icon libraries.
- Feature modules own data queries and task behavior; `App.tsx` owns navigation, locale, and the command layer.
- Add new destinations as intentions, not product departments. Prefer contextual layers until a workflow justifies a dock destination.
- New AI mutations must include a preview model, approval event, audit metadata, safe failure behavior, and undo design before implementation.
- Validate desktop, tablet, mobile, LTR, RTL, keyboard-only, reduced motion, loading, empty, error, and stale-data states before release.
