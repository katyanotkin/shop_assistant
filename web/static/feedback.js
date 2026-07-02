(() => {
  const _PHRASES = [
    "Perfect match",
    "Wrong material",
    "Too expensive",
    "Wrong style",
    "Doesn't ship to me",
    "Out of stock",
  ];

  function esc(s) {
    return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function renderFeedbackBlock(url, feedbackMap) {
    const existing = (feedbackMap && feedbackMap[url]) || "";
    const phrases = _PHRASES
      .map(p => `<button type="button" class="phrase-btn" data-phrase="${esc(p)}">${esc(p)}</button>`)
      .join("");
    return `
      <div class="feedback-row" data-url="${esc(url)}">
        <div class="feedback-phrases">${phrases}</div>
        <div class="feedback-input-row">
          <textarea class="feedback-text" rows="2" maxlength="256" placeholder="Add feedback…">${esc(existing)}</textarea>
        </div>
        <span class="feedback-charcount"></span>
      </div>`;
  }

  const _OVERALL_KEY = "_overall_";

  function renderSaveAllRow(feedbackMap) {
    const existing = (feedbackMap && feedbackMap[_OVERALL_KEY]) || "";
    return `<div class="save-all-row">
      <textarea class="overall-feedback-text" rows="2" maxlength="512" placeholder="Overall run notes…">${esc(existing)}</textarea>
      <div class="save-all-controls">
        <button type="button" class="save-all-btn">Save all feedback</button>
        <span class="feedback-msg"></span>
      </div>
    </div>`;
  }

  function bindFeedback(container, saveBatch) {
    container.querySelectorAll(".feedback-row").forEach(row => {
      const textarea  = row.querySelector(".feedback-text");
      const charcount = row.querySelector(".feedback-charcount");
      if (!textarea || !charcount) return;

      const updateCount = () => { charcount.textContent = `${textarea.value.length}/256`; };
      updateCount();
      textarea.addEventListener("input", updateCount);

      row.querySelectorAll(".phrase-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          const phrase = btn.dataset.phrase;
          textarea.value = (textarea.value ? `${textarea.value}; ${phrase}` : phrase).slice(0, 256);
          updateCount();
        });
      });
    });

    const saveBtn = container.querySelector(".save-all-btn");
    if (!saveBtn) return;
    const msgEl = container.querySelector(".save-all-row .feedback-msg");
    const setMsg = text => { if (msgEl) msgEl.textContent = text; };

    const overallTextarea = container.querySelector(".overall-feedback-text");

    saveBtn.addEventListener("click", async () => {
      const items = [];
      container.querySelectorAll(".feedback-row").forEach(row => {
        const text = row.querySelector(".feedback-text")?.value.trim();
        if (text) items.push({ url: row.dataset.url, text });
      });
      const overallText = overallTextarea?.value.trim();
      if (overallText) items.push({ url: _OVERALL_KEY, text: overallText });
      if (!items.length) {
        setMsg("Nothing to save");
        setTimeout(() => setMsg(""), 2000);
        return;
      }
      saveBtn.disabled = true;
      setMsg("Saving…");
      try {
        await saveBatch(items);
        setMsg("Saved");
        setTimeout(() => setMsg(""), 2000);
      } catch (e) {
        setMsg(`Failed: ${e.message}`);
      } finally {
        saveBtn.disabled = false;
      }
    });
  }

  window.Feedback = { renderFeedbackBlock, renderSaveAllRow, bindFeedback };
})();
