(function () {
  "use strict";

  const state = { models: {}, indices: { names: [], tickers: {} }, prompts: [], journal: [], maxScore: 8 };

  const $ = (id) => document.getElementById(id);

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function formatRp(n) {
    if (n == null || isNaN(n)) return "—";
    return "Rp " + Number(n).toLocaleString("id-ID");
  }

  // ---------- theme ----------
  const root = document.documentElement;
  $("themeToggle").addEventListener("click", function () {
    const isDark =
      root.getAttribute("data-theme") === "dark" ||
      (!root.getAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
    root.setAttribute("data-theme", isDark ? "light" : "dark");
    $("themeToggle").textContent = isDark ? "Dark Mode" : "Light Mode";
  });

  // ---------- tabs ----------
  document.querySelectorAll("nav.tabs button").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("nav.tabs button").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll("section.view").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      $("view-" + b.dataset.view).classList.add("active");
    });
  });

  // ---------- provider/model dependent selects ----------
  function populateProviderModel(providerSelId, modelSelId) {
    const provSel = $(providerSelId);
    const modelSel = $(modelSelId);
    provSel.innerHTML = Object.keys(state.models)
      .map((p) => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`)
      .join("");
    function refreshModels() {
      const models = state.models[provSel.value] || {};
      modelSel.innerHTML = Object.entries(models)
        .map(([label, id]) => `<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`)
        .join("");
    }
    provSel.addEventListener("change", refreshModels);
    refreshModels();
  }

  // ---------- init ----------
  async function init() {
    try {
      const [models, indices, prompts, journal] = await Promise.all([
        fetch("/api/models").then((r) => r.json()),
        fetch("/api/indices").then((r) => r.json()),
        fetch("/api/prompts").then((r) => r.json()),
        fetch("/api/journal").then((r) => r.json()),
      ]);
      state.models = models;
      state.indices = indices;
      state.prompts = prompts.names;
      state.journal = journal;

      $("apiStatus").innerHTML = '<span class="blip"></span>connected to backend';

      populateProviderModel("selProvider", "selModel");
      populateProviderModel("selProviderM", "selModelM");

      $("selIndex").innerHTML = indices.names
        .map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}${n !== "Custom" ? " (" + indices.tickers[n].length + ")" : ""}</option>`)
        .join("");
      $("selIndex").addEventListener("change", () => {
        $("customTickersField").style.display = $("selIndex").value === "Custom" ? "block" : "none";
      });

      const promptOptions = state.prompts.map((p) => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join("");
      $("selPrompt").innerHTML = promptOptions;
      $("selPromptM").innerHTML = promptOptions;

      renderJournal();
    } catch (e) {
      $("apiStatus").className = "live-pill err";
      $("apiStatus").innerHTML = '<span class="blip"></span>backend not connected';
      console.error(e);
    }
  }

  // ---------- screener ----------
  function phaseClass(score) {
    if (score >= state.maxScore * 0.6) return "strong";
    if (score >= state.maxScore * 0.35) return "mid";
    return "weak";
  }

  function ticketHtml(c, idx) {
    return `
      <article class="ticket" data-idx="${idx}">
        <div class="thead">
          <div>
            <div class="ticker">${escapeHtml(c.ticker)}</div>
            <div class="price mono">${c.last_close}</div>
          </div>
          <span class="phase ${phaseClass(c.score)}">${c.score}/${state.maxScore}</span>
        </div>
        <img class="chart" src="data:image/png;base64,${c.chart_b64}" alt="Chart ${escapeHtml(c.ticker)}">
        <div class="signals">
          ${c.signals.map((s) => `<span class="tag">${escapeHtml(s)}</span>`).join("")}
        </div>
        <div class="excerpt rendered-md">${c.analysis_html}</div>
        <div class="foot">
          <button class="btn-link" data-action="expand">Read more &rarr;</button>
          <button class="btn-save" data-action="save">+ Journal</button>
        </div>
      </article>`;
  }

  async function runScreen() {
    const btn = $("btnRunScreen");
    const statusEl = $("screenStatus");
    btn.disabled = true;
    statusEl.textContent = "Fetching data & running AI...";
    $("tape").innerHTML = '<div class="empty-state" style="flex:1;">Processing...</div>';

    const index = $("selIndex").value;
    const customTickers = $("inpCustomTickers").value
      .split(",")
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);

    const body = {
      index,
      custom_tickers: index === "Custom" ? customTickers : null,
      top_n: parseInt($("inpTopN").value, 10) || 8,
      provider: $("selProvider").value,
      model_id: $("selModel").value,
      prompt: $("selPrompt").value,
      equity: parseFloat($("inpEquity").value) || 0,
    };

    try {
      const res = await fetch("/api/screen", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || res.statusText);
      }
      const data = await res.json();
      state.lastScreen = data.candidates;
      state.maxScore = data.max_score || state.maxScore;

      statusEl.textContent = `${data.fetched}/${data.requested} stocks fetched, ${data.candidates.length} candidates passed the filter.`;

      if (!data.candidates.length) {
        $("tape").innerHTML = '<div class="empty-state" style="flex:1;">No candidates passed the quantitative filter today.</div>';
      } else {
        $("tape").innerHTML = data.candidates.map(ticketHtml).join("");
      }
    } catch (e) {
      statusEl.textContent = "Failed: " + e.message;
      $("tape").innerHTML = `<div class="empty-state" style="flex:1;">Screening failed: ${escapeHtml(e.message)}</div>`;
    } finally {
      btn.disabled = false;
    }
  }

  $("btnRunScreen").addEventListener("click", runScreen);

  $("tape").addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    const card = btn.closest(".ticket");
    const idx = parseInt(card.dataset.idx, 10);
    const cand = state.lastScreen[idx];

    if (btn.dataset.action === "expand") {
      const excerpt = card.querySelector(".excerpt");
      excerpt.classList.toggle("expanded");
      btn.textContent = excerpt.classList.contains("expanded") ? "Collapse ←" : "Read more →";
    }

    if (btn.dataset.action === "save") {
      btn.disabled = true;
      btn.textContent = "Saving...";
      try {
        await fetch("/api/journal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ticker: cand.ticker,
            model: `${$("selProvider").value}/${$("selModel").value}`,
            strategy: $("selPrompt").value,
            analysis: cand.analysis,
          }),
        });
        state.journal = await fetch("/api/journal").then((r) => r.json());
        renderJournal();
        btn.textContent = "Saved ✓";
      } catch (err) {
        btn.textContent = "Failed";
        btn.disabled = false;
      }
    }
  });

  // ---------- manual analysis ----------
  $("fileChart").addEventListener("change", () => {
    const file = $("fileChart").files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    $("preview").src = url;
    $("preview").style.display = "block";
  });

  $("btnAnalyzeManual").addEventListener("click", async () => {
    const file = $("fileChart").files[0];
    if (!file) {
      alert("Please upload a chart screenshot first.");
      return;
    }
    const btn = $("btnAnalyzeManual");
    btn.disabled = true;
    btn.textContent = "Analyzing...";

    const form = new FormData();
    form.append("file", file);
    form.append("provider", $("selProviderM").value);
    form.append("model_id", $("selModelM").value);
    form.append("prompt", $("selPromptM").value);
    form.append("equity", parseFloat($("inpEquity").value) || 0);
    form.append("ticker", $("inpTicker").value.trim().toUpperCase());

    try {
      const res = await fetch("/api/analyze", { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || res.statusText);
      }
      const data = await res.json();
      $("manualResultWrap").style.display = "block";
      $("manualResult").innerHTML = data.analysis_html;
      state.journal = await fetch("/api/journal").then((r) => r.json());
      renderJournal();
    } catch (e) {
      $("manualResultWrap").style.display = "block";
      $("manualResult").textContent = "Analysis failed: " + e.message;
    } finally {
      btn.disabled = false;
      btn.textContent = "🚀 Run Analysis";
    }
  });

  // ---------- journal ----------
  function journalRow(entry) {
    const trade = entry.trade || { status: "Planned", entry_price: null, exit_price: null, qty: null, notes: "", pnl: null };
    return `
      <tr data-id="${entry.id}">
        <td class="mono">${escapeHtml(entry.date || "")}</td>
        <td class="mono">${escapeHtml(entry.ticker || "—")}</td>
        <td>${escapeHtml(entry.strategy || "")}</td>
        <td>
          <select class="f-status">
            ${["Planned", "Open", "Closed", "Skipped"].map((s) => `<option value="${s}" ${s === trade.status ? "selected" : ""}>${s}</option>`).join("")}
          </select>
        </td>
        <td class="num"><input class="f-entry mono" type="number" value="${trade.entry_price ?? ""}"></td>
        <td class="num"><input class="f-exit mono" type="number" value="${trade.exit_price ?? ""}"></td>
        <td class="num"><input class="f-qty mono" type="number" value="${trade.qty ?? ""}" style="width:60px;"></td>
        <td class="num mono ${trade.pnl > 0 ? "pnl up" : trade.pnl < 0 ? "pnl down" : ""}">${trade.pnl != null ? formatRp(trade.pnl) : "—"}</td>
        <td><button class="btn-link" data-action="update-trade">Save</button></td>
      </tr>`;
  }

  function renderJournal() {
    $("journalCount").textContent = state.journal.length ? state.journal.length : "";
    const tbody = $("journalBody");
    if (!state.journal.length) {
      tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--ink-faint);font-style:italic;">No journal entries yet.</td></tr>';
      return;
    }
    tbody.innerHTML = state.journal
      .map(journalRow)
      .reverse()
      .join("");
  }

  $("journalBody").addEventListener("click", async (e) => {
    const btn = e.target.closest('button[data-action="update-trade"]');
    if (!btn) return;
    const row = btn.closest("tr");
    const id = row.dataset.id;
    const payload = {
      status: row.querySelector(".f-status").value,
      entry_price: parseFloat(row.querySelector(".f-entry").value) || null,
      exit_price: parseFloat(row.querySelector(".f-exit").value) || null,
      qty: parseInt(row.querySelector(".f-qty").value, 10) || null,
      notes: "",
    };
    btn.textContent = "...";
    try {
      await fetch(`/api/journal/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.journal = await fetch("/api/journal").then((r) => r.json());
      renderJournal();
    } catch (err) {
      btn.textContent = "Failed";
    }
  });

  init();
})();
