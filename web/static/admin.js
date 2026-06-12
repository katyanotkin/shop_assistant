(() => {
  const root = document.getElementById("admin-root");

  async function api(method, path, body) {
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

  function split(val) { return val.split(",").map(s => s.trim()).filter(Boolean); }
  function join(arr)  { return (arr || []).join(", "); }

  function field(label, name, value, type = "text") {
    if (type === "textarea") return `
      <div class="field-row">
        <label class="field-label">${label}</label>
        <textarea name="${name}" class="field-input" rows="3">${value}</textarea>
      </div>`;
    if (type === "number") return `
      <div class="field-row">
        <label class="field-label">${label}</label>
        <input type="number" name="${name}" class="field-input" value="${value ?? ""}" step="any">
      </div>`;
    return `
      <div class="field-row">
        <label class="field-label">${label}</label>
        <input type="text" name="${name}" class="field-input" value="${value ?? ""}">
      </div>`;
  }

  function renderCard(cfg) {
    const c = cfg.criteria || {};
    return `<div class="search-card" data-name="${cfg.search_name}">
      <div class="search-header">
        <h3 class="search-name">${cfg.search_name.replace(/_/g, " ")}</h3>
        <label class="active-label">
          <input type="checkbox" name="active" ${cfg.active ? "checked" : ""}> Active
        </label>
      </div>
      ${field("Category", "category", join(c.category))}
      ${field("Gender", "gender", c.gender)}
      ${field("Material", "material", join(c.material))}
      ${field("Lining", "lining", join(c.lining))}
      ${field("Length", "length", join(c.length))}
      ${field("Exclude", "exclude", join(c.exclude))}
      ${field("Sizes", "sizes", join(c.sizes))}
      ${field("Max price", "max_price", c.max_price, "number")}
      ${field("Notes", "extra_notes", c.extra_notes || "", "textarea")}
      ${field("Preferred shops", "preferred_shops", (cfg.preferred_shops || []).join("\n"), "textarea")}
      <div class="action-row">
        <button class="btn-save">Save</button>
        <span class="save-msg"></span>
      </div>
    </div>`;
  }

  function collect(card) {
    const g = n => card.querySelector(`[name="${n}"]`);
    return {
      search_name: card.dataset.name,
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

  function bindCard(card) {
    card.querySelector(".btn-save").addEventListener("click", async () => {
      const cfg = collect(card);
      const msg = card.querySelector(".save-msg");
      try {
        await api("PUT", `/api/admin/search/${cfg.search_name}`, cfg);
        msg.textContent = "Saved."; msg.className = "save-msg ok";
        setTimeout(() => { msg.textContent = ""; }, 2500);
      } catch (e) {
        msg.textContent = e.message; msg.className = "save-msg err";
      }
    });
  }

  function renderLogin(err) {
    root.innerHTML = `
      <div class="login-wrap">
        <form id="login-form" class="login-card">
          <h2 class="login-title">Admin</h2>
          ${err ? `<p class="login-err">${err}</p>` : ""}
          <input type="password" id="pwd" class="field-input" placeholder="Password" autofocus>
          <button type="submit" class="btn-save">Log in</button>
        </form>
      </div>`;
    document.getElementById("login-form").addEventListener("submit", async e => {
      e.preventDefault();
      try {
        await api("POST", "/api/admin/login", { password: document.getElementById("pwd").value });
        init();
      } catch { renderLogin("Wrong password."); }
    });
  }

  async function init() {
    try {
      const searches = await api("GET", "/api/admin/searches");
      root.innerHTML = `<div class="admin-wrap">${searches.map(renderCard).join("")}</div>`;
      root.querySelectorAll(".search-card").forEach(bindCard);
    } catch (e) {
      if (e.status === 401) renderLogin();
      else root.innerHTML = `<p class="empty-state">Error: ${e.message}</p>`;
    }
  }

  init();
})();
