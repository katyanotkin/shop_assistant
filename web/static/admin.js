(() => {
  const loginOverlay = document.getElementById("login-overlay");
  const adminLayout  = document.getElementById("admin-layout");
  const searchList   = document.getElementById("admin-search-list");
  const content      = document.getElementById("admin-content");

  // ── API ──────────────────────────────────────────────────────────────────

  async function api(method, path, body) {
    const opts = { method, credentials: "same-origin", headers: {} };
    if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    const r = await fetch(path, opts);
    if (r.status === 401) { const e = new Error("Unauthorized"); e.status = 401; throw e; }
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }

  // ── Auth ─────────────────────────────────────────────────────────────────

  function showLogin(err) {
    loginOverlay.hidden = false;
    adminLayout.hidden = true;
    const errEl = document.getElementById("login-err");
    errEl.textContent = err || "";
    errEl.hidden = !err;
    document.getElementById("pwd").value = "";
  }

  document.getElementById("login-form").addEventListener("submit", async e => {
    e.preventDefault();
    try {
      await api("POST", "/api/admin/login", { password: document.getElementById("pwd").value });
    } catch {
      showLogin("Wrong password.");
      return;
    }
    try {
      await init();
    } catch {
      showLogin("Login accepted but auth check failed — check server logs.");
    }
  });

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
  function tag(text, cls) { return `<span class="tag ${cls}">${text}</span>`; }

  function renderResultCard(m) {
    const sc = scoreClass(m.score);
    const site = siteName(m.url);
    const titleText = site && m.title
      ? `<span class="card-site">${site}</span><span class="card-sep"> | </span>${m.title}`
      : (m.title || "(no title)");
    const price = m.price != null ? `<span class="card-price">${m.price}</span>` : "";
    const newTag = m.is_new ? tag("NEW", "tag-new") : "";
    const criteria = [
      ...(m.matched || []).map(t => tag(t, "tag tag-match")),
      ...(m.unmatched || []).map(t => tag(t, "tag tag-miss")),
    ].join("");
    const notes = m.notes ? `<p class="card-notes">${m.notes}</p>` : "";
    return `<div class="card">
      <div class="score-badge ${sc}">${Math.round(m.score)}</div>
      <div class="card-body">
        <div class="card-title-row"><span class="card-title">${titleText}</span>${newTag}</div>
        <div class="card-meta">${price}</div>
        <a class="card-url" href="${m.url}" target="_blank" rel="noopener">${m.url}</a>
        ${criteria ? `<div class="criteria-row">${criteria}</div>` : ""}
        ${notes}
      </div>
    </div>`;
  }

  // ── Edit view ────────────────────────────────────────────────────────────

  function split(v) { return v.split(",").map(s => s.trim()).filter(Boolean); }
  function join(a)  { return (a || []).join(", "); }

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

  function renderEdit(cfg) {
    const c = cfg.criteria || {};
    return `<div class="edit-form" data-name="${cfg.search_name}">
      <div class="edit-top">
        <label class="active-label">
          <input type="checkbox" name="active" ${cfg.active ? "checked" : ""}> Active
        </label>
      </div>
      ${fieldRow("Category", "category", join(c.category))}
      ${fieldRow("Gender", "gender", c.gender)}
      ${fieldRow("Material", "material", join(c.material))}
      ${fieldRow("Lining", "lining", join(c.lining))}
      ${fieldRow("Length", "length", join(c.length))}
      ${fieldRow("Exclude", "exclude", join(c.exclude))}
      ${fieldRow("Sizes", "sizes", join(c.sizes))}
      ${fieldRow("Max price", "max_price", c.max_price, "number")}
      ${fieldRow("Notes", "extra_notes", c.extra_notes || "", "textarea")}
      ${fieldRow("Preferred shops", "preferred_shops", (cfg.preferred_shops || []).join("\n"), "textarea")}
      ${fieldRow("Example products (up to 3 URLs, one per line)", "example_urls", (cfg.example_urls || []).join("\n"), "textarea")}
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
    const name = form.dataset.name;
    return {
      search_name: name,
      active: g("active").checked,
      criteria: {
        category:    split(g("category").value),
        gender:      g("gender").value.trim(),
        material:    split(g("material").value),
        lining:      split(g("lining").value),
        length:      split(g("length").value),
        exclude:     split(g("exclude").value),
        sizes:       split(g("sizes").value),
        max_price:   parseFloat(g("max_price").value) || null,
        extra_notes: g("extra_notes").value.trim() || null,
      },
      preferred_shops: g("preferred_shops").value.split("\n").map(s => s.trim()).filter(Boolean),
      example_urls: g("example_urls").value.split("\n").map(s => s.trim()).filter(Boolean).slice(0, 3),
    };
  }

  function bindEdit(form, opts = {}) {
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
        showView(cfg.search_name, "results");
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

  // ── Results view ─────────────────────────────────────────────────────────

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
    } catch (e) {
      return `<p class="empty-state">No results yet.</p>`;
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
        <textarea id="gen-desc" class="field-input" rows="6" placeholder="I'm looking for a women's waxed cotton coat, midi length, natural lining…"></textarea>
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
        const panel = document.getElementById("view-panel") || content;
        panel.innerHTML = `<p class="save-msg ok" style="margin-bottom:12px">Generated — review, then Save or Save &amp; Run.</p>` + renderEdit(cfg);
        bindEdit(panel.querySelector(".edit-form"), { onSave: name => refreshSidebar(name) });
      } catch (e) {
        setMsg(e.message, "err");
        btn.disabled = false;
      }
    });
  }

  async function refreshSidebar(selectName) {
    const searches = await api("GET", "/api/admin/searches");
    searchList.innerHTML = searches.map(s =>
      `<li role="option" data-name="${s.search_name}" class="${s.active ? "" : "inactive-search"}">
        ${s.search_name.replace(/_/g, " ")}
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
  let activeView = "edit"; // "edit" | "results"

  function tabs(name) {
    return `<div class="view-tabs">
      <button class="tab-btn ${activeView === "edit" ? "active" : ""}" data-view="edit">Edit config</button>
      <button class="tab-btn ${activeView === "results" ? "active" : ""}" data-view="results">Results</button>
    </div>`;
  }

  async function showView(name, view) {
    activeView = view;
    // Update tab state
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.view === view));

    const panel = document.getElementById("view-panel");
    if (!panel) return;

    if (view === "edit") {
      try {
        const cfg = await api("GET", `/api/admin/search/${name}`);
        panel.innerHTML = renderEdit(cfg);
        bindEdit(panel.querySelector(".edit-form"));
      } catch (e) { panel.innerHTML = `<p class="empty-state">${e.message}</p>`; }
    } else {
      panel.innerHTML = `<p class="loading">Loading…</p>`;
      panel.innerHTML = await renderResults(name);
    }
  }

  async function selectSearch(name) {
    activeName = name;
    searchList.querySelectorAll("li").forEach(el =>
      el.classList.toggle("active", el.dataset.name === name));

    content.innerHTML = `${tabs(name)}<div id="view-panel"><p class="loading">Loading…</p></div>`;

    content.querySelectorAll(".tab-btn").forEach(btn => {
      btn.addEventListener("click", () => showView(name, btn.dataset.view));
    });

    showView(name, activeView);
  }

  // ── Init ─────────────────────────────────────────────────────────────────

  async function init() {
    const searches = await api("GET", "/api/admin/searches"); // throws on 401
    loginOverlay.hidden = true;
    adminLayout.hidden = false;

    searchList.innerHTML = searches.map(s =>
      `<li role="option" data-name="${s.search_name}" class="${s.active ? "" : "inactive-search"}">
        ${s.search_name.replace(/_/g, " ")}
      </li>`).join("");

    searchList.querySelectorAll("li").forEach(el =>
      el.addEventListener("click", () => selectSearch(el.dataset.name)));

    if (searches.length) selectSearch(searches[0].search_name);

    document.getElementById("btn-new-search").addEventListener("click", () => {
      activeName = null;
      searchList.querySelectorAll("li").forEach(el => el.classList.remove("active"));
      content.innerHTML = `<div id="view-panel">${renderGenerate()}</div>`;
      bindGenerate();
    });
  }

  init().catch(e => { if (e.status === 401) showLogin(); });
})();
