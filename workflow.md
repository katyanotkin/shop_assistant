# Agent Workflow

Standard agent invocation order for TailoredLoop feature work. Each phase gates the next.

## Phase 1 — Explore (always first)

Use `Explore` agent before touching any code. Search for relevant files, existing patterns, callers of the function being changed. Quick for a targeted lookup; very thorough for cross-cutting changes.

Skip only when the file and line are already known and the change is isolated.

## Phase 2 — Design (before writing code)

| Trigger | Agent |
|---|---|
| Cross-cutting state, shared functions, infra changes | `senior-architect` |
| New feature with multi-file scope | `Plan` |
| Small, self-contained change | Skip — proceed inline |

Never start implementation until design is settled.

## Phase 3 — Implement

| Task type | Agent or inline |
|---|---|
| UI layout, CSS, interaction | `ui-ux-engineer` |
| Backend Python, data model | Inline (main context) |
| Writing/copy/changelog | `writer` |
| Any other code | Inline |

## Phase 4 — Review (after every code change)

Invoke `code-reviewer` after every code write/modify, before calling `qa-engineer`.

Brief the reviewer with an explicit checklist, not just the diff. The checklist must cover:

- **Auth/cookie propagation** — every `fetch()` or `api()` call that hits a protected endpoint must include `credentials: "same-origin"`. Trace each call to its declaration and verify.
- **New public state** — every new `isAdmin`, `isLoggedIn`, or similar flag: what happens if it's stale, never set, or set out of order?
- **Removed guards** — for every deleted line, name the invariant it enforced and confirm the new code re-establishes it.
- **Cross-file callers** — for every changed function signature or return shape, grep callers and verify each still works.
- **XSS** — every value inserted via `innerHTML` must pass through `esc()`.

If the reviewer returns findings, fix them before proceeding to Phase 5.

## Phase 5 — Tests (after reviewer approves)

`qa-engineer` — writes or updates tests. Invoke only after code-reviewer has approved. Never write tests before the reviewer runs.

## Phase 6 — Verify (optional, UI changes)

Use `/verify` skill to confirm the feature works in the live app. Required for any UI golden-path change.

## Phase 7 — Docs (after any significant feature addition)

Invoke the `writer` agent to update **README.md** after any user-facing feature is added or changed. Significant means: new admin capability, new user workflow, new endpoint, changed behaviour a user would notice.

Do not update README inline — delegate to the writer agent. Brief the agent with: what changed, what sections to update, what not to touch.

---

Trivial one-liners (typo fix, single-constant change): phases 2, 5, and 7 may be skipped.

---

## Creating a new search (user workflow)

Admin is integrated into the results page — there is no separate admin page.

1. **Sign in** — click "Admin" in the top-right corner. Enter the admin password in the modal.
2. **New search** — in the admin panel (opens from the Edit button in the toolbar), use the "+ New search" flow: describe what you want in free-form text; Gemini generates an initial structured config.
3. **Review** — inspect the generated fields in the edit panel; edit anything wrong or missing.
4. **Save & Run** — run the first search to see candidates; use the feedback area under each result card to refine over time.
