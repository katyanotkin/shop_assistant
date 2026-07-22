# Handoff

Last touched: 2026-07-22 (HEAD at `862fe42`, "perf: parallelize search/rank
pipeline, drop unjustified pacing delay"). This note orients whoever — human
or Claude session — picks the project up next. For feature/user-journey
detail see [PRODUCT.md](PRODUCT.md); for pipeline/data-model/API detail see
[ARCHITECTURE.md](ARCHITECTURE.md); for the full history see `git log`.

## Uncommitted changes right now — deal with these first

`git status` shows unstaged edits to `ARCHITECTURE.md` and `PRODUCT.md` (a
doc-sync pass for the perf/infra work in the last few commits, apparently
started but never committed):

- `ARCHITECTURE.md`: adds a "Request timeout" and "Concurrency / CPU" row to
  the infra table, documenting `--timeout=600` and
  `--concurrency=1 --no-cpu-throttling`.
- `PRODUCT.md`: updates the run-time estimate from "a few minutes" to "about
  a minute... search, fetch, and scoring all happen concurrently."

Both changes are accurate as of HEAD (verified against `cloudbuild.yaml` and
`core/searcher.py`/`core/ranker.py`). Either commit them or decide they're
not wanted — don't just leave them dangling.

## Product state

The product is a working multi-user web app with three roles (free, premium,
admin) and a working search → fetch → rank → results pipeline. Recent work
(last ~10 commits, all deployed to `shopassistant.verbboard.com`) covered:

- **Search quality**: dropped listing/category pages before scoring, deduped
  candidates by resolved URL, fed real fetched text for reference products
  instead of a bare URL, lowered the feedback-learning threshold to 1 item,
  and stopped silently dropping overall run notes from learning.
- **Privacy fix**: private searches now 404 (indistinguishable from
  nonexistent) for non-owners at the API, not just the UI.
- **Premium tier**: 2 new-or-cloned searches/UTC-day, 90-day run window,
  100 runs/month, vs. free's 1 search / 30-day window / 20 runs/month, admin
  ungated. Includes public-search cloning (`POST
  /api/user/search/{source}/clone`, criteria + preferred_shops only — never
  feedback/pins/references) and redaction of personal-signal layers
  (feedback, pinned finds, reference products, learned notes) from non-owner
  viewers on searches an admin has promoted to public.
  **These specific numbers (2/day, 90-day, 100/month) are explicitly
  provisional** — the product owner called them "for now," pending a chosen
  payment provider. See PRODUCT.md's "Future: subscription model" section
  before treating them as fixed.
- **Two production bugs found live and fixed**: a run with zero matches used
  to crash instead of showing an empty result (CSV fieldnames bug); editing
  any search with a numeric `max_price` crashed the edit panel in both admin
  and user UI (JS coercion gap in `criteria-form.js`).
- **Infra**: Cloud Run timeout raised 300s→600s, then concurrency dropped to
  1 with `--no-cpu-throttling` after CPU contention was confirmed as the
  real bottleneck (a local, uncontended run of the same search took 190s;
  the same search in prod was hitting even the raised 600s ceiling).
- **Perf**: the search/rank pipeline was fully serial — 3 sequential Gemini
  grounded-search calls, then up to 40 candidates fetched+ranked one at a
  time with an unjustified flat 1s sleep after each. Parallelized both
  stages with `ThreadPoolExecutor`; removed the sleep (no rate limit was
  ever backing it); fixed `FETCH_TIMEOUT` being dead config. Net effect on a
  real search: ~190-300s+ down to ~74s. This is very likely *why* the
  timeout/concurrency infra fixes above look "unnecessary" in hindsight —
  they were real fixes for a real problem at the time, and are still safe to
  keep, but the perf work may have made the pipeline fast enough that
  they're no longer load-bearing. Nobody has re-tested whether the timeout
  could safely be lowered again post-parallelization.
- **UX polish**: signed-in users now land on their own most-recent search
  instead of an arbitrary default; a freshly created/cloned search (zero
  runs) shows a "hasn't been run yet" state with a working Run button
  instead of a dead end; editing a search's config now shows a breadcrumb
  back to results instead of a bare panel, and saving patches state in place
  instead of forcing a full reload.

## Infrastructure / deploy — know this before touching it

- Push to `main` → Cloud Build (`cloudbuild.yaml`) → Cloud Run service
  `shop-assistant-web`, region `us-east1`. Vertex AI stays `us-central1`.
- Current Cloud Run flags, both justified by real production incidents this
  session (see commits `04ce018`, `af0e40c`) — understand why before
  changing:
  - `--timeout=600` (default is 300; the pipeline was tipping over it)
  - `--concurrency=1 --no-cpu-throttling` (default concurrency=80 let
    ordinary browsing traffic starve an in-flight run of CPU on a shared
    vCPU)
- `make validate-prod` runs `tests/test_smoke.py` and `tests/test_live_qatp.py`
  against the deployed URL — run this after any deploy that touches request
  handling.
- Firestore database is the named `tailoredloop` database (not the project
  default), set via `FIRESTORE_DATABASE=tailoredloop` in `cloudbuild.yaml`.

## Testing

Two live/browser suites exist beyond the standard mocked unit tests:

- `tests/test_live_qatp.py` — HTTP-only smoke tests against a real deployed
  URL (`PROD_URL` env var), used by `make validate-prod`.
- `tests/test_qatp_browser.py` — new this session. Playwright-driven, clicks
  through the real rendered UI (not just HTTP). Gated on `QATP_BROWSER=1` +
  a reachable server (local dev server by default, or a prod-like target via
  `QATP_BASE_URL`). **Read the module docstring before touching this file**
  — it has one hard rule: it never logs in as the project's two real Google
  test accounts, only synthetic `@example.test` identities created directly
  in Firestore and signed in via a session-cookie injected with a real JWT
  (same `session_secret` the running app reads). This is specifically so the
  suite never consumes the real accounts' real free/premium quota. Do not
  "fix" this to use real OAuth login.

### Real test accounts — do not run automated processes against these directly

- `katyanotkin@gmail.com` — free tier, owns public search `bathroom_cabinet`.
- `kate.middlesex@gmail.com` — premium tier (promoted this session), owns
  private search `tshirt_bra` and clones `wax_coat_copy` / `wax_coat_copy_2`.

These are the product owner's own manual-testing accounts. This detail isn't
independently verifiable from the repo (it's live Firestore state, not
code) — treat it as accurate as of this handoff but re-check current
account/search state in Firestore or the admin panel if it matters to what
you're doing.

## Open / unfinished — verify still true before acting on it

- **Free-tier overwrite-in-place clone**: distinct from the premium clone
  that *was* built. Spec'd in PRODUCT.md ("Copying a public search" /
  capability table), not implemented.
- **"Compare up to 3 items"**: a planning note only (PRODUCT.md, "Future:
  compare up to 3 items"). Not designed, not scheduled.
- **Subscription/payment provider**: not chosen. The premium tier numbers
  (2/day, 90-day, 100/month) are explicitly provisional pending this — see
  PRODUCT.md's "Future: subscription model" section for the demotion policy
  and data-model note already agreed for when this gets built.
- **Per-domain fetch throttling**: the parallelized fetch stage (commit
  `862fe42`) has no per-domain rate limiting. A code reviewer flagged this
  as a theoretical risk (concurrent fetches could hit the same shop domain
  at once) with no evidence it's an actual problem at this app's traffic
  level. Deliberately left unimplemented.
- **walkerandhawkes.com retrieval gap**: the owner reported a specific
  product from this domain was missed by a search. Investigated live, no
  code change: the URL would not have been filtered by `is_listing_url`;
  Gemini's grounded search simply never returned that domain as a candidate
  — looks like a gap in Gemini's search grounding, not a bug in this
  codebase. Suggested workaround (not yet applied by the owner): add the
  domain to that search's `preferred_shops`, which triggers a dedicated
  `site:`-scoped query guaranteeing the domain gets checked.

## Where to look for more

- Full pipeline, data model, API surface, infra: [ARCHITECTURE.md](ARCHITECTURE.md)
- User-facing feature and policy detail (roles, quotas, promotion/redaction
  rules, planned features): [PRODUCT.md](PRODUCT.md)
- Setup and dev commands: [CLAUDE.md](CLAUDE.md), [README.md](README.md)
- Chronological detail on any change mentioned above: `git log` — commit
  messages in this repo are written to be read later, they're detailed.
