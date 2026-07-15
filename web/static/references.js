(() => {
  function esc(s) {
    return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function defaultSiteName(url) {
    try { return new URL(url).hostname; } catch { return url.slice(0, 40); }
  }

  function safeHref(url) {
    try { const u = new URL(url); return (u.protocol === "https:" || u.protocol === "http:") ? url : "#"; }
    catch { return "#"; }
  }

  function shortUrl(url, max = 60) {
    const stripped = url.replace(/^https?:\/\/(www\.)?/, "");
    return stripped.length > max ? stripped.slice(0, max - 1) + "…" : stripped;
  }

  // Shows the user's reference products ("products like this" URLs) in the
  // results view. Prefers run.example_urls — the LIVE config, merged in by the
  // results endpoint — over the run's frozen config_snapshot, so a reference
  // added after the run still shows up.
  function renderNote(run) {
    const urls = run.example_urls ?? run.config_snapshot?.example_urls ?? [];
    if (!urls.length) return "";
    const links = urls
      .map(u => `<a href="${esc(safeHref(u))}" target="_blank" rel="noopener" class="ref-note-link" title="${esc(u)}">${esc(shortUrl(u))}</a>`)
      .join(", ");
    return `<p class="run-reference-note"><span class="ref-note-label">Products like this (your references):</span> ${links}</p>`;
  }

  // withSaveButton: admin saves references independently of the rest of the
  // config; app.js folds example_urls into the single edit-form Save button
  // instead, so it omits the button and passes withSaveButton: false.
  function renderReferences(opts = {}) {
    const withSaveButton = opts.withSaveButton !== false;
    return `<div class="references-card">
      <div class="references-header">
        <span class="references-title">Reference products</span>
        <span class="ref-count"></span>
        <span class="ref-autosave-msg save-msg"></span>
      </div>
      <p class="references-desc">Add up to 3 products you already love — the AI uses these to calibrate what a great match looks like for you.</p>
      <div class="ref-chips"></div>
      <div class="ref-input-row">
        <input type="url" class="field-input ref-url-input" placeholder="Paste a product URL…">
        <button type="button" class="btn-ref-add">Add</button>
      </div>
      ${withSaveButton ? `<div class="ref-action-row">
        <button type="button" class="btn-ref-save btn-primary">Save references</button>
        <span class="ref-save-msg save-msg"></span>
      </div>` : ""}
    </div>`;
  }

  // hiddenInput: the `example_urls` hidden field whose newline-joined value
  // this card keeps in sync as chips are added/removed.
  // opts.siteName: url -> display label
  // opts.onSave: async (urls) => void — only wired up if a .btn-ref-save exists in the card
  // opts.onChange: async (urls) => void — persists immediately on every add/remove,
  //   so a reference is never lost because the user forgot a separate Save click
  function bindReferences(card, hiddenInput, opts = {}) {
    const siteName = opts.siteName || defaultSiteName;
    let urls = hiddenInput ? hiddenInput.value.split("\n").filter(Boolean) : [];

    function syncHidden() {
      if (hiddenInput) hiddenInput.value = urls.join("\n");
    }

    const autosaveMsg = card.querySelector(".ref-autosave-msg");
    const setAutoMsg = (text, cls) => {
      if (autosaveMsg) { autosaveMsg.textContent = text; autosaveMsg.className = `ref-autosave-msg save-msg ${cls}`; }
    };
    // One in-flight save at a time, always re-sending the LATEST state after —
    // parallel PUTs could arrive out of order and persist a stale snapshot.
    let saving = false, dirty = false, clearSeq = 0;
    async function persist() {
      if (!opts.onChange) return;
      dirty = true;
      if (saving) return;
      saving = true;
      while (dirty) {
        dirty = false;
        clearSeq++;
        setAutoMsg("Saving…", "");
        try {
          await opts.onChange(urls.slice());
          if (!dirty) {
            setAutoMsg("Saved.", "ok");
            const seq = clearSeq;
            setTimeout(() => { if (seq === clearSeq) setAutoMsg("", ""); }, 2000);
          }
        } catch (e) {
          if (!dirty) setAutoMsg(`Not saved: ${e.message} — will retry on next change`, "err");
        }
      }
      saving = false;
    }

    function renderChips() {
      const chipsEl = card.querySelector(".ref-chips");
      const countEl = card.querySelector(".ref-count");
      const inputRow = card.querySelector(".ref-input-row");
      chipsEl.innerHTML = urls.map(u => `
        <div class="ref-chip" data-url="${esc(u)}">
          <span class="ref-chip-label">${esc(siteName(u))}</span>
          <button type="button" class="ref-chip-remove" aria-label="Remove">×</button>
        </div>`).join("");
      countEl.textContent = `${urls.length} / 3`;
      if (inputRow) inputRow.hidden = urls.length >= 3;
      card.querySelectorAll(".ref-chip-remove").forEach(btn => {
        btn.addEventListener("click", () => {
          urls = urls.filter(u => u !== btn.closest(".ref-chip").dataset.url);
          renderChips();
          syncHidden();
          persist();
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
      if (!urls.includes(val)) { urls.push(val); renderChips(); syncHidden(); persist(); }
      urlInput.value = "";
    }

    addBtn.addEventListener("click", addUrl);
    urlInput.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); addUrl(); } });

    const saveBtn = card.querySelector(".btn-ref-save");
    if (saveBtn && opts.onSave) {
      const saveMsg = card.querySelector(".ref-save-msg");
      const setMsg = (t, cls) => { saveMsg.textContent = t; saveMsg.className = `ref-save-msg save-msg ${cls}`; };
      saveBtn.addEventListener("click", async () => {
        saveBtn.disabled = true;
        setMsg("Saving…", "");
        try {
          await opts.onSave(urls);
          setMsg("Saved.", "ok");
          setTimeout(() => setMsg("", ""), 2500);
        } catch (e) { setMsg(e.message, "err"); }
        saveBtn.disabled = false;
      });
    }
  }

  window.References = { renderReferences, bindReferences, renderNote };
})();
