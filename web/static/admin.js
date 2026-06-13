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
      init();
    } catch { showLogin("Wrong password."); }
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
    const price = m.price ? `<span class="card-price">€${m.price}</span>` : "";
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
      <div class="action-row">
        <button class="btn-primary btn-save">Save</button>
        <button class="btn-run">Save &amp; Run</button>
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
    };
  }

  function bindEdit(form) {
    const msg  = form.querySelector(".save-msg");
    const setMsg = (text, cls) => { msg.textContent = text; msg.className = `save-msg ${cls}`; };

    form.querySelector(".btn-save").addEventListener("click", async () => {
      const cfg = collectConfig(form);
      try {
        await api("PUT", `/api/admin/search/${cfg.search_name}`, cfg);
        setMsg("Saved.", "ok");
        setTimeout(() => setMsg("", ""), 2500);
      } catch (e) { setMsg(e.message, "err"); }
    });

    form.querySelector(".btn-run").addEventListener("click", async () => {
      const cfg = collectConfig(form);
      const btnRun  = form.querySelector(".btn-run");
      const btnSave = form.querySelector(".btn-save");

      btnRun.disabled = true;
      btnSave.disabled = true;

      let dotsTimer;
      const startDots = () => {
        let n = 0;
        dotsTimer = setInterval(() => {
          n = (n + 1) % 4;
          btnRun.textContent = "Running" + ".".repeat(n + 1);
        }, 450);
      };
      const stopDots = () => {
        clearInterval(dotsTimer);
        btnRun.textContent = "Save & Run";
        btnRun.disabled = false;
        btnSave.disabled = false;
      };

      try {
        await api("PUT", `/api/admin/search/${cfg.search_name}`, cfg);
        await api("POST", `/api/admin/run/${cfg.search_name}`);
        startDots();
        setMsg("", "");

        // Poll until today's result appears in Firestore (run complete)
        const today = new Date().toISOString().slice(0, 10);
        await new Promise((resolve, reject) => {
          let attempts = 0;
          const id = setInterval(async () => {
            attempts++;
            if (attempts > 90) { clearInterval(id); reject(new Error("Timed out after 15 min")); return; }
            try {
              const dates = await api("GET", `/api/results/${encodeURIComponent(cfg.search_name)}`);
              if (dates.includes(today)) { clearInterval(id); resolve(); }
            } catch { /* keep polling */ }
          }, 10000);
        });

        stopDots();
        setMsg("Done! Switch to Results to view.", "ok");
      } catch (e) {
        stopDots();
        setMsg(e.message, "err");
      }
    });
  }

  // ── Results view ─────────────────────────────────────────────────────────

  async function renderResults(name) {
    content.innerHTML = `<p class="loading">Loading…</p>`;
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
      panel.innerHTML = await renderResults(name);
    }
  }

  async function selectSearch(name, searches) {
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
    try {
      const searches = await api("GET", "/api/admin/searches");
      loginOverlay.hidden = true;
      adminLayout.hidden = false;

      searchList.innerHTML = searches.map(s =>
        `<li role="option" data-name="${s.search_name}" class="${s.active ? "" : "inactive-search"}">
          ${s.search_name.replace(/_/g, " ")}
        </li>`).join("");

      searchList.querySelectorAll("li").forEach(el =>
        el.addEventListener("click", () => selectSearch(el.dataset.name, searches)));

      if (searches.length) selectSearch(searches[0].search_name, searches);
    } catch (e) {
      if (e.status === 401) showLogin();
      else content.innerHTML = `<p class="empty-state">Error: ${e.message}</p>`;
    }
  }

  init();
})();
