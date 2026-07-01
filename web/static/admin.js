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

  function renderResultCard(m) {
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
    return `<div class="card">
      <div class="score-badge ${sc}">${Math.round(m.score)}</div>
      <div class="card-body">
        <div class="card-title-row">${titleText}${newTag}</div>
        <div class="card-meta">${price}</div>
        ${criteria ? `<div class="criteria-row">${criteria}</div>` : ""}
        ${notes}
      </div>
    </div>`;
  }

  // ── Edit view ────────────────────────────────────────────────────────────

  function split(v) { return v.split(",").map(s => s.trim()).filter(Boolean); }
  function join(a)  { return (a || []).join(", "); }
  function toLabel(name) { return name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()); }

  // Immutable fields are always shown and cannot be removed.
  // Optional fields are shown only when the config has a value; the user can
  // add or remove them via the field picker.
  const CRITERIA_FIELDS = [
    { name: "category",        label: "Category",        type: "text",     immutable: true  },
    { name: "gender",          label: "Gender",          type: "text",     immutable: false },
    { name: "material",        label: "Material",        type: "text",     immutable: false },
    { name: "lining",          label: "Lining",          type: "text",     immutable: false },
    { name: "length",          label: "Length",          type: "text",     immutable: false },
    { name: "exclude",         label: "Exclude",         type: "text",     immutable: false },
    { name: "sizes",           label: "Sizes",           type: "text",     immutable: false },
    { name: "max_price",       label: "Max price",       type: "number",   immutable: false },
    { name: "extra_notes",     label: "Notes",           type: "textarea", immutable: false },
  ];

  // Top-level (non-criteria) optional fields — always rendered but removable.
  const TOP_LEVEL_FIELDS = [
    { name: "preferred_shops", label: "Preferred shops", type: "textarea", immutable: false },
  ];

  function fieldRow(label, name, value, type, immutable) {
    const present = value !== null && value !== undefined && value !== "";
    const hidden  = !immutable && !present;
    const removeBtn = immutable ? "" : `<button type="button" class="btn-field-remove" aria-label="Remove ${label}">×</button>`;
    const attrs = [
      `class="field-row${immutable ? "" : " field-row--opt"}"`,
      `data-field-name="${name}"`,
      hidden ? "hidden" : "",
    ].filter(Boolean).join(" ");
    if (type === "textarea") return `<div ${attrs}>
      <label class="field-label">${label}</label>
      <textarea name="${name}" class="field-input" rows="3">${value || ""}</textarea>${removeBtn}</div>`;
    if (type === "number") return `<div ${attrs}>
      <label class="field-label">${label}</label>
      <input type="number" name="${name}" class="field-input" value="${value ?? ""}" step="any">${removeBtn}</div>`;
    return `<div ${attrs}>
      <label class="field-label">${label}</label>
      <input type="text" name="${name}" class="field-input" value="${value ?? ""}">${removeBtn}</div>`;
  }

  function renderEdit(cfg) {
    const c = cfg.criteria || {};

    const criteriaRows = CRITERIA_FIELDS.map(f => {
      const raw = c[f.name];
      const value = Array.isArray(raw) ? join(raw) : (raw ?? "");
      return fieldRow(f.label, f.name, value, f.type, f.immutable);
    }).join("\n");

    const knownNames = new Set(CRITERIA_FIELDS.map(f => f.name));
    const customRows = Object.keys(c)
      .filter(k => !knownNames.has(k))
      .map(k => {
        const raw = c[k];
        const value = Array.isArray(raw) ? join(raw) : String(raw ?? "");
        return `<div class="field-row field-row--opt field-row--custom" data-field-name="${esc(k)}">
          <label class="field-label">${esc(toLabel(k))}</label>
          <input type="text" name="${esc(k)}" class="field-input" value="${esc(value)}">
          <button type="button" class="btn-field-remove" aria-label="Remove ${esc(toLabel(k))}">×</button>
        </div>`;
      }).join("\n");

    const topRows = TOP_LEVEL_FIELDS.map(f => {
      const raw = cfg[f.name];
      const value = Array.isArray(raw) ? raw.join("\n") : (raw ?? "");
      return fieldRow(f.label, f.name, value, f.type, f.immutable);
    }).join("\n");

    const allOptional = [...CRITERIA_FIELDS, ...TOP_LEVEL_FIELDS].filter(f => !f.immutable);

    return `<div class="edit-form" data-name="${cfg.search_name}">
      <div class="edit-top">
        <label class="active-label">
          <input type="checkbox" name="active" ${cfg.active ? "checked" : ""}> Active
        </label>
      </div>
      ${criteriaRows}
      ${customRows}
      ${topRows}
      <input type="hidden" name="example_urls" value="${(cfg.example_urls || []).join("\n")}">
      <div class="add-field-row" aria-label="Add a field">
        <span class="add-field-label">Add:</span>
        ${allOptional.map(f => `<button type="button" class="btn-add-field" data-field="${f.name}">${f.label}</button>`).join("")}
        <input type="text" class="custom-field-name" placeholder="custom field…" aria-label="Custom field name">
        <button type="button" class="btn-add-custom">+</button>
      </div>
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
    const name = form.dataset.name;
    const criteria = {};

    // Walk every visible criteria field row by its data-field-name.
    CRITERIA_FIELDS.forEach(f => {
      const row = form.querySelector(`.field-row[data-field-name="${f.name}"]`);
      if (!row || row.hidden) return;
      const el = row.querySelector(`[name="${f.name}"]`);
      if (!el) return;
      if (f.type === "number") {
        const v = parseFloat(el.value);
        if (!isNaN(v)) criteria[f.name] = v;
      } else if (f.type === "text") {
        // gender is a scalar string; all other text fields are comma-separated arrays
        criteria[f.name] = (f.name === "gender")
          ? (el.value.trim() || null)
          : (split(el.value).length ? split(el.value) : undefined);
        if (criteria[f.name] === undefined) delete criteria[f.name];
      } else if (f.type === "textarea") {
        const v = el.value.trim();
        if (v) criteria[f.name] = v;
      }
    });

    form.querySelectorAll(".field-row--custom").forEach(row => {
      if (row.hidden) return;
      const name = row.dataset.fieldName;
      const el = row.querySelector("input, textarea");
      if (!el) return;
      const v = el.value.trim();
      if (!v) return;
      const parts = split(v);
      criteria[name] = parts.length > 1 ? parts : v;
    });

    const preferredShopsRow = form.querySelector('.field-row[data-field-name="preferred_shops"]');
    const preferredShops = (!preferredShopsRow || preferredShopsRow.hidden)
      ? []
      : (preferredShopsRow.querySelector('[name="preferred_shops"]')?.value || "")
          .split("\n").map(s => s.trim()).filter(Boolean);

    return {
      search_name: name,
      active: form.querySelector('[name="active"]').checked,
      criteria,
      preferred_shops: preferredShops,
      example_urls: (form.querySelector('[name="example_urls"]')?.value || "")
        .split("\n").map(s => s.trim()).filter(Boolean).slice(0, 3),
    };
  }

  function bindFieldControls(form) {
    const allOptional = [...CRITERIA_FIELDS, ...TOP_LEVEL_FIELDS].filter(f => !f.immutable);

    function syncChips() {
      allOptional.forEach(f => {
        const chip = form.querySelector(`.btn-add-field[data-field="${f.name}"]`);
        if (!chip) return;
        const row = form.querySelector(`.field-row[data-field-name="${f.name}"]`);
        chip.hidden = row && !row.hidden;
      });
    }

    function removeRow(row) {
      row.hidden = true;
      const el = row.querySelector("input, textarea");
      if (el) el.value = "";
      syncChips();
    }

    function showRow(name) {
      const row = form.querySelector(`.field-row[data-field-name="${name}"]`);
      if (!row) return;
      row.hidden = false;
      row.querySelector("input, textarea")?.focus();
      syncChips();
    }

    form.querySelectorAll(".btn-field-remove").forEach(btn => {
      btn.addEventListener("click", () => removeRow(btn.closest(".field-row")));
    });

    form.querySelectorAll(".btn-add-field").forEach(chip => {
      chip.addEventListener("click", () => showRow(chip.dataset.field));
    });

    const customNameInput = form.querySelector(".custom-field-name");
    const btnAddCustom = form.querySelector(".btn-add-custom");
    if (btnAddCustom && customNameInput) {
      function addCustomField() {
        const rawName = customNameInput.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
        if (!rawName) return;
        const existing = form.querySelector(`.field-row[data-field-name="${rawName}"]`);
        if (existing) { existing.hidden = false; existing.querySelector("input, textarea")?.focus(); syncChips(); customNameInput.value = ""; return; }
        const label = toLabel(rawName);
        const row = document.createElement("div");
        row.className = "field-row field-row--opt field-row--custom";
        row.dataset.fieldName = rawName;
        row.innerHTML = `<label class="field-label">${esc(label)}</label><input type="text" name="${esc(rawName)}" class="field-input" value=""><button type="button" class="btn-field-remove" aria-label="Remove ${esc(label)}">×</button>`;
        form.querySelector(".add-field-row").before(row);
        row.querySelector(".btn-field-remove").addEventListener("click", () => removeRow(row));
        row.querySelector("input").focus();
        customNameInput.value = "";
      }
      btnAddCustom.addEventListener("click", addCustomField);
      customNameInput.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); addCustomField(); } });
    }

    syncChips();
  }

  function bindEdit(form, opts = {}) {
    bindFieldControls(form);

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
        await api("PUT", `/api/admin/search/${cfg.search_name}`, cfg);
        setMsg("Saved.", "ok");
        setTimeout(() => setMsg("", ""), 2500);
        if (opts.onSave) opts.onSave(cfg.search_name);
      } catch (e) { setMsg(e.message, "err"); }
    });

    async function runSearch(btn, saveFirst) {
      const cfg = collectConfig(form);
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

  async function renderResults(name) {
    try {
      const dates = await api("GET", `/api/results/${encodeURIComponent(name)}`);
      const run = await api("GET", `/api/results/${encodeURIComponent(name)}/${dates[0]}`);
      if (run.no_match || (!run.matches?.length && !run.partial_matches?.length)) {
        return `<p class="empty-state">No matches in latest run.</p>`;
      }
      let html = `<p class="run-meta">${dates[0]} · ${run.total_candidates ?? "?"} candidates</p>`;
      if (run.matches?.length)
        html += `<div class="results-section"><p class="section-heading">Matches (${run.matches.length})</p>
          <div class="cards">${run.matches.map(renderResultCard).join("")}</div></div>`;
      if (run.partial_matches?.length)
        html += `<div class="results-section"><p class="section-heading">Partial (${run.partial_matches.length})</p>
          <div class="cards">${run.partial_matches.map(renderResultCard).join("")}</div></div>`;
      return html;
    } catch {
      return `<p class="empty-state">No results yet.</p>`;
    }
  }

  async function loadResults(name) {
    resultsPanel.innerHTML = `<p class="loading">Loading…</p>`;
    resultsPanel.innerHTML = await renderResults(name);
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
      <span class="config-search-name">${esc(cfg.search_name.replace(/_/g, " "))}</span>
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
        ${esc(s.search_name.replace(/_/g, " "))}
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
        ${esc(s.search_name.replace(/_/g, " "))}
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
