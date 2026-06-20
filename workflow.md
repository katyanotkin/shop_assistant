# Agent Workflow

Standard agent invocation order for VerbBoard feature work. Each phase gates the next.

## Phase 1 -- Explore (always first)

Use `Explore` agent before touching any code. Search for relevant files, existing patterns, callers of the function being changed. Quick for a targeted lookup; very thorough for cross-cutting changes.

Skip only when the file and line are already known and the change is isolated.

## Phase 2 -- Design (before writing code)

| Trigger | Agent |
|---|---|
| Cross-cutting state, shared functions, infra changes | `senior-architect` |
| New feature with multi-file scope | `Plan` |
| Small, self-contained change | Skip -- proceed inline |

Never start implementation until design is settled.

## Phase 3 -- Implement

| Task type | Agent or inline |
|---|---|
| UI layout, CSS, interaction | `ui-ux-engineer` |
| Backend Python, data model | Inline (main context) |
| Writing/copy/changelog | `writer` |
| Any other code | Inline |

## Phase 4 -- Review (after every code change)

`code-reviewer` -- always invoke after writing or modifying code, before calling qa-engineer.

## Phase 5 -- Tests (after reviewer approves)

`qa-engineer` -- writes or updates tests. Invoke only after code-reviewer has approved. Never write tests before the reviewer runs.

## Phase 6 -- Verify (optional, UI changes)

Use `/verify` skill to confirm the feature works in the live app. Required for any UI golden-path change.

## Phase 7 -- Docs (after any significant feature addition)

Invoke the `writer` agent to update **README.md** after any user-facing feature is added or changed. Significant means: new admin capability, new user workflow, new endpoint, changed behaviour a user would notice.

Do not update README inline -- delegate to the writer agent. Brief the agent with: what changed, what sections to update, what not to touch.

---

Trivial one-liners (typo fix, single-constant change): phases 2, 5, and 7 may be skipped.

---

## Creating a new search (user workflow)

Start in the **Explore** phase — never go straight to the structured form.

1. **Explore** — click "+ New search" in admin sidebar. Describe what you want in free-form text (material, style, price, size). Gemini generates an initial structured config.
2. **Review** — inspect the generated fields; edit anything that looks wrong or missing.
3. **Save & Run** — run the first search to see candidates; use feedback to refine over time.
