(() => {
  const searchList = document.getElementById("search-list");
  const toolbar = document.getElementById("toolbar");
  const dateSelect = document.getElementById("date-select");
  const resultsPanel = document.getElementById("results-panel");

  let activeSearch = null;
  let isAdmin = false;

  async function api(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }

  function siteName(url) {
    try {
      const locales = new Set(["us", "uk", "eu", "au", "ca"]);
      const skip = new Set(["www", "shop", "store", "m", "en", "co"]);
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

  function scoreClass(s) {
    if (s >= 7) return "green";
    if (s >= 4) return "amber";
    return "red";
  }

  function tag(text, cls) {
    return `<span class="tag ${cls}">${text}</span>`;
  }

  const _PHRASES = ["Perfect match", "Wrong material", "Too expensive", "Wrong style", "Doesn't ship to me", "Out of stock"];

  function renderCard(m, feedbackMap) {
    const sc = scoreClass(m.score);
    const newTag = m.is_new ? tag("NEW", "tag-new") : "";
    const price = m.price != null ? `<span class="card-price">${m.price}</span>` : "";
    const criteria = [
      ...(m.matched || []).map(t => tag(t, "tag tag-match")),
      ...(m.unmatched || []).map(t => tag(t, "tag tag-miss")),
    ].join("");
    const notes = m.notes ? `<p class="card-notes">${m.notes}</p>` : "";
    const site = siteName(m.url);
    const titleInner = site && m.title
      ? `<span class="card-site">${site}</span><span class="card-sep"> | </span>${m.title}`
      : (m.title || "(no title)");
    const titleText = `<a class="card-title-link" href="${m.url}" target="_blank" rel="noopener">${titleInner}</a>`;
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
          <div class="card-title-row">
            ${titleText}
            ${newTag}
          </div>
          <div class="card-meta">
            ${price}
          </div>
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
      if (!prev || (item.title || "").length > (prev.title || "").length) {
        seen.set(item.url, item);
      }
    }
    return [...seen.values()];
  }

  function renderResults(run) {
    if (run.no_match || (!run.matches?.length && !run.partial_matches?.length)) {
      resultsPanel.innerHTML = `<p class="empty-state">No matches found for this run.</p>`;
      return;
    }
    const fb = run.feedback || {};
    const matches = dedupeByUrl(run.matches || []);
    const matchUrls = new Set(matches.map(m => m.url));
    const partials = dedupeByUrl((run.partial_matches || []).filter(m => !matchUrls.has(m.url)));
    let html = `<p class="run-meta">${run.total_candidates ?? "?"} candidates evaluated</p>`;
    if (isAdmin) {
      const overallFb = fb['_overall_'] || '';
      html += `<div class="save-all-row">
        <textarea id="overall-feedback" class="overall-feedback-text" placeholder="Overall run notes…" rows="2" maxlength="512">${overallFb}</textarea>
        <div class="save-all-controls">
          <button type="button" id="save-all-btn" class="save-all-btn">Save all feedback</button>
          <span id="save-all-msg" class="feedback-msg"></span>
        </div>
      </div>`;
    }
    if (matches.length) {
      html += `<div class="results-section">
        <p class="section-heading">Matches (${matches.length})</p>
        <div class="cards">${matches.map(m => renderCard(m, fb)).join("")}</div>
      </div>`;
    }
    if (partials.length) {
      html += `<div class="results-section">
        <p class="section-heading">Partial matches (${partials.length})</p>
        <div class="cards">${partials.map(m => renderCard(m, fb)).join("")}</div>
      </div>`;
    }
    resultsPanel.innerHTML = html;
  }

  function bindFeedback(searchName, runDate) {
    resultsPanel.querySelectorAll(".feedback-row").forEach(row => {
      const textarea = row.querySelector(".feedback-text");
      const charcount = row.querySelector(".feedback-charcount");
      const updateCount = () => { charcount.textContent = `${textarea.value.length}/256`; };
      textarea.addEventListener("input", updateCount);
      row.querySelectorAll(".phrase-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          const phrase = btn.dataset.phrase;
          textarea.value = textarea.value ? `${textarea.value}; ${phrase}` : phrase;
          updateCount();
        });
      });
    });

    const saveAllBtn = document.getElementById("save-all-btn");
    const saveAllMsg = document.getElementById("save-all-msg");
    const overallTextarea = document.getElementById("overall-feedback");
    if (saveAllBtn) {
      saveAllBtn.addEventListener("click", async () => {
        const rows = [...resultsPanel.querySelectorAll(".feedback-row")];
        const items = rows
          .map(r => ({ url: r.dataset.url, text: r.querySelector(".feedback-text").value.trim() }))
          .filter(i => i.text);
        const overallText = overallTextarea?.value.trim();
        if (overallText) items.push({ url: '_overall_', text: overallText });
        if (!items.length) {
          saveAllMsg.textContent = "Nothing to save";
          setTimeout(() => { saveAllMsg.textContent = ""; }, 2000);
          return;
        }
        saveAllBtn.disabled = true;
        saveAllMsg.textContent = `Saving ${items.length}…`;
        try {
          await fetch(
            `/api/feedback/${encodeURIComponent(searchName)}/${encodeURIComponent(runDate)}/batch`,
            { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items }) }
          ).then(r => { if (!r.ok) throw new Error(r.statusText); });
          saveAllMsg.textContent = "Saved";
        } catch {
          saveAllMsg.textContent = "Failed";
        }
        saveAllBtn.disabled = false;
        setTimeout(() => { saveAllMsg.textContent = ""; }, 3000);
      });
    }
  }

  async function loadRun(searchName, runDate) {
    resultsPanel.innerHTML = `<p class="loading">Loading…</p>`;
    try {
      const [run, adminResult] = await Promise.all([
        api(`/api/results/${encodeURIComponent(searchName)}/${encodeURIComponent(runDate)}`),
        api("/api/admin/me").catch(() => ({ admin: false })),
      ]);
      isAdmin = adminResult.admin;
      renderResults(run);
      bindFeedback(searchName, runDate);
    } catch (e) {
      resultsPanel.innerHTML = `<p class="empty-state">Failed to load results: ${e.message}</p>`;
    }
  }

  async function selectSearch(name) {
    if (activeSearch === name) return;
    activeSearch = name;
    history.pushState({}, "", "/" + encodeURIComponent(name));

    document.querySelectorAll(".search-list li").forEach(el => {
      el.classList.toggle("active", el.dataset.name === name);
    });

    toolbar.hidden = true;
    resultsPanel.innerHTML = `<p class="loading">Loading dates…</p>`;

    try {
      const dates = await api(`/api/results/${encodeURIComponent(name)}`);
      dateSelect.innerHTML = dates.map(d => `<option value="${d}">${d}</option>`).join("");
      toolbar.hidden = false;
      await loadRun(name, dates[0]);
    } catch {
      resultsPanel.innerHTML = `<p class="empty-state">No runs found for this search.</p>`;
    }
  }

  dateSelect.addEventListener("change", () => {
    if (activeSearch) loadRun(activeSearch, dateSelect.value);
  });

  async function init() {
    try {
      const searches = await api("/api/searches");
      searchList.innerHTML = searches.map(s =>
        `<li role="option" tabindex="0" data-name="${s.name}" class="${s.active ? "" : "inactive-search"}">
          <span>${s.name.replace(/_/g, " ")}</span>
          <button class="copy-link-btn" title="Copy link" aria-label="Copy link to ${s.name}">⎘</button>
        </li>`
      ).join("");

      searchList.querySelectorAll("li").forEach(el => {
        el.addEventListener("click", () => selectSearch(el.dataset.name));
        el.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") selectSearch(el.dataset.name); });
      });

      searchList.querySelectorAll(".copy-link-btn").forEach(btn => {
        btn.addEventListener("click", e => {
          e.stopPropagation();
          const name = btn.closest("li").dataset.name;
          navigator.clipboard.writeText(`${location.origin}/${name}`).then(() => {
            btn.textContent = "✓";
            setTimeout(() => { btn.textContent = "⎘"; }, 1500);
          });
        });
      });

      const fromPath = decodeURIComponent(window.location.pathname.slice(1));
      const initial = searches.find(s => s.name === fromPath) ? fromPath : searches[0]?.name;
      if (initial) selectSearch(initial);
    } catch {
      searchList.innerHTML = `<li style="padding:12px 16px;color:var(--text-muted)">Failed to load searches</li>`;
    }
  }

  init();
})();
