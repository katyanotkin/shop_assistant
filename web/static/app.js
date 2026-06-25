(() => {
  const searchList  = document.getElementById("search-list");
  const toolbar     = document.getElementById("toolbar");
  const dateSelect  = document.getElementById("date-select");
  const resultsPanel = document.getElementById("results-panel");
  const editPanel   = document.getElementById("edit-panel");

  let activeSearch = null;
  let isAdmin      = false;
  let me           = { role: "free", anonymous: true };
  let _loadSeq     = 0;

  // ── Sidebar collapse ──────────────────────────────────────────────────────
  const sidebarEl      = document.getElementById("sidebar");
  const sidebarToggle  = document.getElementById("sidebar-toggle-btn");

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

  function scoreClass(s) { return s >= 7 ? "green" : s >= 4 ? "amber" : "red"; }
  function tag(text, cls) { return `<span class="tag ${cls}">${text}</span>`; }
  function split(v) { return v.split(",").map(s => s.trim()).filter(Boolean); }
  function join(a)  { return (a || []).join(", "); }

  // ── Admin login modal ─────────────────────────────────────────────────────
  const loginOverlay = document.getElementById("login-overlay");
  const loginErr     = document.getElementById("login-err");

  function showLogin() {
    loginOverlay.hidden = false;
    document.getElementById("admin-pwd").value = "";
    if (loginErr) { loginErr.textContent = ""; loginErr.hidden = true; }
  }
  function hideLogin() { loginOverlay.hidden = true; }

  document.getElementById("login-cancel")?.addEventListener("click", hideLogin);
  document.getElementById("login-form")?.addEventListener("submit", async e => {
    e.preventDefault();
    try {
      await api("/api/admin/login", { method: "POST", body: { password: document.getElementById("admin-pwd").value } });
      hideLogin();
      isAdmin = true;
      updateAdminUI();
      if (activeSearch && dateSelect.value) loadRun(activeSearch, dateSelect.value);
    } catch {
      if (loginErr) { loginErr.textContent = "Wrong password."; loginErr.hidden = false; }
    }
  });

  // ── Admin UI state ────────────────────────────────────────────────────────
  function updateAdminUI() {
    const editBtn = document.getElementById("edit-search-btn");
    const runBtn  = document.getElementById("run-search-btn");
    const topBtn  = document.getElementById("topbar-admin-btn");
    if (editBtn) editBtn.hidden = !isAdmin;
    if (runBtn)  runBtn.hidden  = !isAdmin;
    if (topBtn) {
      topBtn.textContent = isAdmin ? "Admin ✓" : "Admin";
      topBtn.classList.toggle("topbar-admin-btn--active", isAdmin);
    }
  }

  function updateUserSlot() {
    const slot = document.getElementById("user-slot");
    if (!slot) return;
    if (me.anonymous) {
      slot.innerHTML = `<a href="/auth/login" class="topbar-signin-btn">Sign in</a>`;
    } else if (me.role !== "admin") {
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

  function showPremiumBanner() {
    const existing = resultsPanel.querySelector(".premium-banner");
    if (existing) return;
    const banner = document.createElement("div");
    banner.className = "premium-banner";
    const msg = me.anonymous
      ? `<a href="/auth/login">Sign in with Google</a> to save your own searches.`
      : `You're on the Free plan. <a href="mailto:assistantderecherche@gmail.com">Contact us</a> to get full access.`;
    banner.innerHTML = `${msg} <button class="premium-banner-dismiss" aria-label="Dismiss">\xd7</button>`;
    banner.querySelector(".premium-banner-dismiss").addEventListener("click", () => banner.remove());
    resultsPanel.prepend(banner);
  }

  document.getElementById("topbar-admin-btn")?.addEventListener("click", e => {
    e.preventDefault();
    if (isAdmin) { if (activeSearch) openEditPanel(activeSearch); }
    else         showLogin();
  });

  document.getElementById("edit-search-btn")?.addEventListener("click", () => {
    if (!isAdmin) { showPremiumBanner(); return; }
    if (activeSearch) openEditPanel(activeSearch);
  });

  document.getElementById("run-search-btn")?.addEventListener("click", async () => {
    if (!activeSearch) return;
    if (!isAdmin) { showPremiumBanner(); return; }
    const btn = document.getElementById("run-search-btn");
    btn.disabled = true;
    btn.textContent = "Running…";
    try {
      await api(`/api/admin/run/${activeSearch}`, { method: "POST", body: { learn: true } });
      btn.textContent = "Run ▶";
      const dates = await api(`/api/results/${encodeURIComponent(activeSearch)}`);
      dateSelect.innerHTML = dates.map(d => `<option value="${d}">${d}</option>`).join("");
      toolbar.hidden = false;
      await loadRun(activeSearch, dates[0]);
    } catch (e) {
      btn.textContent = "Run ▶";
      alert(`Run failed: ${e.message}`);
    }
    btn.disabled = false;
  });

  // ── Edit panel ────────────────────────────────────────────────────────────
  function openEditPanel(name) {
    editPanel.hidden = false;
    editPanel.innerHTML = `<p class="loading">Loading…</p>`;
    api(`/api/admin/search/${name}`).then(cfg => {
      editPanel.innerHTML = `
        <div class="edit-panel-header">
          <span class="edit-panel-title">${esc(name.replace(/_/g, " "))}</span>
          <button id="close-edit-btn" class="edit-panel-close" aria-label="Close">×</button>
        </div>` + renderEdit(cfg) + renderReferences();
      const form = editPanel.querySelector(".edit-form");
      bindEdit(form, {
        onAfterRun: async () => {
          const dates = await api(`/api/results/${encodeURIComponent(name)}`);
          dateSelect.innerHTML = dates.map(d => `<option value="${d}">${d}</option>`).join("");
          toolbar.hidden = false;
          await loadRun(name, dates[0]);
        },
      });
      bindReferences(editPanel.querySelector(".references-card"), form, name);
      document.getElementById("close-edit-btn").addEventListener("click", () => { editPanel.hidden = true; });
    }).catch(e => {
      editPanel.innerHTML = `<p class="empty-state">${esc(e.message)}</p>`;
    });
  }

  // ── Edit form ─────────────────────────────────────────────────────────────
  function fieldRow(label, name, value, type = "text") {
    if (type === "textarea") return `<div class="field-row">
      <label class="field-label">${label}</label>
      <textarea name="${name}" class="field-input" rows="3">${value}</textarea></div>`;
    if (type === "number") return `<div class="field-row">
      <label class="field-label">${label}</label>
      <input type="number" name="${name}" class="field-input" value="${value ?? ""}" step="any"></div>`;
    return `<div class="field-row">
      <label class="field-label">${label}</label>
      <input type="text" name="${name}" class="field-input" value="${value ?? ""}"></div>`;
  }

  // Cosmetic preference only — unknown keys still render at end, no coupling to schema.
  const _KEY_ORDER = ["category", "gender", "material", "lining", "length", "exclude", "sizes", "max_price", "extra_notes"];
  const _TEXTAREA_KEYS = new Set(["extra_notes"]);
  function _labelFor(k) { return k.replace(/_/g, " ").replace(/^./, c => c.toUpperCase()); }
  function _orderCriteriaKeys(keys) {
    return [...keys].sort((a, b) => {
      const ri = _KEY_ORDER.indexOf(a), rj = _KEY_ORDER.indexOf(b);
      return (ri === -1 ? 999 : ri) - (rj === -1 ? 999 : rj);
    });
  }

  function criteriaRow(key, value) {
    const label = _labelFor(key);
    if (Array.isArray(value)) {
      return `<div class="field-row">
        <label class="field-label">${label}</label>
        <div class="chip-field" data-key="${esc(key)}" data-chips='${esc(JSON.stringify(value))}'>
          <div class="chip-list"></div>
          <input type="text" class="chip-input field-input" placeholder="Add…" autocomplete="off">
        </div>
      </div>`;
    }
    const type = _TEXTAREA_KEYS.has(key) ? "textarea" : typeof value === "number" ? "number" : "text";
    return fieldRow(label, `criteria.${key}`, value ?? "", type);
  }

  function bindCriteriaChips(field) {
    let items = JSON.parse(field.dataset.chips || "[]");
    const listEl = field.querySelector(".chip-list");
    const input  = field.querySelector(".chip-input");

    const sync = () => { field.dataset.chips = JSON.stringify(items); };

    function renderChips() {
      listEl.innerHTML = items.map(v => `
        <span class="chip" data-val="${esc(v)}">${esc(v)
        }<button type="button" class="chip-remove" aria-label="Remove ${esc(v)}">×</button></span>`).join("");
      listEl.querySelectorAll(".chip-remove").forEach(btn => {
        btn.addEventListener("click", () => {
          items = items.filter(v => v !== btn.closest(".chip").dataset.val);
          renderChips(); sync();
        });
      });
    }
    renderChips();

    const add = () => {
      const v = input.value.trim();
      if (v && !items.includes(v)) { items.push(v); renderChips(); sync(); }
      input.value = "";
    };
    input.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
      if (e.key === "Backspace" && !input.value && items.length) {
        items.pop(); renderChips(); sync();
      }
    });
    input.addEventListener("blur", add);
  }

  function renderEdit(cfg) {
    const c   = cfg.criteria || {};
    const vis = cfg.visibility || "public";
    const rows = _orderCriteriaKeys(Object.keys(c)).map(k => criteriaRow(k, c[k])).join("");
    return `<div class="edit-form" data-name="${cfg.search_name}">
      <div class="edit-top">
        <label class="active-label">
          <input type="checkbox" name="active" ${cfg.active ? "checked" : ""}> Active
        </label>
        <label class="active-label">
          <input type="checkbox" name="visibility_private" ${vis === "private" ? "checked" : ""}> Private
        </label>
      </div>
      ${rows}
      ${fieldRow("Preferred shops", "preferred_shops", (cfg.preferred_shops || []).join("\n"), "textarea")}
      <input type="hidden" name="example_urls" value="${esc((cfg.example_urls || []).join("\n"))}">
      <div class="action-row">
        <button class="btn-run btn-run-only">Run</button>
        <button class="btn-primary btn-save">Save</button>
        <button class="btn-run btn-save-run">Save &amp; Run</button>
        <label class="learn-label">
          <input type="checkbox" name="learn_feedback" checked> Learn from feedback
        </label>
        <span class="save-msg"></span>
      </div>
    </div>`;
  }

  function collectConfig(form) {
    const g = n => form.querySelector(`[name="${n}"]`);
    const criteria = {};
    // Array fields: state lives in data-chips JSON on the div.
    form.querySelectorAll(".chip-field").forEach(f => {
      criteria[f.dataset.key] = JSON.parse(f.dataset.chips || "[]");
    });
    // Scalar fields: inputs namespaced as criteria.<key>.
    form.querySelectorAll('[name^="criteria."]').forEach(el => {
      const key = el.name.slice("criteria.".length);
      const raw = el.value.trim();
      criteria[key] = el.type === "number" ? (parseFloat(raw) || null) : (raw || null);
    });
    return {
      search_name: form.dataset.name,
      active:      g("active").checked,
      visibility:  g("visibility_private").checked ? "private" : "public",
      criteria,
      preferred_shops: g("preferred_shops").value.split("\n").map(s => s.trim()).filter(Boolean),
      example_urls:    g("example_urls").value.split("\n").map(s => s.trim()).filter(Boolean).slice(0, 3),
    };
  }

  function bindEdit(form, opts = {}) {
    form.querySelectorAll(".chip-field").forEach(bindCriteriaChips);
    const msg        = form.querySelector(".save-msg");
    const setMsg     = (text, cls) => { msg.textContent = text; msg.className = `save-msg ${cls}`; };
    const btnSave    = form.querySelector(".btn-save");
    const btnRunOnly = form.querySelector(".btn-run-only");
    const btnSaveRun = form.querySelector(".btn-save-run");
    const learnChk   = form.querySelector("[name='learn_feedback']");
    const allBtns    = [btnSave, btnRunOnly, btnSaveRun];

    btnSave.addEventListener("click", async () => {
      const cfg = collectConfig(form);
      try {
        await api(`/api/admin/search/${cfg.search_name}`, { method: "PUT", body: cfg });
        setMsg("Saved.", "ok");
        setTimeout(() => setMsg("", ""), 2500);
      } catch (e) { setMsg(e.message, "err"); }
    });

    async function runSearch(btn, saveFirst) {
      const cfg = collectConfig(form);
      const orig = btn.textContent;
      allBtns.forEach(b => b.disabled = true);
      let n = 0;
      const timer = setInterval(() => { btn.textContent = "...".slice(0, (n++ % 3) + 1); }, 400);
      try {
        if (saveFirst) await api(`/api/admin/search/${cfg.search_name}`, { method: "PUT", body: cfg });
        const result = await api(`/api/admin/run/${cfg.search_name}`, { method: "POST", body: { learn: learnChk.checked } });
        clearInterval(timer);
        btn.textContent = orig;
        allBtns.forEach(b => b.disabled = false);
        setMsg(`Done — ${result.matches} matches, ${result.partial} partial.`, "ok");
        if (opts.onAfterRun) await opts.onAfterRun();
      } catch (e) {
        clearInterval(timer);
        btn.textContent = orig;
        allBtns.forEach(b => b.disabled = false);
        setMsg(e.message, "err");
      }
    }

    btnRunOnly.addEventListener("click", () => runSearch(btnRunOnly, false));
    btnSaveRun.addEventListener("click", () => runSearch(btnSaveRun, true));
  }

  // ── Reference products card ───────────────────────────────────────────────
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
    function syncHidden() { if (hidden) hidden.value = urls.join("\n"); }

    function renderChips() {
      const chipsEl  = card.querySelector(".ref-chips");
      const countEl  = card.querySelector(".ref-count");
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
          renderChips(); syncHidden();
        });
      });
    }
    renderChips();

    const urlInput = card.querySelector(".ref-url-input");
    const addBtn   = card.querySelector(".btn-ref-add");

    function addUrl() {
      const val = urlInput.value.trim();
      if (!val || urls.length >= 3) return;
      try { new URL(val); } catch { urlInput.style.outline = "2px solid var(--score-red)"; return; }
      urlInput.style.outline = "";
      if (!urls.includes(val)) { urls.push(val); renderChips(); syncHidden(); }
      urlInput.value = "";
    }
    addBtn.addEventListener("click", addUrl);
    urlInput.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); addUrl(); } });

    const saveBtn = card.querySelector(".btn-ref-save");
    const saveMsg = card.querySelector(".ref-save-msg");
    const setMsg  = (t, cls) => { saveMsg.textContent = t; saveMsg.className = `ref-save-msg save-msg ${cls}`; };

    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true; setMsg("Saving…", "");
      try {
        const cfg = await api(`/api/admin/search/${name}`);
        cfg.example_urls = urls;
        await api(`/api/admin/search/${name}`, { method: "PUT", body: cfg });
        setMsg("Saved.", "ok");
        setTimeout(() => setMsg("", ""), 2500);
      } catch (e) { setMsg(e.message, "err"); }
      saveBtn.disabled = false;
    });
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
  const _PHRASES = ["Perfect match", "Wrong material", "Too expensive", "Wrong style", "Doesn't ship to me", "Out of stock"];

  function renderCard(m, feedbackMap) {
    const sc    = scoreClass(m.score);
    const newTag = m.is_new ? tag("NEW", "tag-new") : "";
    const price  = m.price != null ? `<span class="card-price">${esc(formatPrice(m.price))}</span>` : "";
    const criteria = [
      ...(m.matched   || []).map(t => tag(t, "tag tag-match")),
      ...(m.unmatched || []).map(t => tag(t, "tag tag-miss")),
    ].join("");
    const notes      = m.notes ? `<p class="card-notes">${esc(m.notes)}</p>` : "";
    const site       = siteName(m.url);
    const titleInner = site && m.title
      ? `<span class="card-site">${esc(site)}</span><span class="card-sep"> | </span>${esc(m.title)}`
      : esc(m.title || "(no title)");
    const titleText  = `<a class="card-title-link" href="${esc(m.url)}" target="_blank" rel="noopener">${titleInner}</a>`;
    const existingFeedback = feedbackMap?.[m.url] || "";
    const phrases = _PHRASES.map(p => `<button type="button" class="phrase-btn" data-phrase="${p}">${p}</button>`).join("");
    const feedbackSection = isAdmin ? `
      <div class="feedback-row" data-url="${m.url}">
        <div class="feedback-phrases">${phrases}</div>
        <div class="feedback-input-row">
          <textarea class="feedback-text" placeholder="Add feedback…" rows="2" maxlength="256">${existingFeedback}</textarea>
        </div>
        <span class="feedback-charcount">${existingFeedback.length}/256</span>
      </div>` : "";
    return `
      <div class="card">
        <div class="score-badge ${sc}">${Math.round(m.score)}</div>
        <div class="card-body">
          <div class="card-title-row">${titleText}${newTag}</div>
          <div class="card-meta">${price}</div>
          ${criteria ? `<div class="criteria-row">${criteria}</div>` : ""}
          ${notes}
          ${feedbackSection}
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

  function renderResults(run) {
    if (run.no_match || (!run.matches?.length && !run.partial_matches?.length)) {
      resultsPanel.innerHTML = `<p class="empty-state">No matches found for this run.</p>`;
      return;
    }
    const fb      = run.feedback || {};
    const matches  = dedupeByUrl(run.matches || []);
    const matchUrls = new Set(matches.map(m => m.url));
    const partials  = dedupeByUrl((run.partial_matches || []).filter(m => !matchUrls.has(m.url)));
    const searchLabel = (run.search_name || "").replace(/_/g, " ");
    let html = `<p class="run-meta"><span class="run-search-label">${esc(searchLabel)}</span><span class="run-date-label">${esc(run.run_date || "")}</span><span class="run-candidates">${run.total_candidates ?? "?"} candidates</span></p>`;
    if (isAdmin) {
      const overallFb = fb["_overall_"] || "";
      html += `<div class="save-all-row">
        <textarea id="overall-feedback" class="overall-feedback-text" placeholder="Overall run notes…" rows="2" maxlength="512">${overallFb}</textarea>
        <div class="save-all-controls">
          <button type="button" id="save-all-btn" class="save-all-btn">Save all feedback</button>
          <span id="save-all-msg" class="feedback-msg"></span>
        </div>
      </div>`;
    }
    if (matches.length) html += `<div class="results-section">
      <p class="section-heading">Matches (${matches.length})</p>
      <div class="cards">${matches.map(m => renderCard(m, fb)).join("")}</div>
    </div>`;
    if (partials.length) html += `<div class="results-section">
      <p class="section-heading">Partial matches (${partials.length})</p>
      <div class="cards">${partials.map(m => renderCard(m, fb)).join("")}</div>
    </div>`;
    resultsPanel.innerHTML = html;
  }

  function bindFeedback(searchName, runDate) {
    resultsPanel.querySelectorAll(".feedback-row").forEach(row => {
      const textarea  = row.querySelector(".feedback-text");
      const charcount = row.querySelector(".feedback-charcount");
      const updateCount = () => { charcount.textContent = `${textarea.value.length}/256`; };
      textarea.addEventListener("input", updateCount);
      row.querySelectorAll(".phrase-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          textarea.value = textarea.value ? `${textarea.value}; ${btn.dataset.phrase}` : btn.dataset.phrase;
          updateCount();
        });
      });
    });

    const saveAllBtn      = document.getElementById("save-all-btn");
    const saveAllMsg      = document.getElementById("save-all-msg");
    const overallTextarea = document.getElementById("overall-feedback");
    if (!saveAllBtn) return;
    saveAllBtn.addEventListener("click", async () => {
      const rows  = [...resultsPanel.querySelectorAll(".feedback-row")];
      const items = rows
        .map(r => ({ url: r.dataset.url, text: r.querySelector(".feedback-text").value.trim() }))
        .filter(i => i.text);
      const overallText = overallTextarea?.value.trim();
      if (overallText) items.push({ url: "_overall_", text: overallText });
      if (!items.length) {
        saveAllMsg.textContent = "Nothing to save";
        setTimeout(() => { saveAllMsg.textContent = ""; }, 2000);
        return;
      }
      saveAllBtn.disabled = true;
      saveAllMsg.textContent = `Saving ${items.length}…`;
      try {
        await api(`/api/feedback/${encodeURIComponent(searchName)}/${encodeURIComponent(runDate)}/batch`,
          { method: "PUT", body: { items } });
        saveAllMsg.textContent = "Saved";
      } catch { saveAllMsg.textContent = "Failed"; }
      saveAllBtn.disabled = false;
      setTimeout(() => { saveAllMsg.textContent = ""; }, 3000);
    });
  }

  // ── Load / select ─────────────────────────────────────────────────────────
  async function loadRun(searchName, runDate) {
    const seq = ++_loadSeq;
    resultsPanel.innerHTML = `<p class="loading">Loading…</p>`;
    try {
      const [run, meResult] = await Promise.all([
        api(`/api/results/${encodeURIComponent(searchName)}/${encodeURIComponent(runDate)}`),
        api("/api/me").catch(() => ({ role: "free", anonymous: true })),
      ]);
      if (seq !== _loadSeq) return;
      me = meResult;
      isAdmin = me.role === "admin";
      updateAdminUI();
      updateUserSlot();
      renderResults(run);
      bindFeedback(searchName, runDate);
    } catch (e) {
      if (seq !== _loadSeq) return;
      resultsPanel.innerHTML = `<p class="empty-state">Failed to load results: ${e.message}</p>`;
    }
  }

  async function selectSearch(name, { replace = false } = {}) {
    if (activeSearch === name) return;
    activeSearch = name;
    if (replace) history.replaceState({}, "", "/" + encodeURIComponent(name));
    else         history.pushState({}, "", "/" + encodeURIComponent(name));
    document.title = `${name.replace(/_/g, " ")} — TailoredLoop`;

    editPanel.hidden = true;

    document.querySelectorAll(".search-list li").forEach(el =>
      el.classList.toggle("active", el.dataset.name === name));

    toolbar.hidden = true;
    const criteriaBar = document.getElementById("criteria-bar");
    if (criteriaBar) criteriaBar.hidden = true;
    resultsPanel.innerHTML = `<p class="loading">Loading dates…</p>`;
    try {
      const [dates, config] = await Promise.all([
        api(`/api/results/${encodeURIComponent(name)}`),
        api(`/api/search/${encodeURIComponent(name)}`).catch(() => null),
      ]);
      dateSelect.innerHTML = dates.map(d => `<option value="${d}">${d}</option>`).join("");
      toolbar.hidden = false;
      if (config) renderCriteriaBar(config);
      await loadRun(name, dates[0]);
    } catch {
      resultsPanel.innerHTML = `<p class="empty-state">No runs found for this search.</p>`;
    }
  }

  dateSelect.addEventListener("change", () => {
    if (activeSearch) loadRun(activeSearch, dateSelect.value);
  });

  // ── Init ─────────────────────────────────────────────────────────────────
  async function init() {
    try {
      const [searches, meResult] = await Promise.all([
        api("/api/searches"),
        api("/api/me").catch(() => ({ role: "free", anonymous: true })),
      ]);
      me = meResult;
      isAdmin = me.role === "admin";
      updateAdminUI();
      updateUserSlot();
      const common = searches.filter(s => s.visibility !== "private");
      const mine   = searches.filter(s => s.visibility === "private" && s.owned);
      const showLabels = mine.length > 0;

      function itemHTML(s) {
        return `<li role="option" tabindex="0" data-name="${s.name}" class="${s.active ? "" : "inactive-search"}">
          <span>${s.name.replace(/_/g, " ")}</span>
          <button class="copy-link-btn" title="Copy link" aria-label="Copy link to ${s.name}">⎘</button>
        </li>`;
      }

      let html = "";
      if (showLabels && common.length) html += `<li class="search-group-label">Public</li>`;
      html += common.map(itemHTML).join("");
      if (mine.length) {
        html += `<li class="search-group-label">My searches</li>`;
        html += mine.map(itemHTML).join("");
      }
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

      const fromPath = decodeURIComponent(window.location.pathname.slice(1));
      const initial  = searches.find(s => s.name === fromPath) ? fromPath : searches[0]?.name;
      if (initial) selectSearch(initial, { replace: true });
    } catch {
      searchList.innerHTML = `<li style="padding:12px 16px;color:var(--text-muted)">Failed to load searches</li>`;
    }
  }

  init();
})();
