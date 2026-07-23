# Product

## What it does

TailoredLoop solves a specific problem: finding products that match detailed, multi-criteria specifications across dozens of online retailers, without having to visit each shop manually. You describe what you want once — material, gender, length, lining, excluded materials, size, price ceiling, preferred shops — and it searches the web, fetches each candidate page, and scores how well each product matches your criteria on a 0–10 scale. Results appear in a browser UI, grouped by match quality.

It is designed for searches that are hard to express in a single Google query and where you want consistent, comparable scoring across many results over time.

---

## Where it lives

The web interface is at **shopassistant.verbboard.com**.

The results page (`/`) is public for public searches — anyone with the URL can read their results. Private searches 404 for anyone who isn't the owner or an admin, indistinguishable from a search that doesn't exist. Admin features (creating searches for anyone, triggering runs, editing any config, viewing all users) require a password. Signed-in users can create, edit, delete, run, and leave feedback on their own search without a password — see "Accounts and roles" below.

---

## The user journey

### Step 1 — Create a search

Go to `/admin` and log in. In the sidebar, click **+ New search**.

You will see a two-field form:

- **Search name** — a short identifier, lowercase with underscores (e.g. `wax_coat`). This becomes the permanent ID for this search.
- **Describe what you want** — free-form text. Write naturally: material, style, length, size, price limit, any shops you prefer. Example: *"women's waxed cotton coat, midi or longer, natural lining or unlined, size M or L, under £500, prefer Barbour and House of Bruar"*.

Click **Generate config**. The AI reads your description and produces a structured configuration populated only with fields mentioned or implied by your text — `category` is always present; every other field (gender, material, lining, etc.) is included only if the description calls for it. The generated config appears in an editable form. Optional fields can be added with the chip buttons in the **Add:** row, or removed with the × button on each field. Review the populated fields — the AI will get most things right but you may want to add, remove, or adjust values.

Your original description isn't discarded once the config is generated. A collapsed **Original request** disclosure sits right above the criteria fields whenever you come back to edit this search — in the admin panel and in your own search view on the main page alike. Click it to re-read exactly what you typed. It's collapsed by default so it doesn't clutter the form. On a promoted public search, it's visible only to the owner and admin, the same as feedback text, pinned finds, and reference products.

When you are satisfied, click **Save** to store the config, or **Save & Run** to store it and immediately run the first search.

### Reference products (optional)

In the config panel, the **Reference products** card lets you add up to 3 URLs of products you already love — from any shop, not just past results from this search. Adding or removing a URL saves immediately — the card shows a Saving…/Saved status, there is no separate Save step. The AI uses these to calibrate what a great match looks like when scoring candidates.

Each run, the ranker fetches the actual text of every reference page once and feeds an excerpt of it to the scoring model, so calibration is based on real product content, not just the URL. Today this only sharpens *scoring*: it does not change what search queries get generated or which candidate URLs get fetched. Pasting a reference product does not make the search go find "more like this" — it only changes how already-found candidates get judged against it.

Your current reference products are shown in the results view as links ("Products like this (your references): …") above the results list. This reflects the references saved right now, not necessarily what was saved when that run happened — if you add or remove a reference after a run, the results view for that run updates to match.

### Deal-breaker criteria

Every criteria field normally reduces a result's score proportionally when it doesn't match — a partial mismatch on one field doesn't sink an otherwise great result. Some criteria aren't like that: "flex on price, but not on cabinet dimensions."

In the config panel, each optional field (Material, Lining, Length, Sizes, Max price, and any custom field you've added) has a **Deal-breaker** checkbox next to it. Ticking it makes that field non-negotiable: a result that fails to satisfy it is capped at a score of 3, the same way an excluded material already caps a result today — low enough that it falls below the Partial match threshold and doesn't appear in results at all, rather than surfacing as a lower-scored match. Category and Gender aren't offered the checkbox because they're already non-negotiable everywhere (a category or gender mismatch already zeroes the score); Exclude isn't offered it either since an excluded value already caps the score the same way a deal-breaker would.

### Step 2 — What happens during a run

When a search runs, the system:

1. Generates three targeted Google search queries from your criteria.
2. Uses Google Search grounding to find candidate product URLs — preferred shops are searched first.
3. Drops candidate URLs that are recognizably category, collection, or search-results pages, and dedupes URLs that resolve to the same page, before fetching them.
4. Fetches each remaining product page and strips away navigation, footers, and scripts.
5. Scores each page 0–10 against your criteria and extracts the product title, price, and a list of what matched and what did not. A page that turns out to be a multi-product listing rather than a single product is scored 0.
6. Saves everything to the database and writes a local CSV file.
7. Sends an email notification if any results are new since the last run (requires email configuration).

A run typically takes about a minute, depending on how many candidate URLs are found (up to 40 by default) — search, fetch, and scoring all happen concurrently rather than one step at a time.

Grounded search has some query-to-query variance — a genuinely good match found recently can simply fail to be resurfaced by a fresh run's newly-generated queries, even though it's still available. To make results more reliable, every run also automatically pulls in the Matches and Partial matches from the search's last 2 runs, dedupes them against this run's freshly-discovered candidates, and re-fetches and re-scores them completely fresh against the *current* criteria — not whatever criteria was in effect when they first appeared. These carried-forward candidates share the same ~40-candidate-per-run budget as new discovery and get priority within it. Anything that no longer qualifies under fresh scoring just drops silently and isn't retried. There's no visual difference between a carried-forward result and one found fresh this run — if it still qualifies, it appears as a normal Match or Partial match either way. This is separate from pinned finds (below), which are a manual, user-curated, permanently-frozen pick — carried-forward results are automatic, unlimited beyond the last-2-runs window, and always re-verified fresh rather than frozen.

### Step 3 — Read results

Open the main page (`/`). The left sidebar lists all active searches. Click one to load its results.

A date picker at the top lets you switch between runs. The most recent run loads by default.

If you own the search, a config panel sits side-by-side with the results (collapsible, same toggle as the admin panel) and follows the same date picker. Selecting the **latest** run shows your **live, editable** config — the same form described in "Editing a search config" below. Selecting an **older** run shows that run's config exactly as it was when it executed: fields are disabled and there's no Save button, with a banner reading "Read-only — showing config as of [date]" and a one-click button back to the latest run. A search that hasn't been run yet always shows the live editable config, since there's no past run to freeze. This is how editing works now for a search's own owner — there's no separate edit screen. Viewers of a public search they don't own instead see a compact, read-only criteria summary bar above the results, not the full panel.

Results are divided into two sections:

- **Matches** — scored 7 or above. These satisfy the core criteria.
- **Partial matches** — scored 4–6. Something meaningful matched but one or more criteria are not met or unclear.

Each result card shows:
- The score (0–10), color-coded green/amber/red.
- A **NEW** badge if this URL did not appear in the previous run.
- The product title and shop name.
- The price if extracted.
- Green tags for matched criteria, red tags for unmatched ones.
- A one-sentence explanation from the AI.
- A link to the product page.

### Step 4 — Give feedback

If you are logged in as admin, or you own the search you are viewing, each result card has a feedback area below it. You can:

- Type free-form text about why the product did or did not work for you.
- Click any of the quick-phrase buttons (e.g. "Wrong material", "Doesn't ship to me", "Too expensive") to append that phrase to the feedback field. Multiple phrases can be combined.

There is a character counter that shows how much of the 256-character limit you have used.

When you are done, click **Save all feedback** at the top of the results panel. This saves all non-empty feedback fields in one batch write.

Feedback is stored per product URL per run date. If you load an older run, any feedback you previously left for that run will appear pre-filled in the text areas.

### Pinned finds

Leaving the exact "Perfect match" quick-phrase on a result pins it — up to 3 per search, oldest dropped first if you pin a 4th. A pinned find reappears in a **Your picks** section above Matches on every future run, even if that run's search queries don't rediscover the URL (out of stock, delisted, or just not surfaced this time) — so a product you've already confirmed you love never silently disappears. Pinned finds also feed the ranker as calibration benchmarks, the same way reference products do — they become style/quality examples for scoring future candidates, not just a static list.

Unpin from the **Your picks** card at any time. Pinned cards don't show the feedback box — a pin can come from a different, older run than the one you're currently viewing, so leaving new feedback there could get misattributed to today's run.

### Step 5 — Feedback improves future runs (learn mode)

The next time a search runs, the system looks at feedback you have left across the last 10 runs. If there is at least 1 item with feedback, it calls the AI to distill:

- **Product preferences** — patterns about what you actually want (e.g. "user prefers unlined or cotton lining; dislikes synthetic blends even when unlabeled"). This is injected into the search query planning and scoring prompts for the next run.
- **Shops to avoid** — if you have left feedback on multiple products from the same shop indicating a recurring problem (doesn't ship, poor quality control, repeatedly out of stock), that shop's results will be filtered out automatically.

**Teach this search** — the free-text box for feedback on the run as a whole, not tied to one product — is included too, and treated as an explicit, high-signal statement about what future runs should look for or avoid, rather than being silently ignored.

Learn mode is on by default. You can turn it off per-run with the **Learn from feedback** checkbox next to the run button in the admin edit view.

---

## Admin features

| Feature | Who can use it |
|---------|---------------|
| View results | Anyone, for public searches; owner or admin only for private searches |
| Create / edit searches (any user's) | Admin (password required) |
| Run a search manually (any user's) | Admin |
| Leave feedback on results | Admin, or the search's owner |
| Save feedback | Admin, or the search's owner |

### Running a search manually

In the admin panel, select a search from the sidebar. Click **Run** to trigger a search immediately without saving config changes, or **Save & Run** to save first and then run. The button shows an animated indicator while the run is in progress. When done, a summary shows how many matches and partial matches were found, and the results panel updates automatically alongside the config panel.

### Editing a search config

Select a search from the sidebar. The config panel sits side-by-side with results (collapsible) and shows the fields currently set on the search. `category` is always visible and cannot be removed. All other fields are optional: present fields show an × button to remove them; hidden fields appear as chip buttons in an **Add:** row at the bottom of the form — click a chip to reveal that field. Each field that takes multiple values (material, sizes, etc.) is a comma-separated list. Preferred shops is a newline-separated list of URLs. Click **Save** to update the config without running.

The config panel is run-scoped, following the same date picker used to browse results. Selecting the **latest** run shows this live, editable form. Selecting an **older** run instead shows that run's config frozen exactly as it was when it executed: fields are disabled, and the Save, visibility, and delete controls are hidden. A banner reads "Read-only — showing config as of [date]" with a one-click button back to the latest run. A search that has never been run always shows the live editable form.

### Scheduled runs

Searches can be triggered automatically via Cloud Build on a schedule (configured separately from the web UI). The web UI is the primary way to view results and manage configs; scheduled runs write their output to the same Firestore database that the UI reads from.

---

## Accounts and roles

TailoredLoop is a multi-user service with a curated public layer open to anyone. Signed-in users get their own private search(es); the admin can promote any search to a public showcase. (A few pieces of this model — free-tier cloning into an existing slot, self-serve subscriptions — are still planned and marked as such below.)

### Roles

Every account has one of three roles:

| Role | How you get it |
|---|---|
| **Free** | Default on first sign-in via Google |
| **Premium** | Admin grants it manually (whether you paid or were comped is decided outside the product) |
| **Admin** | Bootstrapped; additional admins promoted manually |

### What each role can do

| Capability | Visitor (no account) | Free | Premium | Admin |
|---|---|---|---|---|
| Browse public results | ✓ | ✓ | ✓ | ✓ |
| Sign in | — | ✓ | ✓ | ✓ |
| Create a private search | — | 1 total | 2 new or cloned per day | unlimited |
| Clone a public search into a private copy | — | — (planned) | ✓ | ✓ |
| Edit own search | — | ✓ | ✓ | ✓ |
| Delete any search | — | — | — | ✓ |
| Run own search | — | within 30 days of creation | within 90 days of creation | no window limit |
| Runs per calendar month | — | 20 | 100 | unlimited |
| View own private results & leave feedback | — | ✓ | ✓ | ✓ |
| Promote any search to public | — | — | — | ✓ |
| View all searches (any owner) | — | — | — | ✓ |
| View all users & manage roles | — | — | — | ✓ |
| Edit any search config | — | — | — | ✓ |

Deleting is admin-only across the board — Free and Premium users can edit their search but cannot delete it themselves. There is no self-serve way to remove a single search; the only user-initiated removal is deleting the whole account (see below), which reassigns ownership to admin rather than deleting the data.

### User accounts and private searches

Users sign in with Google. Each user's searches and results are private — only visible to that user and to the admin. This is enforced at the API level: a private search's config, run list, and run data all 404 for anyone else, indistinguishable from a search that doesn't exist.

**Free tier** gives users 1 private search. They can create it, configure it, edit it, and run it for up to one month from the date the search was created. After one month, runs are disabled; the search and its results remain readable, and it can still be edited. Promotion to public does not change or reset the run window — the same 1-month clock applies regardless. Runs are also capped at 20 per UTC calendar month; hitting the cap shows: *"You've used all 20 runs for this month. Runs reset on the 1st."*

No user can delete their own search — see "Admin capabilities" below. A free user who wants a different search than the one they have can still edit its criteria freely, or replace it via cloning a public search into their slot (see "Copying a public search" below) — but only *before* their current search has ever been run. Once it's been run at least once, that slot is locked to edit-in-place only; they can no longer swap it for a different search. This closes off run-then-swap as a way to get repeated fresh 30-day windows out of one free account: editing an existing search keeps its original `created_at` and run window unchanged, and once used, the slot can't be traded in for a different search at all.

When a free user tries a gated action the UI shows: *"You're on the Free plan. Contact us to get full access."*

**Premium** users can create up to 2 new searches per UTC calendar day — from scratch, or by cloning a public search (see "Copying a public search" below); either kind counts the same toward the daily cap. Each search can be run for up to 90 days from the date it was created (mirroring free's 30-day window, just longer), and premium is capped at 100 runs per UTC calendar month. Otherwise they get the same workflow as today: describe what you want, generate a config, run it, read results, leave feedback.

When a premium user hits the daily creation cap: *"You've reached today's limit of 2 new searches. Try again tomorrow."* When a search's run window has expired: *"This search's 90-day run window has expired. Create a new search to keep monitoring, or contact us if you need it extended."*

### Common results

The admin can promote any search — their own or a user's — to **public**. Promoted searches appear on the public results page as a curated showcase:

- The search config is visible to everyone but not editable by visitors or other users.
- Visitors can browse results and click through to product pages but cannot run the search, leave feedback, or modify anything.

**Results of a promoted user-owned search.** Run results remain visible to everyone — scores, match/partial tags, AI explanations, candidate counts, and the config (criteria, preferred shops) are all part of the showcase. But layers of personal signal stay **owner-only** regardless of promotion, the same categories the Copy feature already excludes: per-result **feedback text**, **pinned finds** ("Your picks"), **reference products** ("Products like this"), and the **original request** text behind the config. Learned preference notes distilled by Learn mode (`feedback_notes`, avoided shops) are likewise owner-only, including the copies frozen inside each run's config snapshot. Non-owner viewers simply see the run without these sections. Promotion changes nothing about the owner's experience — their run window, monthly quota, and full view of their own pins/references/feedback are unaffected, and promotion requires no consent beyond the Terms of Service already in effect.

### Copying a public search

Premium and admin users can clone a public search into a private copy of their own — either to run it as-is or to polish the criteria first. A **Copy** button appears next to public searches the user doesn't own, in the sidebar. The clone copies the criteria config (including any deal-breaker flags) and preferred shops; it does not copy the original owner's feedback, pinned finds, or reference products, since those are personal signal about what worked for *that* user's taste, not the objective spec. The clone is a brand-new private search owned by the cloner, with its own fresh `created_at` — so it gets a full new 90-day run window — and it counts toward the premium 2-per-day creation cap the same as a from-scratch search. Its default title is "*source title* (copy)"; the cloner can rename it.

**Free-tier cloning into an existing slot is still planned, not shipped.** The idea, unchanged from the original design: since Free users can't delete their own search (see "Admin capabilities" below), cloning would fill their existing 1-private-search slot rather than add a bonus one, by overwriting that search in place — the same way editing does, not by deleting and recreating — and only while the existing search has never been run. This is not implemented yet.

### Granting premium access

The admin manages roles from a **Users** tab in the admin panel. Each user appears in a list with their current role as a dropdown (`Free / Premium`). Changing the dropdown takes effect immediately — no re-login required for the user. There is no payment UI, no billing form, and no expiry — determining whether someone qualifies for premium happens outside the product.

### Admin capabilities

Admin is a full superuser:

- Sees all searches from all users, not just their own.
- Can edit, run, or delete any search regardless of owner. Deleting is admin-only — no other role can delete a search, their own or anyone else's.
- Promotes and demotes any search between private and public.
- Views the user list and changes any user's role.

### Account deletion

Any signed-in user can delete their own account (self-serve, from the top bar). This removes their identity data (email, display name, profile picture) immediately. It does not delete their searches or results — those aren't personal data (see the Privacy Policy) and are retained by reassigning `owner_id` to admin, the same way as any other admin-owned search. This applies uniformly regardless of role: Free, Premium, and Admin accounts are all handled the same way on deletion, so there's no special-casing based on tier.

### Future: subscription model (self-serve premium)

Today premium is granted manually by an admin, with no payment flow. As a subscription model, the plan is:

**Promotion (free → premium).** A payment provider webhook flips the role the same way the admin dropdown does today — both paths call the same role-update path, so admin-manual grants (comps, support cases) keep working alongside self-serve checkout. The existing free-tier gate copy ("You're on the Free plan. Contact us to get full access.") becomes the upgrade entry point once checkout exists.

**Demotion (premium → free, e.g. subscription lapses).** Decided policy: a demoted user keeps read access to every search they created while premium — nothing is deleted, hidden, or forcibly consolidated down to the free 1-search limit. Whether a given search can still be *run* is governed by the same 1-month-from-creation window that already applies to every free-role search today — no special-casing for "was this user ever premium." A search created recently (even while still premium) still gets its full month like any free user's search would; older searches simply age out of the window the same way they always do.

**Refinement — early upgraders keep their unused free days.** If a user upgrades to premium *before* their one existing search's 30-day free window has elapsed, that unused time isn't forfeited: on a later demotion, the search's remaining run-eligibility is the leftover balance from the original window (e.g. upgraded on day 5 of 30 → 25 days still owed), counted from the demotion date, not from the original `created_at` as if the premium period had counted against it. This only applies to the one search that falls within the free allowance — it's a fairness fix for the boundary case, not a general "premium time doesn't count" rule. Implementing this needs the backend to know when the user upgraded (and, if it happens more than once, when each premium period started/ended) to compute the unused balance — a small addition beyond the plain per-search `created_at` check described above, deferred alongside the rest of this section until a payment provider is chosen.

**Differentiating premium beyond free (levers set for now, not committed).** The owner has set concrete numbers for now, ahead of any payment flow: premium gets 2 new-or-cloned searches/day, a 90-day run window per search, and 100 runs/month; free gets 1 search, a 30-day run window, and 20 runs/month. These are a placeholder differentiation, not a final pricing decision, and are subject to revision once a payment provider is chosen. Other candidates that map to real cost/quality levers in the pipeline remain open and uncommitted: more frequent scheduled runs per search, a higher candidate-fetch limit per run, a longer feedback history window for learn mode.

**Data model note for whoever picks this up.** When a payment provider is chosen, prefer adding a `subscription_status` field on the user doc (e.g. `active` / `past_due` / `canceled`) separate from `role`, so a failed-payment retry doesn't have to instantly demote — `role` stays the single coarse permission check the backend already gates on, `subscription_status` becomes the input that decides when to flip it.

---

## Future: compare up to 3 items

Not scheduled, not designed in detail. The idea: pick up to 3 items (their titles, prices, and scored attributes) and have the AI determine the relevant comparison criteria itself, rather than the user pre-specifying what to compare on.

This pairs naturally with pinned finds (above) — a user's own saved favorites are the most likely source of items they'd want compared — but it isn't blocked by pinned finds or deal-breaker criteria; it only needs 3 chosen product records as input.
