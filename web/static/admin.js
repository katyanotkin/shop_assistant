(() => {
  const searchList   = document.getElementById("admin-search-list");
  const configPanel   = document.getElementById("config-panel");
  const configContent = document.getElementById("config-content");
  const resultsPanel  = document.getElementById("results-panel");
  const adminPanels   = document.querySelector(".admin-panels");

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

  function renderResultCard(m, feedbackMap) {
    const sc = scoreClass(m.score);
    const site = siteName(m.url);
    const titleInner = site && m.title
      ? `<span class="card-site">${esc(site)}</span><span class="card-sep"> | </span>${esc(m.title)}`
      : esc(m.title || "(no title)");
    const titleText = `<a class="card-title-link" href="${esc(safeHref(m.url))}" target="_blank" rel="noopener">${titleInner}</a>`;
    const price = m.price != null ? `<span class="card-price">${esc(String(m.price))}</span>` : "";
    const newTag = m.is_new ? tag("NEW", "tag-new") : "";
    const criteria = [
      ...(m.matched || []).map(t => tag(t, "tag tag-match")),
      ...(m.unmatched || []).map(t => tag(t, "tag tag-miss")),
    ].join("");
    const notes = m.notes ? `<p class="card-notes">${esc(m.notes)}</p>` : "";
    const feedback = Feedback.renderFeedbackBlock(m.url, feedbackMap);
    return `<div class="card">
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
        loadResults(cfg.search_name);
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
    return `<div class="references-card">
      <div class="references-header">
        <span class="references-title">Reference products</span>
        <span class="ref-count"></span>
      </div>
      <p class="references-desc">Add up to 3 products you already love — the AI uses these to calibrate what a great match looks like for you.</p>
      <div class="ref-chips"></div>
      <div class="ref-input-row">
        <input type="url" class="field-input ref-url-input" placeholder="Paste a product URL…">
        <button class="btn-ref-add">Add</button>
      </div>
      <div class="ref-action-row">
        <button class="btn-ref-save btn-primary">Save references</button>
        <span class="ref-save-msg save-msg"></span>
      </div>
    </div>`;
  }

  function bindReferences(card, editForm, name) {
    const hidden = editForm.querySelector('[name="example_urls"]');
    let urls = hidden ? hidden.value.split("\n").filter(Boolean) : [];

    function chipLabel(u) {
      try { return siteName(u) || new URL(u).hostname; } catch { return u.slice(0, 40); }
    }

    function syncHidden() {
      if (hidden) hidden.value = urls.join("\n");
    }

    function renderChips() {
      const chipsEl = card.querySelector(".ref-chips");
      const countEl = card.querySelector(".ref-count");
      const inputRow = card.querySelector(".ref-input-row");
      chipsEl.innerHTML = urls.map(u => `
        <div class="ref-chip" data-url="${esc(u)}">
          <span class="ref-chip-label">${esc(chipLabel(u))}</span>
          <button class="ref-chip-remove" aria-label="Remove">×</button>
        </div>`).join("");
      countEl.textContent = `${urls.length} / 3`;
      if (inputRow) inputRow.hidden = urls.length >= 3;
      card.querySelectorAll(".ref-chip-remove").forEach(btn => {
        btn.addEventListener("click", () => {
          urls = urls.filter(u => u !== btn.closest(".ref-chip").dataset.url);
          renderChips();
          syncHidden();
        });
      });
    }

    renderChips();

    const urlInput = card.querySelector(".ref-url-input");
    const addBtn = card.querySelector(".btn-ref-add");

    function addUrl() {
      const val = urlInput.value.trim();
      if (!val || urls.length >= 3) return;
      try { new URL(val); } catch {
        urlInput.style.outline = "2px solid var(--score-red)";
        return;
      }
      urlInput.style.outline = "";
      if (!urls.includes(val)) { urls.push(val); renderChips(); syncHidden(); }
      urlInput.value = "";
    }

    addBtn.addEventListener("click", addUrl);
    urlInput.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); addUrl(); } });

    const saveBtn = card.querySelector(".btn-ref-save");
    const saveMsg = card.querySelector(".ref-save-msg");
    const setMsg = (t, cls) => { saveMsg.textContent = t; saveMsg.className = `ref-save-msg save-msg ${cls}`; };

    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      setMsg("Saving…", "");
      try {
        const cfg = await api("GET", `/api/admin/search/${name}`);
        cfg.example_urls = urls;
        await api("PUT", `/api/admin/search/${name}`, cfg);
        setMsg("Saved.", "ok");
        setTimeout(() => setMsg("", ""), 2500);
      } catch (e) { setMsg(e.message, "err"); }
      saveBtn.disabled = false;
    });
  }

  // ── Results panel ─────────────────────────────────────────────────────────

  async function loadResults(name) {
    resultsPanel.innerHTML = `<p class="loading">Loading…</p>`;
    try {
      const dates = await api("GET", `/api/results/${encodeURIComponent(name)}`);
      const runDate = dates[0];
      const run = await api("GET", `/api/results/${encodeURIComponent(name)}/${runDate}`);
      if (run.no_match || (!run.matches?.length && !run.partial_matches?.length)) {
        resultsPanel.innerHTML = `<p class="empty-state">No matches in latest run.</p>`;
        return;
      }
      const feedbackMap = run.feedback || {};
      let html = `<p class="run-meta">${runDate} · ${run.total_candidates ?? "?"} candidates</p>`;
      html += Feedback.renderSaveAllRow();
      if (run.matches?.length)
        html += `<div class="results-section"><p class="section-heading">Matches (${run.matches.length})</p>
          <div class="cards">${run.matches.map(m => renderResultCard(m, feedbackMap)).join("")}</div></div>`;
      if (run.partial_matches?.length)
        html += `<div class="results-section"><p class="section-heading">Partial (${run.partial_matches.length})</p>
          <div class="cards">${run.partial_matches.map(m => renderResultCard(m, feedbackMap)).join("")}</div></div>`;
      resultsPanel.innerHTML = html;
      Feedback.bindFeedback(resultsPanel, items => api(
        "PUT", `/api/feedback/${encodeURIComponent(name)}/${encodeURIComponent(runDate)}/batch`, { items },
      ));
    } catch {
      resultsPanel.innerHTML = `<p class="empty-state">No results yet.</p>`;
    }
  }

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

  function renderConfigHeader(cfg) {
    const vis = cfg.visibility || "public";
    return `<div class="config-header-row">
      <span class="config-search-name">${esc(cfg.title || cfg.search_name.replace(/_/g, " "))}</span>
      <button type="button" class="btn-visibility btn-run" data-name="${esc(cfg.search_name)}" data-visibility="${esc(vis)}">
        ${vis === "public" ? "Make private" : "Make public"}
      </button>
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
    activeName = null;
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

  async function selectSearch(name) {
    if (activeName === name) return;
    activeName = name;

    searchList.querySelectorAll("li").forEach(el =>
      el.classList.toggle("active", el.dataset.name === name));

    configContent.innerHTML = `<p class="loading">Loading…</p>`;
    resultsPanel.innerHTML = `<p class="loading">Loading…</p>`;

    try {
      const cfg = await api("GET", `/api/admin/search/${name}`);
      configContent.innerHTML = renderConfigHeader(cfg) + renderEdit(cfg) + renderReferences();
      bindVisibilityToggle(configContent.querySelector(".config-header-row"));
      const form = configPanel.querySelector(".edit-form");
      bindEdit(form);
      bindReferences(configPanel.querySelector(".references-card"), form, name);
    } catch (e) {
      configContent.innerHTML = `<p class="empty-state">${esc(e.message)}</p>`;
    }

    loadResults(name);
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
      activeName = null;
      searchList.querySelectorAll("li").forEach(el => el.classList.remove("active"));
      configContent.innerHTML = renderGenerate();
      resultsPanel.innerHTML = `<p class="empty-state">Save the new search, then run it to see results.</p>`;
      bindGenerate();
    });

    document.getElementById("btn-users")?.addEventListener("click", loadUsers);

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
