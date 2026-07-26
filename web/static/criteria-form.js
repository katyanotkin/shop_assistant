(() => {
  function esc(s) {
    return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

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

  // Fields already enforced elsewhere in the ranker prompt as hard (gender) or
  // near-hard (exclude) rules — marking them a deal-breaker would be a no-op
  // that just confuses the prompt, so they don't get the toggle at all.
  const DEAL_BREAKER_INELIGIBLE = new Set(["category", "gender", "exclude"]);

  function dealBreakerToggle(name, type, immutable, dealBreaker) {
    if (immutable || type === "textarea" || DEAL_BREAKER_INELIGIBLE.has(name)) return "";
    const safeName = esc(name);
    return `<label class="field-dealbreaker-label">
      <input type="checkbox" class="field-dealbreaker" data-field="${safeName}" ${dealBreaker ? "checked" : ""}> Deal-breaker</label>`;
  }

  function fieldRow(label, name, value, type, immutable, dealBreaker = false, readOnly = false) {
    const present = value !== null && value !== undefined && value !== "";
    const hidden  = !immutable && !present;
    const removeBtn = (immutable || readOnly) ? "" : `<button type="button" class="btn-field-remove" aria-label="Remove ${label}">×</button>`;
    const dbToggle = readOnly ? "" : dealBreakerToggle(name, type, immutable, dealBreaker);
    const disabledAttr = readOnly ? " disabled" : "";
    const attrs = [
      `class="field-row${immutable ? "" : " field-row--opt"}"`,
      `data-field-name="${name}"`,
      hidden ? "hidden" : "",
    ].filter(Boolean).join(" ");
    const safeValue = esc(value ?? "");
    if (type === "textarea") return `<div ${attrs}>
      <label class="field-label">${label}</label>
      <textarea name="${name}" class="field-input" rows="3"${disabledAttr}>${safeValue}</textarea>${removeBtn}</div>`;
    if (type === "number") return `<div ${attrs}>
      <label class="field-label">${label}</label>
      <input type="number" name="${name}" class="field-input" value="${safeValue}" step="any"${disabledAttr}>${dbToggle}${removeBtn}</div>`;
    return `<div ${attrs}>
      <label class="field-label">${label}</label>
      <input type="text" name="${name}" class="field-input" value="${safeValue}"${disabledAttr}>${dbToggle}${removeBtn}</div>`;
  }

  function renderEditFields(cfg, readOnly = false) {
    const c = cfg.criteria || {};
    const dbSet = new Set(c.deal_breakers || []);

    const criteriaRows = CRITERIA_FIELDS.map(f => {
      const raw = c[f.name];
      // String(), not `raw ?? ""` — max_price is stored as a JS number, and a
      // truthy number defeats esc()'s `s || ""` guard (no .replace method),
      // crashing the render. Mirrors the same coercion customRows uses below.
      const value = Array.isArray(raw) ? join(raw) : String(raw ?? "");
      return fieldRow(f.label, f.name, value, f.type, f.immutable, dbSet.has(f.name), readOnly);
    }).join("\n");

    const knownNames = new Set(CRITERIA_FIELDS.map(f => f.name));
    const customRows = Object.keys(c)
      .filter(k => !knownNames.has(k) && k !== "deal_breakers")
      .map(k => {
        const raw = c[k];
        const value = Array.isArray(raw) ? join(raw) : String(raw ?? "");
        const disabledAttr = readOnly ? " disabled" : "";
        return `<div class="field-row field-row--opt field-row--custom" data-field-name="${esc(k)}">
          <label class="field-label">${esc(toLabel(k))}</label>
          <input type="text" name="${esc(k)}" class="field-input" value="${esc(value)}"${disabledAttr}>
          ${readOnly ? "" : dealBreakerToggle(k, "text", false, dbSet.has(k))}
          ${readOnly ? "" : `<button type="button" class="btn-field-remove" aria-label="Remove ${esc(toLabel(k))}">×</button>`}
        </div>`;
      }).join("\n");

    const topRows = TOP_LEVEL_FIELDS.map(f => {
      const raw = cfg[f.name];
      const value = Array.isArray(raw) ? raw.join("\n") : String(raw ?? "");
      return fieldRow(f.label, f.name, value, f.type, f.immutable, false, readOnly);
    }).join("\n");

    if (readOnly) return `${criteriaRows}\n${customRows}\n${topRows}`;

    const allOptional = [...CRITERIA_FIELDS, ...TOP_LEVEL_FIELDS].filter(f => !f.immutable);

    return `${criteriaRows}
      ${customRows}
      ${topRows}
      <input type="hidden" name="example_urls" value="${esc((cfg.example_urls || []).join("\n"))}">
      <div class="add-field-row" aria-label="Add a field">
        <span class="add-field-label">Add:</span>
        ${allOptional.map(f => `<button type="button" class="btn-add-field" data-field="${f.name}">${f.label}</button>`).join("")}
        <input type="text" class="custom-field-name" placeholder="custom field…" aria-label="Custom field name">
        <button type="button" class="btn-add-custom">+</button>
      </div>`;
  }

  function renderDescription(cfg) {
    if (!cfg.description) return "";
    return `<details class="description-disclosure">
      <summary>Original request</summary>
      <p class="card-notes">${esc(cfg.description)}</p>
    </details>`;
  }

  function renderEdit(cfg, actionsHtml = "", opts = {}) {
    const readOnly = !!opts.readOnly;
    return `<div class="edit-form${readOnly ? " edit-form--readonly" : ""}" data-name="${esc(cfg.search_name)}">
      <div class="edit-top">
        <label class="active-label">
          <input type="checkbox" name="active" ${cfg.active ? "checked" : ""}${readOnly ? " disabled" : ""}> Active
        </label>
      </div>
      ${renderDescription(cfg)}
      ${renderEditFields(cfg, readOnly)}
      ${actionsHtml}
    </div>`;
  }

  // A selected run date is "latest" when it matches the first (most recent)
  // entry in the dates list — shared by admin.js and app.js so both surfaces
  // agree on when the config panel is live-editable vs. a read-only snapshot.
  function isLatestRun(selectedDate, dates) {
    return !!selectedDate && Array.isArray(dates) && dates.length > 0 && selectedDate === dates[0];
  }

  // Identical on both surfaces: a neutral (not amber/red — those already mean
  // score-bands) notice that the config panel is showing a frozen historical
  // snapshot rather than the live, editable config.
  function renderReadOnlyBanner(date) {
    return `<div class="readonly-banner">
      <span aria-hidden="true">🔒</span>
      <span>Read-only — showing config as of ${esc(date)}.</span>
      <button type="button" class="btn-run readonly-banner-btn" id="readonly-switch-latest-btn">Switch to latest run to edit</button>
    </div>`;
  }

  function bindReadOnlyBanner(onSwitchToLatest) {
    document.getElementById("readonly-switch-latest-btn")?.addEventListener("click", onSwitchToLatest);
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

    // Only keep a deal-breaker flag for a field that actually made it into `criteria`
    // above — a checkbox left checked on a field the user just cleared (without
    // clicking the row's × remove button) must not produce a dangling deal-breaker.
    const dealBreakers = Array.from(form.querySelectorAll(".field-dealbreaker"))
      .filter(cb => !cb.closest(".field-row").hidden && cb.checked && cb.dataset.field in criteria)
      .map(cb => cb.dataset.field);
    if (dealBreakers.length) criteria.deal_breakers = dealBreakers;

    const preferredShopsRow = form.querySelector('.field-row[data-field-name="preferred_shops"]');
    const preferredShops = (!preferredShopsRow || preferredShopsRow.hidden)
      ? []
      : (preferredShopsRow.querySelector('[name="preferred_shops"]')?.value || "")
          .split(/[\s,;]+/).map(s => s.trim()).filter(Boolean);

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
      const dbCheckbox = row.querySelector(".field-dealbreaker");
      if (dbCheckbox) dbCheckbox.checked = false;
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
        if (!rawName || rawName === "deal_breakers") return;
        const existing = form.querySelector(`.field-row[data-field-name="${rawName}"]`);
        if (existing) { existing.hidden = false; existing.querySelector("input, textarea")?.focus(); syncChips(); customNameInput.value = ""; return; }
        const label = toLabel(rawName);
        const row = document.createElement("div");
        row.className = "field-row field-row--opt field-row--custom";
        row.dataset.fieldName = rawName;
        row.innerHTML = `<label class="field-label">${esc(label)}</label><input type="text" name="${esc(rawName)}" class="field-input" value="">${dealBreakerToggle(rawName, "text", false, false)}<button type="button" class="btn-field-remove" aria-label="Remove ${esc(label)}">×</button>`;
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

  window.CriteriaForm = {
    CRITERIA_FIELDS,
    TOP_LEVEL_FIELDS,
    fieldRow,
    renderEditFields,
    renderEdit,
    collectConfig,
    bindFieldControls,
    toLabel,
    isLatestRun,
    renderReadOnlyBanner,
    bindReadOnlyBanner,
  };
})();
