# Product

## What it does

TailoredLoop solves a specific problem: finding products that match detailed, multi-criteria specifications across dozens of online retailers, without having to visit each shop manually. You describe what you want once — material, gender, length, lining, excluded materials, size, price ceiling, preferred shops — and it searches the web, fetches each candidate page, and scores how well each product matches your criteria on a 0–10 scale. Results appear in a browser UI, grouped by match quality.

It is designed for searches that are hard to express in a single Google query and where you want consistent, comparable scoring across many results over time.

---

## Where it lives

The web interface is at **shopassistant.verbboard.com**.

The results page (`/`) is public — anyone with the URL can read results. Admin features (creating searches for anyone, triggering runs, editing any config, viewing all users) require a password. Signed-in users can create, edit, delete, run, and leave feedback on their own search without a password — see "Planned: multi-user model" below.

---

## The user journey

### Step 1 — Create a search

Go to `/admin` and log in. In the sidebar, click **+ New search**.

You will see a two-field form:

- **Search name** — a short identifier, lowercase with underscores (e.g. `wax_coat`). This becomes the permanent ID for this search.
- **Describe what you want** — free-form text. Write naturally: material, style, length, size, price limit, any shops you prefer. Example: *"women's waxed cotton coat, midi or longer, natural lining or unlined, size M or L, under £500, prefer Barbour and House of Bruar"*.

Click **Generate config**. The AI reads your description and produces a structured configuration populated only with fields mentioned or implied by your text — `category` is always present; every other field (gender, material, lining, etc.) is included only if the description calls for it. The generated config appears in an editable form. Optional fields can be added with the chip buttons in the **Add:** row, or removed with the × button on each field. Review the populated fields — the AI will get most things right but you may want to add, remove, or adjust values.

When you are satisfied, click **Save** to store the config, or **Save & Run** to store it and immediately run the first search.

### Step 2 — What happens during a run

When a search runs, the system:

1. Generates three targeted Google search queries from your criteria.
2. Uses Google Search grounding to find candidate product URLs — preferred shops are searched first.
3. Fetches each product page and strips away navigation, footers, and scripts.
4. Scores each page 0–10 against your criteria and extracts the product title, price, and a list of what matched and what did not.
5. Saves everything to the database and writes a local CSV file.
6. Sends an email notification if any results are new since the last run (requires email configuration).

A run typically takes a few minutes depending on how many candidate URLs are found (up to 40 by default).

### Step 3 — Read results

Open the main page (`/`). The left sidebar lists all active searches. Click one to load its results.

A date picker at the top lets you switch between runs. The most recent run loads by default.

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

### Step 5 — Feedback improves future runs (learn mode)

The next time a search runs, the system looks at feedback you have left across the last 10 runs. If there are at least 3 items with feedback, it calls the AI to distill:

- **Product preferences** — patterns about what you actually want (e.g. "user prefers unlined or cotton lining; dislikes synthetic blends even when unlabeled"). This is injected into the search query planning and scoring prompts for the next run.
- **Shops to avoid** — if you have left feedback on multiple products from the same shop indicating a recurring problem (doesn't ship, poor quality control, repeatedly out of stock), that shop's results will be filtered out automatically.

Learn mode is on by default. You can turn it off per-run with the **Learn from feedback** checkbox next to the run button in the admin edit view.

---

## Admin features

| Feature | Who can use it |
|---------|---------------|
| View results | Anyone (public) |
| Create / edit searches (any user's) | Admin (password required) |
| Run a search manually (any user's) | Admin |
| Leave feedback on results | Admin, or the search's owner |
| Save feedback | Admin, or the search's owner |

### Running a search manually

In the admin panel, select a search from the sidebar. Click **Run** to trigger a search immediately without saving config changes, or **Save & Run** to save first and then run. The button shows an animated indicator while the run is in progress. When done, a summary shows how many matches and partial matches were found, and the view switches to the Results tab automatically.

### Editing a search config

Select a search from the sidebar. The Edit config tab shows the fields currently set on the search. `category` is always visible and cannot be removed. All other fields are optional: present fields show an × button to remove them; hidden fields appear as chip buttons in an **Add:** row at the bottom of the form — click a chip to reveal that field. Each field that takes multiple values (material, sizes, etc.) is a comma-separated list. Preferred shops is a newline-separated list of URLs. Click **Save** to update the config without running.

### Scheduled runs

Searches can be triggered automatically via Cloud Build on a schedule (configured separately from the web UI). The web UI is the primary way to view results and manage configs; scheduled runs write their output to the same Firestore database that the UI reads from.

---

## Planned: multi-user model

The planned evolution moves from a single-admin tool to a service with multiple users, while keeping a curated public layer open to anyone.

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
| Create 1 private search | — | ✓ | ✓ | ✓ |
| Edit or delete own search | — | ✓ | ✓ | ✓ |
| Run own search (within 1 month of creation) | — | ✓ | ✓ | ✓ |
| Create unlimited searches | — | — | ✓ | ✓ |
| Run searches after 1 month | — | — | ✓ | ✓ |
| View own private results & leave feedback | — | ✓ | ✓ | ✓ |
| Promote any search to public | — | — | — | ✓ |
| View all searches (any owner) | — | — | — | ✓ |
| View all users & manage roles | — | — | — | ✓ |
| Edit any search config | — | — | — | ✓ |

### User accounts and private searches

Users sign in with Google. Each user's searches and results are private — only visible to that user and to the admin.

**Free tier** gives users 1 private search. They can create it, configure it, edit or delete it, and run it for up to one month from the date the search was created. After one month, runs are disabled; the search and its results remain readable, and it can still be edited or deleted. Promotion to public does not change or reset the run window — the same 1-month clock applies regardless.

When a free user tries a gated action the UI shows: *"You're on the Free plan. Contact us to get full access."*

**Premium** users can create unlimited searches and run them indefinitely. They get the same workflow as today: describe what you want, generate a config, run it, read results, leave feedback.

### Common results

The admin can promote any search — their own or a user's — to **public**. Promoted searches appear on the public results page as a curated showcase:

- The search config is visible to everyone but not editable by visitors or other users.
- Results appear exactly as they do for the owner.
- Visitors can browse results and click through to product pages but cannot run the search, leave feedback, or modify anything.

### Granting premium access

The admin manages roles from a **Users** tab in the admin panel. Each user appears in a list with their current role as a dropdown (`Free / Premium`). Changing the dropdown takes effect immediately — no re-login required for the user. There is no payment UI, no billing form, and no expiry — determining whether someone qualifies for premium happens outside the product.

### Admin capabilities

Admin is a full superuser:

- Sees all searches from all users, not just their own.
- Can edit, run, or delete any search regardless of owner.
- Promotes and demotes any search between private and public.
- Views the user list and changes any user's role.
- Cannot accidentally remove the last admin account (the action is blocked).

### Future: subscription model (self-serve premium)

Today premium is granted manually by an admin, with no payment flow. As a subscription model, the plan is:

**Promotion (free → premium).** A payment provider webhook flips the role the same way the admin dropdown does today — both paths call the same role-update path, so admin-manual grants (comps, support cases) keep working alongside self-serve checkout. The existing free-tier gate copy ("You're on the Free plan. Contact us to get full access.") becomes the upgrade entry point once checkout exists.

**Demotion (premium → free, e.g. subscription lapses).** Decided policy: a demoted user keeps read access to every search they created while premium — nothing is deleted, hidden, or forcibly consolidated down to the free 1-search limit. Whether a given search can still be *run* is governed by the same 1-month-from-creation window that already applies to every free-role search today — no special-casing for "was this user ever premium." A search created recently (even while still premium) still gets its full month like any free user's search would; older searches simply age out of the window the same way they always do.

**Refinement — early upgraders keep their unused free days.** If a user upgrades to premium *before* their one existing search's 30-day free window has elapsed, that unused time isn't forfeited: on a later demotion, the search's remaining run-eligibility is the leftover balance from the original window (e.g. upgraded on day 5 of 30 → 25 days still owed), counted from the demotion date, not from the original `created_at` as if the premium period had counted against it. This only applies to the one search that falls within the free allowance — it's a fairness fix for the boundary case, not a general "premium time doesn't count" rule. Implementing this needs the backend to know when the user upgraded (and, if it happens more than once, when each premium period started/ended) to compute the unused balance — a small addition beyond the plain per-search `created_at` check described above, deferred alongside the rest of this section until a payment provider is chosen.

**Differentiating premium beyond "unlimited + no expiry" (open, not committed).** Candidates that map to real cost/quality levers in the pipeline rather than generic tier features: more frequent scheduled runs per search, a higher candidate-fetch limit per run, a longer feedback history window for learn mode. None of these are committed — v1 of paid premium may stay exactly "unlimited searches, no run-window expiry," matching today's behavior.

**Data model note for whoever picks this up.** When a payment provider is chosen, prefer adding a `subscription_status` field on the user doc (e.g. `active` / `past_due` / `canceled`) separate from `role`, so a failed-payment retry doesn't have to instantly demote — `role` stays the single coarse permission check the backend already gates on, `subscription_status` becomes the input that decides when to flip it.
