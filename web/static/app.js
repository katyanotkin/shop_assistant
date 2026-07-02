(() => {
  const searchList        = document.getElementById("search-list");
  const toolbar           = document.getElementById("toolbar");
  const dateSelect        = document.getElementById("date-select");
  const resultsPanel      = document.getElementById("results-panel");
  const createPanel       = document.getElementById("create-panel");
  const runSearchBtn      = document.getElementById("run-search-btn");
  const editSearchBtn     = document.getElementById("edit-search-btn");
  const runGateMsg        = document.getElementById("run-gate-msg");
  const newSearchContainer = document.getElementById("new-search-container");

  const _defaultTitle = document.title;

  let activeSearch = null;
  let me           = { role: "free", anonymous: true };
  let _loadSeq     = 0;
  let _searches    = [];
  let _showFeedback = false;
  let _savedToolbarVisible  = false;
  let _savedCriteriaVisible = false;

  // ── Sidebar collapse ──────────────────────────────────────────────────────
  const sidebarEl     = document.getElementById("sidebar");
  const sidebarToggle = document.getElementById("sidebar-toggle-btn");

  function setSidebarCollapsed(collapsed) {
    sidebarEl.classList.toggle("collapsed", collapsed);
    if (sidebarToggle) {
      sidebarToggle.textContent = collapsed ? "▶" : "◀";
      sidebarToggle.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
    }
    try { localStorage.setItem("sa-sidebar-collapsed", collapsed ? "1" : ""); } catch {}
  }

  sidebarToggle?.addEventListener("click", () => {
    setSidebarCollapsed(!sidebarEl.classList.contains("collapsed"));
  });

  try {
    if (localStorage.getItem("sa-sidebar-collapsed") === "1") setSidebarCollapsed(true);
  } catch {}

  // ── API ───────────────────────────────────────────────────────────────────
  async function api(path, { method = "GET", body } = {}) {
    const opts = { method, credentials: "same-origin", headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const r = await fetch(path, opts);
    if (r.status === 401) { const e = new Error("Unauthorized"); e.status = 401; throw e; }
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function esc(s) {
    return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function formatPrice(p) {
    if (p == null) return "";
    const s = String(p).trim();
    return /^[$£€¥₹₩₺₽฿]/.test(s) ? s : `$${s}`;
  }

  function siteName(url) {
    try {
      const locales = new Set(["us", "uk", "eu", "au", "ca"]);
      const skip    = new Set(["www", "shop", "store", "m", "en", "co"]);
      const parts   = new URL(url).hostname.split(".");
      const labels  = [];
      for (let i = 0; i < parts.length - 1; i++) {
        const p = parts[i].toLowerCase();
        if (skip.has(p)) continue;
        labels.push(locales.has(p) ? p.toUpperCase() : p.charAt(0).toUpperCase() + p.slice(1));
      }
      return labels.join(" ") || parts[0];
    } catch { return ""; }
  }

  const DAY_MS = 24 * 60 * 60 * 1000;
  const FREE_PLAN_MSG = "You're on the Free plan. Contact us to get full access.";

  // Mirrors the backend's `(now - created_at).days > 30` (Python timedelta.days floors to
  // whole elapsed days), so the button disables exactly when the server would 403.
  function isRunWindowExpired(createdAt) {
    if (!createdAt) return false;
    const created = new Date(createdAt);
    if (isNaN(created.getTime())) return false;
    const elapsedDays = Math.floor((Date.now() - created.getTime()) / DAY_MS);
    return elapsedDays > 30;
  }

  function scoreClass(s) { return s >= 7 ? "green" : s >= 4 ? "amber" : "red"; }
  function tag(text, cls) { return `<span class="tag ${cls}">${esc(text)}</span>`; }
  function safeHref(url) {
    try { const u = new URL(url); return (u.protocol === "https:" || u.protocol === "http:") ? url : "#"; }
    catch { return "#"; }
  }

  // ── User slot ─────────────────────────────────────────────────────────────
  function updateUserSlot() {
    const slot = document.getElementById("user-slot");
    if (!slot) return;
    if (me.anonymous) {
      slot.innerHTML = `<a href="/auth/login" class="topbar-signin-btn">Sign in</a>`;
    } else {
      const name = esc(me.name || me.email || "");
      slot.innerHTML = `<span class="topbar-username" title="${esc(me.email || "")}">${name}</span>
        <button id="signout-btn" class="topbar-signout-btn">Sign out</button>
        <button id="delete-account-btn" class="topbar-signout-btn topbar-delete-btn">Delete account</button>`;
      document.getElementById("signout-btn")?.addEventListener("click", async () => {
        try { await fetch("/auth/logout", { method: "POST", credentials: "same-origin" }); } catch {}
        window.location.href = "/";
      });
      document.getElementById("delete-account-btn")?.addEventListener("click", async () => {
        if (!confirm("Delete your account? Your login info will be removed within seconds. Your search data is retained (as described in our Privacy Policy). This cannot be undone.")) return;
        try {
          const r = await fetch("/api/me", { method: "DELETE", credentials: "same-origin" });
          if (r.ok) { window.location.href = "/"; return; }
        } catch {}
        alert("Something went wrong. Please try again or email assistantderecherche@gmail.com.");
      });
    }
  }

  // ── New search button ─────────────────────────────────────────────────────
  function updateNewSearchBtn(searches) {
    if (!newSearchContainer) return;
    const mine = searches.filter(s => s.owned);
    if (me.anonymous) {
      newSearchContainer.hidden = true;
      return;
    }
    if (me.role === "admin") {
      newSearchContainer.innerHTML = `<a href="/admin" class="btn-new-search">Admin panel</a>`;
      newSearchContainer.hidden = false;
      return;
    }
    if (me.role === "premium" || (me.role === "free" && mine.length === 0)) {
      newSearchContainer.innerHTML = `<button id="new-search-btn" class="btn-new-search">+ New search</button>`;
      newSearchContainer.hidden = false;
      document.getElementById("new-search-btn").addEventListener("click", openCreatePanel);
      return;
    }
    newSearchContainer.hidden = true;
  }

  // ── Criteria bar ─────────────────────────────────────────────────────────
  function renderCriteriaBar(config) {
    const bar = document.getElementById("criteria-bar");
    if (!bar) return;
    const c = config.criteria || {};
    const chips = [];
    if (c.category?.length) chips.push(...[].concat(c.category));
    if (c.gender) chips.push(c.gender);
    if (c.material?.length) chips.push(...[].concat(c.material));
    if (c.sizes?.length) chips.push(`sizes: ${[].concat(c.sizes).join(", ")}`);
    if (c.max_price != null) chips.push(`max ${c.max_price}`);
    if (c.exclude?.length) chips.push(`excl. ${[].concat(c.exclude).join(", ")}`);
    if (!chips.length && !c.extra_notes) { bar.hidden = true; return; }
    let html = `<div class="criteria-summary">${chips.map(p => `<span class="criteria-chip">${esc(p)}</span>`).join("")}</div>`;
    if (c.extra_notes) html += `<p class="criteria-notes">${esc(c.extra_notes)}</p>`;
    bar.innerHTML = html;
    bar.hidden = false;
  }

  // ── Results rendering ─────────────────────────────────────────────────────
  function renderCard(m, showFeedback, feedbackMap) {
    const sc       = scoreClass(m.score);
    const newTag   = m.is_new ? tag("NEW", "tag-new") : "";
    const price    = m.price != null ? `<span class="card-price">${esc(formatPrice(m.price))}</span>` : "";
    const criteria = [
      ...(m.matched   || []).map(t => tag(t, "tag tag-match")),
      ...(m.unmatched || []).map(t => tag(t, "tag tag-miss")),
    ].join("");
    const notes      = m.notes ? `<p class="card-notes">${esc(m.notes)}</p>` : "";
    const site       = siteName(m.url);
    const titleInner = site && m.title
      ? `<span class="card-site">${esc(site)}</span><span class="card-sep"> | </span>${esc(m.title)}`
      : esc(m.title || "(no title)");
    const titleText  = `<a class="card-title-link" href="${esc(safeHref(m.url))}" target="_blank" rel="noopener">${titleInner}</a>`;
    const feedback   = showFeedback ? Feedback.renderFeedbackBlock(m.url, feedbackMap) : "";
    return `
      <div class="card">
        <div class="score-badge ${sc}">${Math.round(m.score)}</div>
        <div class="card-body">
          <div class="card-title-row">${titleText}${newTag}</div>
          <div class="card-meta">${price}</div>
          ${criteria ? `<div class="criteria-row">${criteria}</div>` : ""}
          ${notes}
          ${feedback}
        </div>
      </div>`;
  }

  function dedupeByUrl(items) {
    const seen = new Map();
    for (const item of items) {
      const prev = seen.get(item.url);
      if (!prev || (item.title || "").length > (prev.title || "").length) seen.set(item.url, item);
    }
    return [...seen.values()];
  }

  function renderResults(run, showFeedback) {
    if (run.no_match || (!run.matches?.length && !run.partial_matches?.length)) {
      resultsPanel.innerHTML = `<p class="empty-state">No matches found for this run.</p>`;
      return;
    }
    const matches   = dedupeByUrl(run.matches || []);
    const matchUrls = new Set(matches.map(m => m.url));
    const partials  = dedupeByUrl((run.partial_matches || []).filter(m => !matchUrls.has(m.url)));
    const label = run.config_snapshot?.title || (run.search_name || "").replace(/_/g, " ");
    const feedbackMap = run.feedback || {};
    let html = `<p class="run-meta"><span class="run-search-label">${esc(label)}</span><span class="run-date-label">${esc(run.run_date || "")}</span><span class="run-candidates">${run.total_candidates ?? "?"} candidates</span></p>`;
    if (showFeedback) html += Feedback.renderSaveAllRow();
    if (matches.length) html += `<div class="results-section">
      <p class="section-heading">Matches (${matches.length})</p>
      <div class="cards">${matches.map(m => renderCard(m, showFeedback, feedbackMap)).join("")}</div>
    </div>`;
    if (partials.length) html += `<div class="results-section">
      <p class="section-heading">Partial matches (${partials.length})</p>
      <div class="cards">${partials.map(m => renderCard(m, showFeedback, feedbackMap)).join("")}</div>
    </div>`;
    resultsPanel.innerHTML = html;
  }

  // ── Load / select ─────────────────────────────────────────────────────────
  async function loadRun(searchName, runDate, showFeedback) {
    const seq = ++_loadSeq;
    resultsPanel.innerHTML = `<p class="loading">Loading…</p>`;
    try {
      const run = await api(`/api/results/${encodeURIComponent(searchName)}/${encodeURIComponent(runDate)}`);
      if (seq !== _loadSeq) return;
      renderResults(run, showFeedback);
      if (showFeedback) {
        Feedback.bindFeedback(resultsPanel, items => api(
          `/api/feedback/${encodeURIComponent(searchName)}/${encodeURIComponent(runDate)}/batch`,
          { method: "PUT", body: { items } },
        ));
      }
    } catch (e) {
      if (seq !== _loadSeq) return;
      resultsPanel.innerHTML = `<p class="empty-state">Failed to load results: ${esc(e.message)}</p>`;
    }
  }

  async function selectSearch(name, { replace = false } = {}) {
    if (activeSearch === name) return;

    if (!createPanel.hidden) closeCreatePanel();

    activeSearch = name;
    if (replace) history.replaceState({}, "", "/" + encodeURIComponent(name));
    else         history.pushState({}, "", "/" + encodeURIComponent(name));
    const title = _searches.find(s => s.name === name)?.title || name.replace(/_/g, " ");
    document.title = `${title} — TailoredLoop`;

    document.querySelectorAll(".search-list li").forEach(el =>
      el.classList.toggle("active", el.dataset.name === name));

    runSearchBtn.hidden = true;
    editSearchBtn.hidden = true;
    runGateMsg.hidden = true;
    toolbar.hidden = true;
    const criteriaBar = document.getElementById("criteria-bar");
    if (criteriaBar) criteriaBar.hidden = true;
    resultsPanel.hidden = false;
    resultsPanel.innerHTML = `<p class="loading">Loading dates…</p>`;
    try {
      const owned = _searches.find(s => s.name === name)?.owned || false;
      const promises = [
        api(`/api/results/${encodeURIComponent(name)}`),
        api(`/api/search/${encodeURIComponent(name)}`).catch(() => null),
      ];
      if (owned) promises.push(api(`/api/user/search/${encodeURIComponent(name)}`).catch(() => null));
      const [dates, config, ownerConfig] = await Promise.all(promises);
      dateSelect.innerHTML = dates.map(d => `<option value="${d}">${d}</option>`).join("");
      toolbar.hidden = false;
      if (config) renderCriteriaBar(config);
      runSearchBtn.hidden = !owned;
      const canEdit = owned && me.role !== "admin";
      _showFeedback = canEdit;
      editSearchBtn.hidden = !canEdit;
      const expired = owned && me.role === "free" && isRunWindowExpired(ownerConfig && ownerConfig.created_at);
      runSearchBtn.disabled = expired;
      runGateMsg.hidden = !expired;
      if (expired) runGateMsg.textContent = FREE_PLAN_MSG;
      await loadRun(name, dates[0], _showFeedback);
    } catch {
      resultsPanel.innerHTML = `<p class="empty-state">No runs found for this search.</p>`;
    }
  }

  dateSelect.addEventListener("change", () => {
    if (activeSearch) loadRun(activeSearch, dateSelect.value, _showFeedback);
  });

  runSearchBtn.addEventListener("click", async () => {
    const name = activeSearch;
    if (!name) return;
    runSearchBtn.disabled = true;
    const origText = runSearchBtn.textContent;
    runSearchBtn.textContent = "Running…";
    try {
      await api(`/api/user/search/${encodeURIComponent(name)}/run`, { method: "POST" });
      const dates = await api(`/api/results/${encodeURIComponent(name)}`);
      dateSelect.innerHTML = dates.map(d => `<option value="${d}">${d}</option>`).join("");
      if (dates.length) await loadRun(name, dates[0], _showFeedback);
    } catch (e) {
      resultsPanel.innerHTML = `<p class="empty-state">Run failed: ${esc(e.message)}</p>`;
    } finally {
      runSearchBtn.textContent = origText;
      runSearchBtn.disabled = false;
    }
  });

  editSearchBtn.addEventListener("click", () => {
    if (activeSearch) openEditPanel(activeSearch);
  });

  // ── Create search panel ───────────────────────────────────────────────────
  function openCreatePanel() {
    _savedToolbarVisible = !toolbar.hidden;
    const criteriaBar = document.getElementById("criteria-bar");
    _savedCriteriaVisible = criteriaBar ? !criteriaBar.hidden : false;
    toolbar.hidden = true;
    if (criteriaBar) criteriaBar.hidden = true;
    resultsPanel.hidden = true;
    createPanel.innerHTML = renderCreatePanel();
    createPanel.hidden = false;
    bindCreatePanel();
  }

  function closeCreatePanel() {
    createPanel.hidden = true;
    resultsPanel.hidden = false;
    if (_savedToolbarVisible) toolbar.hidden = false;
    const criteriaBar = document.getElementById("criteria-bar");
    if (criteriaBar && _savedCriteriaVisible) criteriaBar.hidden = false;
  }

  function renderCreatePanel() {
    return `<div class="generate-panel">
      <h2 class="generate-title">New search</h2>
      <div class="field-row">
        <label class="field-label" for="cs-title">Title</label>
        <input type="text" id="cs-title" class="field-input" placeholder="e.g. Bathroom Cabinet" autocomplete="off">
      </div>
      <div class="field-row">
        <label class="field-label" for="cs-desc">Description</label>
        <textarea id="cs-desc" class="field-input" rows="6" placeholder="Describe what you want — category, material, size, max price, shops to search…"></textarea>
      </div>
      <div class="action-row">
        <button id="cs-generate-btn" class="btn-primary">Generate</button>
        <button id="cs-cancel-btn" class="btn-run">Cancel</button>
        <span id="cs-msg" class="save-msg"></span>
      </div>
      <div id="cs-preview" hidden>
        <pre id="cs-config-pre" class="cs-config-pre"></pre>
        <div class="action-row">
          <button id="cs-save-btn" class="btn-primary">Save</button>
          <button id="cs-run-btn" class="btn-run" hidden>Run</button>
          <span id="cs-save-msg" class="save-msg"></span>
        </div>
      </div>
    </div>`;
  }

  function bindCreatePanel() {
    let generatedConfig = null;
    let savedName       = null;

    const msg    = document.getElementById("cs-msg");
    const setMsg = (text, cls) => { msg.textContent = text; msg.className = `save-msg ${cls}`; };

    document.getElementById("cs-cancel-btn").addEventListener("click", closeCreatePanel);

    document.getElementById("cs-generate-btn").addEventListener("click", async () => {
      const titleVal = document.getElementById("cs-title").value.trim();
      const desc     = document.getElementById("cs-desc").value.trim();
      if (!titleVal) { setMsg("Title is required.", "err"); return; }
      if (desc.length < 10) { setMsg("Description must be at least 10 characters.", "err"); return; }

      const genBtn = document.getElementById("cs-generate-btn");
      genBtn.disabled = true;
      setMsg("Generating…", "");
      try {
        generatedConfig = await api("/api/user/search/generate", { method: "POST", body: { title: titleVal, description: desc } });
        document.getElementById("cs-config-pre").textContent = JSON.stringify(generatedConfig, null, 2);
        document.getElementById("cs-preview").hidden = false;
        setMsg("", "");
      } catch (e) {
        setMsg(e.message, "err");
        genBtn.disabled = false;
      }
    });

    document.getElementById("cs-save-btn").addEventListener("click", async () => {
      if (!generatedConfig) return;
      const saveBtn = document.getElementById("cs-save-btn");
      const saveMsg = document.getElementById("cs-save-msg");
      const setSaveMsg = (t, cls) => { saveMsg.textContent = t; saveMsg.className = `save-msg ${cls}`; };
      saveBtn.disabled = true;
      setSaveMsg("Saving…", "");
      try {
        const name = generatedConfig.search_name;
        await api(`/api/user/search/${encodeURIComponent(name)}`, { method: "PUT", body: generatedConfig });
        savedName = name;
        setSaveMsg("Saved.", "ok");
        document.getElementById("cs-run-btn").hidden = false;
        const searches = await api("/api/searches");
        _searches = searches;
        buildSearchList(searches);
        updateNewSearchBtn(searches);
      } catch (e) {
        setSaveMsg(e.message, "err");
        saveBtn.disabled = false;
      }
    });

    document.getElementById("cs-run-btn").addEventListener("click", async () => {
      if (!savedName) return;
      const runBtn = document.getElementById("cs-run-btn");
      const saveMsg = document.getElementById("cs-save-msg");
      const setSaveMsg = (t, cls) => { saveMsg.textContent = t; saveMsg.className = `save-msg ${cls}`; };
      runBtn.disabled = true;
      setSaveMsg("Running…", "");
      try {
        await api(`/api/user/search/${encodeURIComponent(savedName)}/run`, { method: "POST" });
        const name = savedName;
        closeCreatePanel();
        activeSearch = null;
        selectSearch(name);
      } catch (e) {
        setSaveMsg(e.message, "err");
        runBtn.disabled = false;
      }
    });
  }

  // ── Edit search panel ─────────────────────────────────────────────────────
  async function openEditPanel(name) {
    _savedToolbarVisible = !toolbar.hidden;
    const criteriaBar = document.getElementById("criteria-bar");
    _savedCriteriaVisible = criteriaBar ? !criteriaBar.hidden : false;
    toolbar.hidden = true;
    if (criteriaBar) criteriaBar.hidden = true;
    resultsPanel.hidden = true;
    createPanel.innerHTML = `<p class="loading">Loading…</p>`;
    createPanel.hidden = false;
    try {
      const cfg = await api(`/api/user/search/${encodeURIComponent(name)}`);
      createPanel.innerHTML = renderEditPanel(cfg);
      bindEditPanel(cfg);
    } catch (e) {
      createPanel.innerHTML = `<p class="empty-state">Failed to load search: ${esc(e.message)}</p>
        <div class="action-row"><button id="edit-back-btn" class="btn-run">Back</button></div>`;
      document.getElementById("edit-back-btn").addEventListener("click", closeCreatePanel);
    }
  }

  function renderEditPanel(cfg) {
    const actions = `<div class="action-row">
      <button type="button" class="btn-primary" id="edit-save-btn">Save</button>
      <button type="button" class="btn-run" id="edit-cancel-btn">Cancel</button>
      <button type="button" class="btn-run edit-delete-btn" id="edit-delete-btn">Delete search</button>
      <span class="save-msg" id="edit-save-msg"></span>
    </div>`;
    return `<div class="generate-panel">
      <h2 class="generate-title">Edit search</h2>
      <div class="field-row">
        <label class="field-label" for="edit-title">Title</label>
        <input type="text" id="edit-title" class="field-input" value="${esc(cfg.title || "")}" maxlength="200" autocomplete="off">
      </div>
      ${CriteriaForm.renderEdit(cfg, actions)}
    </div>`;
  }

  function bindEditPanel(cfg) {
    const form = createPanel.querySelector(".edit-form");
    CriteriaForm.bindFieldControls(form);

    const titleInput = document.getElementById("edit-title");
    const saveMsg    = document.getElementById("edit-save-msg");
    const setMsg     = (text, cls) => { saveMsg.textContent = text; saveMsg.className = `save-msg ${cls}`; };

    document.getElementById("edit-cancel-btn").addEventListener("click", closeCreatePanel);

    document.getElementById("edit-save-btn").addEventListener("click", async () => {
      const title = titleInput.value.trim();
      if (!title) { setMsg("Title is required.", "err"); return; }
      const saveBtn = document.getElementById("edit-save-btn");
      saveBtn.disabled = true;
      setMsg("Saving…", "");
      try {
        const updated = { ...cfg, ...CriteriaForm.collectConfig(form), title };
        await api(`/api/user/search/${encodeURIComponent(cfg.search_name)}`, { method: "PUT", body: updated });
        setMsg("Saved.", "ok");
        const searches = await api("/api/searches");
        _searches = searches;
        buildSearchList(searches);
        updateNewSearchBtn(searches);
        closeCreatePanel();
        const name = cfg.search_name;
        activeSearch = null;
        selectSearch(name);
      } catch (e) {
        setMsg(e.message, "err");
        saveBtn.disabled = false;
      }
    });

    document.getElementById("edit-delete-btn").addEventListener("click", async () => {
      if (!confirm(`Delete "${cfg.title || cfg.search_name}"? This cannot be undone.`)) return;
      const delBtn = document.getElementById("edit-delete-btn");
      delBtn.disabled = true;
      setMsg("Deleting…", "");
      try {
        await api(`/api/user/search/${encodeURIComponent(cfg.search_name)}`, { method: "DELETE" });
        activeSearch = null;
        const searches = await api("/api/searches");
        _searches = searches;
        buildSearchList(searches);
        updateNewSearchBtn(searches);
        createPanel.hidden = true;
        createPanel.innerHTML = "";
        history.replaceState({}, "", "/");
        document.title = _defaultTitle;
        toolbar.hidden = true;
        runSearchBtn.hidden = true;
        editSearchBtn.hidden = true;
        runGateMsg.hidden = true;
        const criteriaBar = document.getElementById("criteria-bar");
        if (criteriaBar) criteriaBar.hidden = true;
        resultsPanel.hidden = false;
        resultsPanel.innerHTML = `<p class="empty-state">Select a search from the left to view results.</p>`;
      } catch (e) {
        setMsg(e.message, "err");
        delBtn.disabled = false;
      }
    });
  }

  // ── Sidebar ───────────────────────────────────────────────────────────────
  function buildSearchList(searches) {
    const mine       = searches.filter(s => s.owned);
    const common     = searches.filter(s => !s.owned);
    const showLabels = mine.length > 0;

    function itemHTML(s) {
      return `<li role="option" tabindex="0" data-name="${esc(s.name)}" class="${s.active ? "" : "inactive-search"}">
        <span>${esc(s.title || s.name.replace(/_/g, " "))}</span>
        <button class="copy-link-btn" title="Copy link" aria-label="Copy link to ${esc(s.name)}">⎘</button>
      </li>`;
    }

    let html = "";
    if (mine.length) {
      html += `<li class="search-group-label">My searches</li>`;
      html += mine.map(itemHTML).join("");
    }
    if (showLabels && common.length) html += `<li class="search-group-label">Public</li>`;
    html += common.map(itemHTML).join("");
    searchList.innerHTML = html;

    searchList.querySelectorAll("li[role='option']").forEach(el => {
      el.addEventListener("click", () => selectSearch(el.dataset.name));
      el.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") selectSearch(el.dataset.name); });
    });

    searchList.querySelectorAll(".copy-link-btn").forEach(btn => {
      btn.addEventListener("click", e => {
        e.stopPropagation();
        const name = btn.closest("li").dataset.name;
        navigator.clipboard.writeText(`${location.origin}/${name}`)
          .then(() => { btn.textContent = "✓"; setTimeout(() => { btn.textContent = "⎘"; }, 1500); })
          .catch(() => { btn.textContent = "✗"; setTimeout(() => { btn.textContent = "⎘"; }, 1500); });
      });
    });

    if (activeSearch) {
      searchList.querySelectorAll("li[role='option']").forEach(el =>
        el.classList.toggle("active", el.dataset.name === activeSearch));
    }
  }

  // ── Init ─────────────────────────────────────────────────────────────────
  async function init() {
    try {
      const [searches, meResult] = await Promise.all([
        api("/api/searches"),
        api("/api/me").catch(() => ({ role: "free", anonymous: true })),
      ]);
      me = meResult;
      _searches = searches;
      updateUserSlot();
      buildSearchList(searches);
      updateNewSearchBtn(searches);

      const fromPath = decodeURIComponent(window.location.pathname.slice(1));
      const initial  = searches.find(s => s.name === fromPath) ? fromPath : searches[0]?.name;
      if (initial) selectSearch(initial, { replace: true });
    } catch {
      searchList.innerHTML = `<li style="padding:12px 16px;color:var(--text-muted)">Failed to load searches</li>`;
    }
  }

  init();
})();
