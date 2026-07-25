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

  function digitsOnly(s) {
    return (s || "").replace(/[^\d]/g, "");
  }

  function formatThousands(digits) {
    return digits ? Number(digits).toLocaleString("en-US") : "";
  }

  // ---------- capital input: auto-format with thousands commas ----------
  const equityInput = $("inpEquity");
  function reformatEquity() {
    const digitsBeforeCursor = digitsOnly(equityInput.value.slice(0, equityInput.selectionStart));
    equityInput.value = formatThousands(digitsOnly(equityInput.value));
    let pos = 0, seen = 0;
    while (pos < equityInput.value.length && seen < digitsBeforeCursor.length) {
      if (/\d/.test(equityInput.value[pos])) seen++;
      pos++;
    }
    equityInput.setSelectionRange(pos, pos);
  }
  equityInput.addEventListener("input", reformatEquity);
  equityInput.value = formatThousands(digitsOnly(equityInput.value));

  function parseEquity() {
    return parseFloat(digitsOnly(equityInput.value)) || 0;
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

  // ---------- version footer ----------
  async function loadVersion() {
    try {
      const v = await fetch("/api/version").then((r) => r.json());
      const parts = [`build ${v.commit}`];
      if (v.branch) parts.push(v.branch);
      if (v.environment) parts.push(v.environment);
      $("versionTag").textContent = ` · ${parts.join(" · ")}`;
    } catch (e) {
      // non-critical, leave the footer without a version tag
    }
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

  function planHtml(plan) {
    if (!plan) return "";
    const isSetup = plan.verdict === "SETUP";
    const rows = [
      ["Phase", plan.phase || "—", ""],
      ["Entry", plan.entry_low != null && plan.entry_high != null ? `${plan.entry_low}–${plan.entry_high}` : "—", ""],
      ["Lot", plan.lots != null ? `${plan.lots} lot` : "—", ""],
      ["Stop", plan.stop_loss ?? "—", ""],
      ["Loss at Stop", formatRp(plan.loss_at_stop_rp), "loss"],
      ["Target", plan.target ?? "—", ""],
      ["Profit at Target", formatRp(plan.profit_at_target_rp), "gain"],
      ["RRR", plan.rrr != null ? `1:${plan.rrr}` : "—", ""],
      ["Risk", plan.risk_pct != null ? `${plan.risk_pct}%` : "—", ""],
    ];
    return `
      <div class="plan-stats">
        <span class="verdict ${isSetup ? "setup" : "no-setup"}">${isSetup ? "Setup" : "No Setup"}</span>
        <div class="plan-grid mono">
          ${rows.map(([k, v, cls]) => `<div class="plan-cell"><span>${k}</span><b class="${cls}">${escapeHtml(String(v))}</b></div>`).join("")}
        </div>
      </div>`;
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
        ${planHtml(c.plan)}
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
    statusEl.innerHTML = '<span class="spinner"></span> Fetching data &amp; running AI...';
    $("tape").innerHTML = '<div class="empty-state processing" style="flex:1;"><span class="spinner"></span> Processing...</div>';

    const index = $("selIndex").value;
    const customTickers = $("inpCustomTickers").value
      .split(",")
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);

    const body = {
      index,
      custom_tickers: index === "Custom" ? customTickers : null,
      top_n: parseInt($("inpTopN").value, 10) || 4,
      provider: $("selProvider").value,
      model_id: $("selModel").value,
      prompt: $("selPrompt").value,
      equity: parseEquity(),
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
    btn.innerHTML = '<span class="spinner spinner-inline"></span> Analyzing...';
    $("manualResultWrap").style.display = "block";
    $("manualResult").innerHTML = '<div class="empty-state processing"><span class="spinner"></span> Analyzing chart...</div>';

    const form = new FormData();
    form.append("file", file);
    form.append("provider", $("selProviderM").value);
    form.append("model_id", $("selModelM").value);
    form.append("prompt", $("selPromptM").value);
    form.append("equity", parseEquity());
    form.append("ticker", $("inpTicker").value.trim().toUpperCase());

    try {
      const res = await fetch("/api/analyze", { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || res.statusText);
      }
      const data = await res.json();
      $("manualResultWrap").style.display = "block";
      $("manualResult").innerHTML = planHtml(data.plan) + data.analysis_html;
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
        <td>
          <button class="btn-link" data-action="update-trade">Save</button>
          <button class="btn-link btn-danger" data-action="delete-entry">Delete</button>
        </td>
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
    const saveBtn = e.target.closest('button[data-action="update-trade"]');
    const deleteBtn = e.target.closest('button[data-action="delete-entry"]');

    if (saveBtn) {
      const row = saveBtn.closest("tr");
      const id = row.dataset.id;
      const payload = {
        status: row.querySelector(".f-status").value,
        entry_price: parseFloat(row.querySelector(".f-entry").value) || null,
        exit_price: parseFloat(row.querySelector(".f-exit").value) || null,
        qty: parseInt(row.querySelector(".f-qty").value, 10) || null,
        notes: "",
      };
      saveBtn.textContent = "...";
      try {
        await fetch(`/api/journal/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        state.journal = await fetch("/api/journal").then((r) => r.json());
        renderJournal();
      } catch (err) {
        saveBtn.textContent = "Failed";
      }
    }

    if (deleteBtn) {
      const row = deleteBtn.closest("tr");
      const id = row.dataset.id;
      const ticker = row.querySelector(".mono").textContent;
      if (!confirm(`Delete journal entry for ${ticker}? This can't be undone from the UI.`)) return;
      deleteBtn.textContent = "...";
      deleteBtn.disabled = true;
      try {
        const res = await fetch(`/api/journal/${id}`, { method: "DELETE" });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || res.statusText);
        }
        state.journal = await fetch("/api/journal").then((r) => r.json());
        renderJournal();
      } catch (err) {
        deleteBtn.textContent = "Failed";
        deleteBtn.disabled = false;
        alert("Delete failed: " + err.message);
      }
    }
  });

  init();
  loadVersion();
})();
