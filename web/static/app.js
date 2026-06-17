(() => {
  const searchList = document.getElementById("search-list");
  const toolbar = document.getElementById("toolbar");
  const dateSelect = document.getElementById("date-select");
  const resultsPanel = document.getElementById("results-panel");

  let activeSearch = null;

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
    const price = m.price ? `<span class="card-price">€${m.price}</span>` : "";
    const criteria = [
      ...(m.matched || []).map(t => tag(t, "tag tag-match")),
      ...(m.unmatched || []).map(t => tag(t, "tag tag-miss")),
    ].join("");
    const notes = m.notes ? `<p class="card-notes">${m.notes}</p>` : "";
    const site = siteName(m.url);
    const titleText = site && m.title
      ? `<span class="card-site">${site}</span><span class="card-sep"> | </span>${m.title}`
      : (m.title || "(no title)");
    const existingFeedback = feedbackMap?.[m.url] || "";
    const phrases = _PHRASES.map(p => `<button type="button" class="phrase-btn" data-phrase="${p}">${p}</button>`).join("");
    return `
      <div class="card">
        <div class="score-badge ${sc}">${Math.round(m.score)}</div>
        <div class="card-body">
          <div class="card-title-row">
            <span class="card-title">${titleText}</span>
            ${newTag}
          </div>
          <div class="card-meta">
            ${price}
          </div>
          <a class="card-url" href="${m.url}" target="_blank" rel="noopener">${m.url}</a>
          ${criteria ? `<div class="criteria-row">${criteria}</div>` : ""}
          ${notes}
          <div class="feedback-row" data-url="${m.url}">
            <div class="feedback-phrases">${phrases}</div>
            <div class="feedback-input-row">
              <textarea class="feedback-text" placeholder="Add feedback…" rows="2">${existingFeedback}</textarea>
              <button type="button" class="feedback-submit">Save</button>
            </div>
            <span class="feedback-msg"></span>
          </div>
        </div>
      </div>`;
  }

  function renderResults(run) {
    if (run.no_match || (!run.matches?.length && !run.partial_matches?.length)) {
      resultsPanel.innerHTML = `<p class="empty-state">No matches found for this run.</p>`;
      return;
    }
    const fb = run.feedback || {};
    let html = `<p class="run-meta">${run.total_candidates ?? "?"} candidates evaluated</p>`;
    if (run.matches?.length) {
      html += `<div class="results-section">
        <p class="section-heading">Matches (${run.matches.length})</p>
        <div class="cards">${run.matches.map(m => renderCard(m, fb)).join("")}</div>
      </div>`;
    }
    if (run.partial_matches?.length) {
      html += `<div class="results-section">
        <p class="section-heading">Partial matches (${run.partial_matches.length})</p>
        <div class="cards">${run.partial_matches.map(m => renderCard(m, fb)).join("")}</div>
      </div>`;
    }
    resultsPanel.innerHTML = html;
  }

  function bindFeedback(searchName, runDate) {
    resultsPanel.querySelectorAll(".feedback-row").forEach(row => {
      const url = row.dataset.url;
      const textarea = row.querySelector(".feedback-text");
      const msgEl = row.querySelector(".feedback-msg");

      row.querySelectorAll(".phrase-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          const phrase = btn.dataset.phrase;
          textarea.value = textarea.value ? `${textarea.value}; ${phrase}` : phrase;
        });
      });

      row.querySelector(".feedback-submit").addEventListener("click", async () => {
        msgEl.textContent = "Saving…";
        try {
          const r = await fetch(
            `/api/feedback/${encodeURIComponent(searchName)}/${encodeURIComponent(runDate)}`,
            { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url, text: textarea.value }) }
          );
          if (!r.ok) throw new Error(r.statusText);
          msgEl.textContent = "Saved";
          setTimeout(() => { msgEl.textContent = ""; }, 2000);
        } catch {
          msgEl.textContent = "Failed";
        }
      });
    });
  }

  async function loadRun(searchName, runDate) {
    resultsPanel.innerHTML = `<p class="loading">Loading…</p>`;
    try {
      const run = await api(`/api/results/${encodeURIComponent(searchName)}/${encodeURIComponent(runDate)}`);
      renderResults(run);
      bindFeedback(searchName, runDate);
    } catch (e) {
      resultsPanel.innerHTML = `<p class="empty-state">Failed to load results: ${e.message}</p>`;
    }
  }

  async function selectSearch(name) {
    if (activeSearch === name) return;
    activeSearch = name;

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
        `<li role="option" data-name="${s.name}" class="${s.active ? "" : "inactive-search"}">${s.name.replace(/_/g, " ")}</li>`
      ).join("");

      searchList.querySelectorAll("li").forEach(el => {
        el.addEventListener("click", () => selectSearch(el.dataset.name));
      });

      if (searches.length) selectSearch(searches[0].name);
    } catch {
      searchList.innerHTML = `<li style="padding:12px 16px;color:var(--text-muted)">Failed to load searches</li>`;
    }
  }

  init();
})();
