(() => {
  const searchList   = document.getElementById("admin-search-list");
  const configPanel   = document.getElementById("config-panel");
  const configContent = document.getElementById("config-content");
  const resultsPanel  = document.getElementById("results-panel");
  const adminPanels   = document.querySelector(".admin-panels");
  const dateToolbar   = document.getElementById("admin-date-toolbar");
  const dateSelectEl  = document.getElementById("admin-date-select");

  let latestRunDate = null;
  let currentRunDate = null;

  // Monotonic navigation token — see the identical comment in app.js. Bumped
  // once per user-initiated navigation (selecting a different search or
  // switching run date) so a slow-resolving earlier navigation can never
  // clobber a faster-resolving later one.
  let _navSeq = 0;
  function _beginNav() { return ++_navSeq; }
  function _isCurrentNav(seq) { return seq === _navSeq; }

  // ── API ──────────────────────────────────────────────────────────────────

  async function api(method, path, body) {
    const opts = { method, credentials: "same-origin", headers: {} };
    if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    const r = await fetch(path, opts);
    if (r.status === 401) { const e = new Error("Unauthorized"); e.status = 401; throw e; }
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }

  // ── Helpers shared with app.js ────────────────────────────────────────────

  function siteName(url) {
    try {
      const locales = new Set(["us","uk","eu","au","ca"]);
      const skip = new Set(["www","shop","store","m","en","co"]);
      const parts = new URL(url).hostname.split(".");
      const labels = [];
      for (let i = 0; i < parts.length - 1; i++) {
        const p = parts[i].toLowerCase();
        if (skip.has(p)) continue;
        labels.push(locales.has(p) ? p.toUpperCase() : p.charAt(0).toUpperCase() + p.slice(1));
      }
      return labels.join(" ") || parts[0];
    } catch { return ""; }
  }

  function scoreClass(s) { return s >= 7 ? "green" : s >= 4 ? "amber" : "red"; }
  function tag(text, cls) { return `<span class="tag ${cls}">${esc(text)}</span>`; }
  function esc(s) {
    return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function safeHref(url) {
    try { const u = new URL(url); return (u.protocol === "https:" || u.protocol === "http:") ? url : "#"; }
    catch { return "#"; }
  }

  function renderResultCard(m, feedbackMap, opts = {}) {
    const sc = scoreClass(m.score);
    const site = siteName(m.url);
    const titleInner = site && m.title
      ? `<span class="card-site">${esc(site)}</span><span class="card-sep"> | </span>${esc(m.title)}`
      : esc(m.title || "(no title)");
    const titleText = `<a class="card-title-link" href="${esc(safeHref(m.url))}" target="_blank" rel="noopener">${titleInner}</a>`;
    const price = m.price != null ? `<span class="card-price">${esc(String(m.price))}</span>` : "";
    const newTag = m.is_new ? tag("NEW", "tag-new") : "";
    const unpinBtn = opts.pinned
      ? `<button type="button" class="btn-unpin" data-url="${esc(m.url)}" aria-label="Unpin">Unpin</button>`
      : "";
    const criteria = [
      ...(m.matched || []).map(t => tag(t, "tag tag-match")),
      ...(m.unmatched || []).map(t => tag(t, "tag tag-miss")),
    ].join("");
    const notes = m.notes ? `<p class="card-notes">${esc(m.notes)}</p>` : "";
    const feedback = opts.pinned ? "" : Feedback.renderFeedbackBlock(m.url, feedbackMap, m.title);
    return `<div class="card">
      <div class="score-badge ${sc}">${Math.round(m.score)}</div>
      <div class="card-body">
        <div class="card-title-row">${titleText}${newTag}${unpinBtn}</div>
        <div class="card-meta">${price}</div>
        ${criteria ? `<div class="criteria-row">${criteria}</div>` : ""}
        ${notes}
        ${feedback}
      </div>
    </div>`;
  }

  // ── Edit view (field manifest, rendering, collection: shared with app.js) ─

  const ADMIN_EDIT_ACTIONS = `<div class="action-row">
      <button class="btn-run btn-run-only">Run</button>
      <button class="btn-primary btn-save">Save</button>
      <button class="btn-run btn-save-run">Save &amp; Run</button>
      <label class="learn-label">
        <input type="checkbox" name="learn_feedback" checked> Learn from feedback
      </label>
      <span class="save-msg"></span>
    </div>`;

  function renderEdit(cfg) {
    return CriteriaForm.renderEdit(cfg, ADMIN_EDIT_ACTIONS);
  }

  function bindEdit(form, opts = {}) {
    CriteriaForm.bindFieldControls(form);

    const msg        = form.querySelector(".save-msg");
    const setMsg     = (text, cls) => { msg.textContent = text; msg.className = `save-msg ${cls}`; };
    const btnSave    = form.querySelector(".btn-save");
    const btnRunOnly = form.querySelector(".btn-run-only");
    const btnSaveRun = form.querySelector(".btn-save-run");
    const learnChk   = form.querySelector("[name='learn_feedback']");
    const allBtns    = [btnSave, btnRunOnly, btnSaveRun];

    btnSave.addEventListener("click", async () => {
      const cfg = CriteriaForm.collectConfig(form);
      try {
        await api("PUT", `/api/admin/search/${cfg.search_name}`, cfg);
        setMsg("Saved.", "ok");
        setTimeout(() => setMsg("", ""), 2500);
        if (opts.onSave) opts.onSave(cfg.search_name);
      } catch (e) { setMsg(e.message, "err"); }
    });

    async function runSearch(btn, saveFirst) {
      const cfg = CriteriaForm.collectConfig(form);
      const originalText = btn.textContent;
      allBtns.forEach(b => b.disabled = true);
      let n = 0;
      const timer = setInterval(() => { btn.textContent = "...".slice(0, (n++ % 3) + 1); }, 400);
      try {
        if (saveFirst) await api("PUT", `/api/admin/search/${cfg.search_name}`, cfg);
        const result = await api("POST", `/api/admin/run/${cfg.search_name}`, { learn: learnChk.checked });
        clearInterval(timer);
        btn.textContent = originalText;
        allBtns.forEach(b => b.disabled = false);
        setMsg(`Done — ${result.matches} matches, ${result.partial} partial.`, "ok");
        if (opts.onSave) await opts.onSave(cfg.search_name);
        await afterRun(cfg.search_name);
      } catch (e) {
        clearInterval(timer);
        btn.textContent = originalText;
        allBtns.forEach(b => b.disabled = false);
        setMsg(e.message, "err");
      }
    }

    btnRunOnly.addEventListener("click", () => runSearch(btnRunOnly, false));
    btnSaveRun.addEventListener("click", () => runSearch(btnSaveRun, true));
  }

  // ── Reference products card ──────────────────────────────────────────────

  function renderReferences() {
    // No manual Save button: references persist automatically on add/remove.
    return References.renderReferences({ withSaveButton: false });
  }

  function bindReferences(card, editForm, name) {
    const hidden = editForm.querySelector('[name="example_urls"]');
    References.bindReferences(card, hidden, {
      siteName,
      onChange: async urls => {
        // The admin PUT merges into the stored config, so sending just the
        // references never clobbers unsaved edits elsewhere in the form.
        await api("PUT", `/api/admin/search/${name}`, { example_urls: urls });
      },
    });
  }

  // ── Results panel ─────────────────────────────────────────────────────────

  function bindUnpin(container, name, runDate, seq) {
    container.querySelectorAll(".btn-unpin").forEach(btn => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          await api("POST", `/api/feedback/${encodeURIComponent(name)}/pinned/remove`, { url: btn.dataset.url });
          loadResults(name, runDate, seq);
        } catch (e) {
          btn.disabled = false;
          btn.textContent = e.message;
        }
      });
    });
  }

  function renderRun(run, name, runDate, seq) {
    const freshUrls = new Set([...(run.matches || []), ...(run.partial_matches || [])].map(m => m.url));
    const pinned = (run.pinned_finds || []).filter(m => !freshUrls.has(m.url));
    if (run.no_match || (!run.matches?.length && !run.partial_matches?.length && !pinned.length)) {
      resultsPanel.innerHTML = `<p class="empty-state">No matches in this run.</p>` + References.renderNote(run, { siteName });
      return;
    }
    const feedbackMap = run.feedback || {};
    let html = `<p class="run-meta">${esc(runDate)} · ${run.total_candidates ?? "?"} candidates</p>`;
    html += References.renderNote(run, { siteName });
    html += Feedback.renderSaveAllRow(feedbackMap);
    if (pinned.length)
      html += `<div class="results-section"><p class="section-heading">Your picks (${pinned.length})</p>
        <div class="cards">${pinned.map(m => renderResultCard(m, feedbackMap, { pinned: true })).join("")}</div></div>`;
    if (run.matches?.length)
      html += `<div class="results-section"><p class="section-heading">Matches (${run.matches.length})</p>
        <div class="cards">${run.matches.map(m => renderResultCard(m, feedbackMap)).join("")}</div></div>`;
    if (run.partial_matches?.length)
      html += `<div class="results-section"><p class="section-heading">Partial (${run.partial_matches.length})</p>
        <div class="cards">${run.partial_matches.map(m => renderResultCard(m, feedbackMap)).join("")}</div></div>`;
    resultsPanel.innerHTML = html;
    Feedback.bindFeedback(resultsPanel, async items => {
      await api("PUT", `/api/feedback/${encodeURIComponent(name)}/${encodeURIComponent(runDate)}/batch`, { items });
      // A "Perfect match" item in this batch may have just created a pin —
      // reload so a new "Your picks" section (or an updated one) shows up
      // without the user having to navigate away and back.
      loadResults(name, runDate, seq);
    });
    bindUnpin(resultsPanel, name, runDate, seq);
  }

  // `seq` defaults to the current nav token for same-context refreshes
  // (feedback save, unpin) that aren't a fresh navigation in their own right.
  async function loadResults(name, runDate, seq = _navSeq) {
    resultsPanel.innerHTML = `<p class="loading">Loading…</p>`;
    try {
      const run = await api("GET", `/api/results/${encodeURIComponent(name)}/${encodeURIComponent(runDate)}`);
      if (!_isCurrentNav(seq)) return null;
      renderRun(run, name, runDate, seq);
      return run;
    } catch {
      if (!_isCurrentNav(seq)) return null;
      resultsPanel.innerHTML = `<p class="empty-state">No results yet.</p>`;
      return null;
    }
  }

  // ── Run-scoped config panel: live/editable on the latest run, a read-only
  // frozen snapshot on any earlier one ────────────────────────────────────────

  function isLatest(date) {
    return CriteriaForm.isLatestRun(date, latestRunDate ? [latestRunDate] : []);
  }

  async function renderLiveConfig(name, seq = _navSeq) {
    configContent.innerHTML = `<p class="loading">Loading…</p>`;
    try {
      const cfg = await api("GET", `/api/admin/search/${encodeURIComponent(name)}`);
      if (!_isCurrentNav(seq)) return;
      configContent.innerHTML = renderConfigHeader(cfg) + renderEdit(cfg) + renderReferences();
      bindVisibilityToggle(configContent.querySelector(".config-header-row"));
      bindDeleteButton(configContent.querySelector(".config-header-row"));
      const form = configPanel.querySelector(".edit-form");
      bindEdit(form);
      bindReferences(configPanel.querySelector(".references-card"), form, name);
    } catch (e) {
      if (!_isCurrentNav(seq)) return;
      configContent.innerHTML = `<p class="empty-state">${esc(e.message)}</p>`;
    }
  }

  function renderReadOnlyConfig(snap, date, name) {
    configContent.innerHTML = CriteriaForm.renderReadOnlyBanner(date) + renderConfigHeader(snap, { readOnly: true })
      + CriteriaForm.renderEdit(snap, "", { readOnly: true });
    CriteriaForm.bindReadOnlyBanner(() => {
      dateSelectEl.value = latestRunDate;
      selectRunDate(name, latestRunDate);
    });
  }

  function populateDateSelect(dates) {
    dateSelectEl.innerHTML = dates.map(d => `<option value="${esc(d)}">${esc(d)}</option>`).join("");
    dateToolbar.hidden = dates.length === 0;
  }

  async function selectRunDate(name, date) {
    const seq = _beginNav();
    currentRunDate = date;
    const run = await loadResults(name, date, seq);
    if (!_isCurrentNav(seq)) return;
    if (isLatest(date)) {
      await renderLiveConfig(name, seq);
    } else if (run) {
      renderReadOnlyConfig(run.config_snapshot || {}, date, name);
    }
  }

  dateSelectEl.addEventListener("change", () => {
    if (activeName) selectRunDate(activeName, dateSelectEl.value);
  });

  // ── Generate from description ─────────────────────────────────────────────

  function renderGenerate() {
    return `<div class="generate-panel">
      <h3 class="generate-title">New search</h3>
      <div class="field-row">
        <label class="field-label">Search name</label>
        <input type="text" id="gen-name" class="field-input" placeholder="e.g. wool_coat (lowercase, underscores)">
      </div>
      <div class="field-row">
        <label class="field-label">Describe what you want</label>
        <textarea id="gen-desc" class="field-input" rows="6" placeholder="Describe what you want — include any relevant details: category, gender, material, size, max price, preferred shops, things to exclude…"></textarea>
      </div>
      <div class="action-row">
        <button id="gen-btn" class="btn-primary">Generate config</button>
        <span id="gen-msg" class="save-msg"></span>
      </div>
    </div>`;
  }

  function bindGenerate() {
    const btn = document.getElementById("gen-btn");
    const msg = document.getElementById("gen-msg");
    const setMsg = (text, cls) => { msg.textContent = text; msg.className = `save-msg ${cls}`; };

    btn.addEventListener("click", async () => {
      const name = document.getElementById("gen-name").value.trim().toLowerCase().replace(/\s+/g, "_");
      const desc = document.getElementById("gen-desc").value.trim();
      if (!name) { setMsg("Search name required.", "err"); return; }
      if (desc.length < 10) { setMsg("Description too short.", "err"); return; }

      btn.disabled = true;
      setMsg("Generating…", "");
      try {
        const cfg = await api("POST", "/api/admin/search/generate", { search_name: name, description: desc });
        configContent.innerHTML= `<p class="save-msg ok" style="margin-bottom:12px">Generated — review, then Save or Save &amp; Run.</p>` + renderEdit(cfg) + renderReferences();
        const form = configPanel.querySelector(".edit-form");
        bindEdit(form, { onSave: n => refreshSidebar(n) });
        bindReferences(configPanel.querySelector(".references-card"), form, name);
      } catch (e) {
        setMsg(e.message, "err");
        btn.disabled = false;
      }
    });
  }

  // ── Config header (search name + visibility toggle) ──────────────────────

  function renderConfigHeader(cfg, opts = {}) {
    const vis = cfg.visibility || "public";
    const name = cfg.search_name || "";
    const title = `<span class="config-search-name">${esc(cfg.title || name.replace(/_/g, " "))}</span>`;
    if (opts.readOnly) {
      // Visibility toggle and delete act on the LIVE search, not this frozen
      // snapshot — showing them while browsing history would mutate the
      // wrong thing, so they're omitted entirely rather than disabled.
      return `<div class="config-header-row">${title}</div>`;
    }
    return `<div class="config-header-row">
      ${title}
      <button type="button" class="btn-visibility btn-run" data-name="${esc(name)}" data-visibility="${esc(vis)}">
        ${vis === "public" ? "Make private" : "Make public"}
      </button>
      <button type="button" class="btn-run edit-delete-btn" data-name="${esc(name)}">Delete</button>
      <span class="visibility-msg save-msg"></span>
    </div>`;
  }

  function bindVisibilityToggle(headerRow) {
    const btn   = headerRow?.querySelector(".btn-visibility");
    const msgEl = headerRow?.querySelector(".visibility-msg");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const name    = btn.dataset.name;
      const current = btn.dataset.visibility;
      const next    = current === "public" ? "private" : "public";
      btn.disabled  = true;
      try {
        await api("PATCH", `/api/admin/search/${encodeURIComponent(name)}/visibility`, { visibility: next });
        btn.dataset.visibility = next;
        btn.textContent        = next === "public" ? "Make private" : "Make public";
        if (msgEl) { msgEl.textContent = "Saved"; msgEl.className = "visibility-msg save-msg ok"; setTimeout(() => { msgEl.textContent = ""; }, 2500); }
      } catch (e) {
        if (msgEl) { msgEl.textContent = e.message; msgEl.className = "visibility-msg save-msg err"; }
      }
      btn.disabled = false;
    });
  }

  function bindDeleteButton(headerRow) {
    const btn   = headerRow?.querySelector(".edit-delete-btn");
    const msgEl = headerRow?.querySelector(".visibility-msg");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const name = btn.dataset.name;
      if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
      btn.disabled = true;
      try {
        await api("DELETE", `/api/admin/search/${encodeURIComponent(name)}`);
        _beginNav(); // invalidate any in-flight load for the just-deleted search
        activeName = null;
        latestRunDate = null;
        currentRunDate = null;
        dateToolbar.hidden = true;
        configContent.innerHTML = `<p class="empty-state">Select a search from the left.</p>`;
        resultsPanel.innerHTML = "";
        await refreshSidebar();
      } catch (e) {
        btn.disabled = false;
        if (msgEl) { msgEl.textContent = e.message; msgEl.className = "visibility-msg save-msg err"; }
      }
    });
  }

  // ── Users tab ─────────────────────────────────────────────────────────────

  function renderUsersTable(users) {
    if (!users.length) return `<p class="empty-state">No users yet.</p>`;
    return `<table class="users-table">
      <thead><tr><th>Name</th><th>Email</th><th>Role</th></tr></thead>
      <tbody>${users.map(u => `<tr>
        <td>${esc(u.display_name || "")}</td>
        <td>${esc(u.email || "")}</td>
        <td>
          <select class="role-select" data-uid="${esc(u.uid)}">
            ${["free", "premium", "admin"].map(r => `<option value="${r}" ${u.role === r ? "selected" : ""}>${r}</option>`).join("")}
          </select>
          <span class="role-saved-msg save-msg"></span>
        </td>
      </tr>`).join("")}</tbody>
    </table>`;
  }

  async function loadUsers() {
    _beginNav(); // invalidate any in-flight search load
    activeName = null;
    latestRunDate = null;
    currentRunDate = null;
    dateToolbar.hidden = true;
    searchList.querySelectorAll("li").forEach(el => el.classList.remove("active"));
    configContent.innerHTML   = `<p class="loading">Loading users…</p>`;
    resultsPanel.innerHTML    = `<p class="empty-state">Select a search to view results.</p>`;
    try {
      const users = await api("GET", "/api/admin/users");
      configContent.innerHTML = renderUsersTable(users);
      configContent.querySelectorAll(".role-select").forEach(select => {
        select.addEventListener("change", async () => {
          const uid   = select.dataset.uid;
          const role  = select.value;
          const msgEl = select.parentElement.querySelector(".role-saved-msg");
          select.disabled = true;
          if (msgEl) { msgEl.textContent = "Saving…"; msgEl.className = "role-saved-msg save-msg"; }
          try {
            await api("PATCH", `/api/admin/user/${encodeURIComponent(uid)}/role`, { role });
            if (msgEl) { msgEl.textContent = "Saved"; msgEl.className = "role-saved-msg save-msg ok"; setTimeout(() => { msgEl.textContent = ""; }, 2500); }
          } catch (e) {
            if (msgEl) { msgEl.textContent = e.message; msgEl.className = "role-saved-msg save-msg err"; }
          }
          select.disabled = false;
        });
      });
    } catch (e) {
      configContent.innerHTML = `<p class="empty-state">Failed to load users: ${esc(e.message)}</p>`;
    }
  }

  // ── Site feedback tab ─────────────────────────────────────────────────────

  function renderSiteFeedbackTable(entries) {
    if (!entries.length) return `<p class="empty-state">No site feedback yet.</p>`;
    return `<table class="users-table">
      <thead><tr><th>When</th><th>From</th><th>Feedback</th></tr></thead>
      <tbody>${entries.map(f => `<tr>
        <td>${esc((f.created_at || "").slice(0, 16).replace("T", " "))}</td>
        <td>${esc(f.owner_name || "Anonymous")}</td>
        <td>${esc(f.text || "")}</td>
      </tr>`).join("")}</tbody>
    </table>`;
  }

  async function loadSiteFeedback() {
    _beginNav(); // invalidate any in-flight search load
    activeName = null;
    latestRunDate = null;
    currentRunDate = null;
    dateToolbar.hidden = true;
    searchList.querySelectorAll("li").forEach(el => el.classList.remove("active"));
    configContent.innerHTML   = `<p class="loading">Loading site feedback…</p>`;
    resultsPanel.innerHTML    = `<p class="empty-state">Select a search to view results.</p>`;
    try {
      const entries = await api("GET", "/api/admin/site-feedback");
      configContent.innerHTML = renderSiteFeedbackTable(entries);
    } catch (e) {
      configContent.innerHTML = `<p class="empty-state">Failed to load site feedback: ${esc(e.message)}</p>`;
    }
  }

  async function refreshSidebar(selectName) {
    const searches = await api("GET", "/api/admin/searches");
    searchList.innerHTML = searches.map(s =>
      `<li role="option" data-name="${esc(s.search_name)}" class="${s.active ? "" : "inactive-search"}">
        ${esc(s.title || s.search_name.replace(/_/g, " "))}
      </li>`).join("");
    searchList.querySelectorAll("li").forEach(el =>
      el.addEventListener("click", () => selectSearch(el.dataset.name)));
    if (selectName) {
      activeName = null;
      selectSearch(selectName);
    }
  }

  // ── Search selection ──────────────────────────────────────────────────────

  let activeName = null;

  async function afterRun(name) {
    const seq = _beginNav();
    let dates = [];
    try { dates = await api("GET", `/api/results/${encodeURIComponent(name)}`); } catch { /* no runs yet */ }
    if (!_isCurrentNav(seq)) return; // superseded by a newer navigation while the run was in flight
    latestRunDate = dates[0] || null;
    populateDateSelect(dates);
    if (latestRunDate) {
      dateSelectEl.value = latestRunDate;
      await selectRunDate(name, latestRunDate);
    }
  }

  async function selectSearch(name) {
    if (activeName === name) return;
    const seq = _beginNav();
    activeName = name;

    searchList.querySelectorAll("li").forEach(el =>
      el.classList.toggle("active", el.dataset.name === name));

    configContent.innerHTML = `<p class="loading">Loading…</p>`;
    resultsPanel.innerHTML = `<p class="loading">Loading…</p>`;

    let dates = [];
    try { dates = await api("GET", `/api/results/${encodeURIComponent(name)}`); } catch { /* no runs yet */ }
    if (!_isCurrentNav(seq)) return; // superseded by a newer selectSearch/selectRunDate
    latestRunDate = dates[0] || null;
    populateDateSelect(dates);

    if (dates.length === 0) {
      // Zero-run search: no "latest run" to point at — must default to the
      // live editable config, not an absent state.
      currentRunDate = null;
      resultsPanel.innerHTML = `<p class="empty-state">No results yet.</p>`;
      await renderLiveConfig(name, seq);
      return;
    }

    dateSelectEl.value = latestRunDate;
    await selectRunDate(name, latestRunDate);
  }

  // ── Sidebar collapse ──────────────────────────────────────────────────────

  const adminSidebar = document.getElementById("admin-sidebar");
  const collapseBtn  = document.getElementById("sidebar-collapse-btn");

  collapseBtn.addEventListener("click", () => {
    const collapsed = adminSidebar.classList.toggle("admin-sidebar--collapsed");
    collapseBtn.setAttribute("aria-expanded", String(!collapsed));
    collapseBtn.setAttribute("aria-label", collapsed ? "Expand searches panel" : "Collapse searches panel");
  });

  // ── Config panel collapse ─────────────────────────────────────────────────

  const configCollapseBtn = document.getElementById("config-collapse-btn");

  configCollapseBtn.addEventListener("click", () => {
    const collapsed = adminPanels.classList.toggle("admin-panels--config-collapsed");
    configCollapseBtn.setAttribute("aria-expanded", String(!collapsed));
    configCollapseBtn.setAttribute("aria-label", collapsed ? "Expand config" : "Collapse config");
    configCollapseBtn.title = collapsed ? "Expand config" : "Collapse config";
  });

  // ── Init ─────────────────────────────────────────────────────────────────

  async function init() {
    const searches = await api("GET", "/api/admin/searches");

    searchList.innerHTML = searches.map(s =>
      `<li role="option" data-name="${esc(s.search_name)}" class="${s.active ? "" : "inactive-search"}">
        ${esc(s.title || s.search_name.replace(/_/g, " "))}
      </li>`).join("");

    searchList.querySelectorAll("li").forEach(el =>
      el.addEventListener("click", () => selectSearch(el.dataset.name)));

    if (searches.length) selectSearch(searches[0].search_name);

    document.getElementById("btn-new-search").addEventListener("click", () => {
      _beginNav(); // invalidate any in-flight search load
      activeName = null;
      latestRunDate = null;
      currentRunDate = null;
      dateToolbar.hidden = true;
      searchList.querySelectorAll("li").forEach(el => el.classList.remove("active"));
      configContent.innerHTML = renderGenerate();
      resultsPanel.innerHTML = `<p class="empty-state">Save the new search, then run it to see results.</p>`;
      bindGenerate();
    });

    document.getElementById("btn-users")?.addEventListener("click", loadUsers);
    document.getElementById("btn-site-feedback")?.addEventListener("click", loadSiteFeedback);

    document.getElementById("btn-logout")?.addEventListener("click", async () => {
      try { await fetch("/auth/logout", { method: "POST", credentials: "same-origin" }); } catch {}
      window.location.href = "/admin/login";
    });
  }

  init().catch(e => {
    if (e.status === 401) { window.location.href = "/admin/login"; return; }
    document.body.innerHTML = `<p style="padding:2rem;color:var(--score-red,red)">Failed to load admin: ${esc(e.message)}. <a href="/admin/login">Sign in again</a></p>`;
  });
})();
