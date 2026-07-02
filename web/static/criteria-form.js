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

  function fieldRow(label, name, value, type, immutable) {
    const present = value !== null && value !== undefined && value !== "";
    const hidden  = !immutable && !present;
    const removeBtn = immutable ? "" : `<button type="button" class="btn-field-remove" aria-label="Remove ${label}">×</button>`;
    const attrs = [
      `class="field-row${immutable ? "" : " field-row--opt"}"`,
      `data-field-name="${name}"`,
      hidden ? "hidden" : "",
    ].filter(Boolean).join(" ");
    const safeValue = esc(value ?? "");
    if (type === "textarea") return `<div ${attrs}>
      <label class="field-label">${label}</label>
      <textarea name="${name}" class="field-input" rows="3">${safeValue}</textarea>${removeBtn}</div>`;
    if (type === "number") return `<div ${attrs}>
      <label class="field-label">${label}</label>
      <input type="number" name="${name}" class="field-input" value="${safeValue}" step="any">${removeBtn}</div>`;
    return `<div ${attrs}>
      <label class="field-label">${label}</label>
      <input type="text" name="${name}" class="field-input" value="${safeValue}">${removeBtn}</div>`;
  }

  function renderEditFields(cfg) {
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

  function renderEdit(cfg, actionsHtml = "") {
    return `<div class="edit-form" data-name="${esc(cfg.search_name)}">
      <div class="edit-top">
        <label class="active-label">
          <input type="checkbox" name="active" ${cfg.active ? "checked" : ""}> Active
        </label>
      </div>
      ${renderEditFields(cfg)}
      ${actionsHtml}
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

  window.CriteriaForm = {
    CRITERIA_FIELDS,
    TOP_LEVEL_FIELDS,
    fieldRow,
    renderEditFields,
    renderEdit,
    collectConfig,
    bindFieldControls,
    toLabel,
  };
})();
