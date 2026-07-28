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

  // ---------- thousands-comma input formatting (reused for any Rp field) ----------
  function attachThousandsFormatter(inputEl) {
    function reformat() {
      const digitsBeforeCursor = digitsOnly(inputEl.value.slice(0, inputEl.selectionStart));
      inputEl.value = formatThousands(digitsOnly(inputEl.value));
      let pos = 0, seen = 0;
      while (pos < inputEl.value.length && seen < digitsBeforeCursor.length) {
        if (/\d/.test(inputEl.value[pos])) seen++;
        pos++;
      }
      inputEl.setSelectionRange(pos, pos);
    }
    inputEl.addEventListener("input", reformat);
    inputEl.value = formatThousands(digitsOnly(inputEl.value));
    return () => parseFloat(digitsOnly(inputEl.value)) || 0;
  }

  const parseEquity = attachThousandsFormatter($("inpEquity"));
  const parsePositionAvgPrice = attachThousandsFormatter($("inpPositionAvgPrice"));
  const parseAutoEquity = attachThousandsFormatter($("autoEquity"));

  // ---------- refresh ----------
  $("btnRefreshApp").addEventListener("click", function () {
    location.reload();
  });

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
      b.scrollIntoView({ block: "nearest", inline: "nearest" });
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

  // ---------- automation ----------
  const AUTO_HOURS = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16];
  const AUTO_DAYS = [0, 1, 2, 3, 4]; // Monday-Friday
  const AUTO_DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
  const AUTOMATION_DEFAULTS = {
    enabled: false, hours_wib: [], days_wib: [], index_name: "LQ45", custom_tickers: [],
    strategies: [], provider: "Claude", model_id: "claude-sonnet-5",
    equity: 10000000, top_n: 4,
  };

  function wibLabel(h) {
    return String(h).padStart(2, "0") + ":00";
  }

  function dayLabel(d) {
    return AUTO_DAY_LABELS[d] || String(d);
  }

  function toggleChip(cb) {
    cb.closest(".choice-chip").classList.toggle("checked", cb.checked);
  }

  // Fields with exactly one active value at a time (overwritten on save,
  // never merged) — distinct from hours/days/strategies, which Save treats
  // as additions to the existing active list.
  function applySingleValueSettingsToForm(settings) {
    $("autoEnabled").checked = !!settings.enabled;
    $("autoIndex").value = settings.index_name || "LQ45";
    $("autoCustomTickersField").style.display = $("autoIndex").value === "Custom" ? "block" : "none";
    $("autoCustomTickers").value = (settings.custom_tickers || []).join(", ");
    $("autoProvider").value = settings.provider || "Claude";
    $("autoProvider").dispatchEvent(new Event("change"));
    $("autoModel").value = settings.model_id || "";
    $("autoTopN").value = settings.top_n ?? 4;
    $("autoEquity").value = settings.equity ?? 9500000;
    $("autoEquity").dispatchEvent(new Event("input"));
  }

  function clearMultiSelectForm() {
    ["autoHours", "autoDays", "autoStrategies"].forEach((id) => {
      $(id).querySelectorAll("input[type=checkbox]").forEach((cb) => {
        cb.checked = false;
        toggleChip(cb);
      });
    });
  }

  // Full sync: single-value fields + check the boxes matching current
  // active state. Only used on initial tab load — after that, the form is
  // a staging area for additions (see clearMultiSelectForm), not a mirror
  // of the saved config (the Active Automation panel is that mirror).
  function applySettingsToForm(settings) {
    applySingleValueSettingsToForm(settings);
    const activeHours = new Set(settings.hours_wib || []);
    $("autoHours").querySelectorAll("input[type=checkbox]").forEach((cb) => {
      cb.checked = activeHours.has(parseInt(cb.value, 10));
      toggleChip(cb);
    });
    const activeDays = new Set(settings.days_wib || []);
    $("autoDays").querySelectorAll("input[type=checkbox]").forEach((cb) => {
      cb.checked = activeDays.has(parseInt(cb.value, 10));
      toggleChip(cb);
    });
    const activeStrategies = new Set(settings.strategies || []);
    $("autoStrategies").querySelectorAll("input[type=checkbox]").forEach((cb) => {
      cb.checked = activeStrategies.has(cb.value);
      toggleChip(cb);
    });
  }

  function collectSingleValueSettings() {
    const customTickers = $("autoCustomTickers").value.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean);
    return {
      enabled: $("autoEnabled").checked,
      index_name: $("autoIndex").value,
      custom_tickers: $("autoIndex").value === "Custom" ? customTickers : [],
      provider: $("autoProvider").value,
      model_id: $("autoModel").value,
      equity: parseAutoEquity(),
      top_n: parseInt($("autoTopN").value, 10) || 4,
    };
  }

  function collectFormAdditions() {
    return {
      hours_wib: Array.from($("autoHours").querySelectorAll("input:checked")).map((cb) => parseInt(cb.value, 10)),
      days_wib: Array.from($("autoDays").querySelectorAll("input:checked")).map((cb) => parseInt(cb.value, 10)),
      strategies: Array.from($("autoStrategies").querySelectorAll("input:checked")).map((cb) => cb.value),
    };
  }

  async function putAutomationSettings(payload) {
    const res = await fetch("/api/automation/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      // res.statusText is often empty over HTTP/2 (no reason phrase), so
      // always fall back to the numeric status rather than risking a blank
      // "Failed: " message that gives no clue what went wrong.
      throw new Error(err.detail || res.statusText || `HTTP ${res.status}`);
    }
    return await res.json();
  }

  function tagsHtml(kind, items, labelFn) {
    return items.map(
      (v) => `<span class="removable-tag" data-kind="${kind}" data-value="${escapeHtml(String(v))}">${escapeHtml(labelFn(v))}<button type="button" aria-label="Remove ${escapeHtml(labelFn(v))}">×</button></span>`
    ).join("") || `<span class="field-hint" style="margin:0;">none selected</span>`;
  }

  function renderActiveAutomationSummary(settings) {
    const el = $("autoActiveSummary");
    if (!settings) {
      el.innerHTML = `<div class="empty-state" style="margin:0;">Settings unavailable.</div>`;
      return;
    }
    const dayTags = tagsHtml("day", (settings.days_wib || []).slice().sort((a, b) => a - b), dayLabel);
    const hourTags = tagsHtml("hour", (settings.hours_wib || []).slice().sort((a, b) => a - b), wibLabel);
    const strategyTags = tagsHtml("strategy", settings.strategies || [], (s) => s);

    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px;">
        <span class="verdict ${settings.enabled ? "setup" : "no-setup"}">${settings.enabled ? "Automation ON" : "Automation OFF"}</span>
        <button class="btn-link btn-danger" id="btnClearAutomation" type="button">Disable &amp; clear</button>
      </div>
      <label class="field-hint" style="margin:0 0 6px;">Active days</label>
      <div class="choice-grid" style="margin-bottom:14px;">${dayTags}</div>
      <label class="field-hint" style="margin:0 0 6px;">Active hours (WIB)</label>
      <div class="choice-grid" style="margin-bottom:14px;">${hourTags}</div>
      <label class="field-hint" style="margin:0 0 6px;">Active strategies</label>
      <div class="choice-grid" style="margin-bottom:14px;">${strategyTags}</div>
      <div class="field-hint" style="margin:0;">
        Index: ${escapeHtml(settings.index_name || "—")} · Provider: ${escapeHtml(settings.provider || "—")} · Model: ${escapeHtml(settings.model_id || "—")} · Capital: ${formatRp(settings.equity)}
      </div>`;
  }

  // formSync: "full" resyncs every field (incl. checking active boxes) to
  // match the saved state — used for initial load and Disable & Clear.
  // "clear-multi" syncs single-value fields but blanks the hour/day/
  // strategy checkboxes — used after an additive Save, since those boxes
  // are a staging area, not a mirror of what's now active. "none" leaves
  // the form untouched — used after removing one tag, so it doesn't
  // clobber whatever the user was mid-adding.
  async function applyAndSaveAutomation(payload, formSync = "full") {
    $("automationStatus").textContent = "Saving...";
    try {
      const saved = await putAutomationSettings(payload);
      state.automationSettings = saved;
      if (formSync === "full") {
        applySettingsToForm(saved);
      } else if (formSync === "clear-multi") {
        applySingleValueSettingsToForm(saved);
        clearMultiSelectForm();
      }
      renderActiveAutomationSummary(saved);
      $("automationStatus").textContent = "Saved ✓";
    } catch (e) {
      $("automationStatus").textContent = "Failed: " + e.message;
    }
  }

  $("autoActiveSummary").addEventListener("click", (e) => {
    if (e.target.closest("#btnClearAutomation")) {
      if (confirm("Turn off automation and clear all saved settings?")) {
        applyAndSaveAutomation({ ...AUTOMATION_DEFAULTS }, "full");
      }
      return;
    }
    const removeBtn = e.target.closest(".removable-tag button");
    if (!removeBtn || !state.automationSettings) return;
    const tag = removeBtn.closest(".removable-tag");
    const { kind, value } = tag.dataset;
    const updated = { ...state.automationSettings };
    if (kind === "hour") {
      updated.hours_wib = (updated.hours_wib || []).filter((h) => String(h) !== value);
    } else if (kind === "day") {
      updated.days_wib = (updated.days_wib || []).filter((d) => String(d) !== value);
    } else if (kind === "strategy") {
      updated.strategies = (updated.strategies || []).filter((s) => s !== value);
    }
    applyAndSaveAutomation(updated, "none");
  });

  async function initAutomation() {
    populateProviderModel("autoProvider", "autoModel");

    $("autoIndex").innerHTML = state.indices.names
      .map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}${n !== "Custom" ? " (" + state.indices.tickers[n].length + ")" : ""}</option>`)
      .join("");
    $("autoIndex").addEventListener("change", () => {
      $("autoCustomTickersField").style.display = $("autoIndex").value === "Custom" ? "block" : "none";
    });

    $("autoDays").innerHTML = AUTO_DAYS.map(
      (d) => `<label class="choice-chip"><input type="checkbox" value="${d}"> ${dayLabel(d)}</label>`
    ).join("");
    $("autoDays").querySelectorAll("input[type=checkbox]").forEach((cb) => {
      cb.addEventListener("change", () => toggleChip(cb));
    });

    $("autoHours").innerHTML = AUTO_HOURS.map(
      (h) => `<label class="choice-chip"><input type="checkbox" value="${h}"> ${wibLabel(h)}</label>`
    ).join("");
    $("autoHours").querySelectorAll("input[type=checkbox]").forEach((cb) => {
      cb.addEventListener("change", () => toggleChip(cb));
    });

    $("autoStrategies").innerHTML = state.prompts.map(
      (p) => `<label class="choice-chip"><input type="checkbox" value="${escapeHtml(p)}"> ${escapeHtml(p)}</label>`
    ).join("");
    $("autoStrategies").querySelectorAll("input[type=checkbox]").forEach((cb) => {
      cb.addEventListener("change", () => toggleChip(cb));
    });

    try {
      const res = await fetch("/api/automation/settings");
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
      const settings = await res.json();
      state.automationSettings = settings;
      applySettingsToForm(settings);
      renderActiveAutomationSummary(settings);
    } catch (e) {
      $("automationStatus").textContent = "Settings unavailable: " + e.message;
      renderActiveAutomationSummary(null);
    }

    try {
      const res = await fetch("/api/automation/results");
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
      renderAutomationResults(await res.json());
    } catch (e) {
      $("autoResultsList").innerHTML = `<div class="empty-state">Couldn't load recent setups: ${escapeHtml(e.message)}</div>`;
    }
  }

  function formatWib(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    // WIB is a fixed UTC+7 offset (no DST) — compute directly rather than
    // relying on the browser's local timezone.
    const wib = new Date(d.getTime() + 7 * 60 * 60 * 1000);
    const pad = (n) => String(n).padStart(2, "0");
    return `${wib.getUTCFullYear()}-${pad(wib.getUTCMonth() + 1)}-${pad(wib.getUTCDate())} ${pad(wib.getUTCHours())}:${pad(wib.getUTCMinutes())}`;
  }

  function formatAutoScore(r) {
    if (r.score == null) return "—";
    // max_score wasn't recorded for rows saved before that column existed —
    // fall back to a bare number for those rather than showing "4/null".
    return r.max_score != null ? `${r.score}/${r.max_score}` : String(r.score);
  }

  function renderAutomationResults(results) {
    const el = $("autoResultsList");
    state.lastAutomationResults = results || [];
    if (!results || !results.length) {
      el.innerHTML = `<div class="empty-state">No automated setups yet. They'll show up here once automation is enabled and finds one.</div>`;
      return;
    }
    el.innerHTML = results
      .map((r, i) => {
        const plan = { ...r, verdict: "SETUP" };
        return `
          <div class="manual-result auto-result-card" style="margin-bottom:10px;padding:0;overflow:hidden;">
            <button type="button" class="auto-result-toggle" data-idx="${i}" aria-expanded="false">
              <span class="auto-result-summary">
                <span class="mono" style="font-size:15px;font-weight:700;">${escapeHtml(r.ticker)}</span>
                ${actionBadgeHtml(r.action)}
                <span class="run-status">${escapeHtml(r.strategy)} · ${formatWib(r.ticked_at)} WIB · score ${escapeHtml(formatAutoScore(r))}</span>
              </span>
              <span class="auto-result-chevron">Details ▾</span>
            </button>
            <div class="auto-result-detail" id="autoResultDetail${i}" hidden style="padding:0 22px 20px;">
              ${planHtml(plan)}
              ${
                r.analysis_html
                  ? `<div class="excerpt rendered-md" style="padding:0;margin-top:6px;">${r.analysis_html}</div>`
                  : r.narrative_markdown
                  ? `<div class="excerpt" style="padding:0;margin-top:6px;">${escapeHtml(r.narrative_markdown)}</div>`
                  : ""
              }
              <div class="foot" style="padding:12px 0 0;">
                <button class="btn-save" data-action="save-auto-result" data-idx="${i}">+ Journal</button>
              </div>
            </div>
          </div>`;
      })
      .join("");
  }

  $("autoResultsList").addEventListener("click", async (e) => {
    const toggleBtn = e.target.closest(".auto-result-toggle");
    if (toggleBtn) {
      const detail = $("autoResultDetail" + toggleBtn.dataset.idx);
      const expanded = toggleBtn.getAttribute("aria-expanded") === "true";
      toggleBtn.setAttribute("aria-expanded", String(!expanded));
      detail.hidden = expanded;
      toggleBtn.querySelector(".auto-result-chevron").textContent = expanded ? "Details ▾" : "Hide ▴";
      return;
    }

    const saveBtn = e.target.closest('[data-action="save-auto-result"]');
    if (saveBtn) {
      const r = state.lastAutomationResults[parseInt(saveBtn.dataset.idx, 10)];
      if (!r) return;
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving...";
      try {
        await fetch("/api/journal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ticker: r.ticker,
            model: `${r.provider || "Automation"}/${r.model_id || "unknown"}`,
            strategy: r.strategy,
            analysis: r.narrative_markdown || "",
          }),
        });
        state.journal = await fetch("/api/journal").then((res) => res.json());
        renderJournal();
        saveBtn.textContent = "Saved ✓";
      } catch (err) {
        saveBtn.textContent = "Failed";
        saveBtn.disabled = false;
      }
    }
  });

  $("btnSaveAutomation").addEventListener("click", async () => {
    const btn = $("btnSaveAutomation");
    btn.disabled = true;
    try {
      const current = state.automationSettings || { ...AUTOMATION_DEFAULTS };
      const additions = collectFormAdditions();
      const merged = {
        ...collectSingleValueSettings(),
        hours_wib: Array.from(new Set([...(current.hours_wib || []), ...additions.hours_wib])),
        days_wib: Array.from(new Set([...(current.days_wib || []), ...additions.days_wib])),
        strategies: Array.from(new Set([...(current.strategies || []), ...additions.strategies])),
      };
      await applyAndSaveAutomation(merged, "clear-multi");
    } finally {
      btn.disabled = false;
    }
  });

  // ---------- version footer ----------
  async function loadVersion() {
    try {
      const v = await fetch("/api/version").then((r) => r.json());
      const parts = [`deployed ${v.deployed_at}`];
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
      // Core config (models/indices/prompts) must all load for the app to be
      // usable at all. The journal is independently fetched — a Supabase
      // hiccup there shouldn't take down the rest of the app (screener,
      // manual analysis, automation settings all work without it).
      const [models, indices, prompts] = await Promise.all([
        fetch("/api/models").then((r) => r.json()),
        fetch("/api/indices").then((r) => r.json()),
        fetch("/api/prompts").then((r) => r.json()),
      ]);
      state.models = models;
      state.indices = indices;
      state.prompts = prompts.names;

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

      try {
        state.journal = await fetch("/api/journal").then((r) => r.json());
      } catch (e) {
        state.journal = [];
        console.error("journal fetch failed:", e);
      }
      renderJournal();

      await initAutomation();
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

  function actionBadgeHtml(action) {
    if (!action) return "";
    const cls = action === "BUY" ? "action-buy" : action === "SELL" ? "action-sell" : "action-hold";
    return `<span class="verdict ${cls}">${escapeHtml(action)}</span>`;
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
        ${actionBadgeHtml(plan.action)}
        <div class="plan-grid mono">
          ${rows.map(([k, v, cls]) => `<div class="plan-cell"><span>${k}</span><b class="${cls}">${escapeHtml(String(v))}</b></div>`).join("")}
        </div>
      </div>`;
  }

  function positionHtml(position) {
    if (!position) return "";
    const rows = [
      ["Shares", position.shares, ""],
      ["Cost Basis", formatRp(position.cost_basis_rp), ""],
      ["Current Value", formatRp(position.current_value_rp), ""],
      ["Unrealized P/L", formatRp(position.pnl_rp), position.pnl_rp >= 0 ? "gain" : "loss"],
      ["P/L %", position.pnl_pct != null ? `${position.pnl_pct}%` : "—", position.pnl_pct >= 0 ? "gain" : "loss"],
    ];
    return `
      <div class="plan-stats">
        <span class="verdict no-setup">My Position</span>
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
  let manualMode = "ticker";
  document.querySelectorAll(".mode-toggle .mode-btn").forEach((b) => {
    b.addEventListener("click", () => {
      manualMode = b.dataset.mode;
      document.querySelectorAll(".mode-toggle .mode-btn").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      $("uploadModeField").style.display = manualMode === "upload" ? "block" : "none";
      $("lblTicker").textContent = manualMode === "ticker" ? "Ticker" : "Ticker (optional, needed for P/L)";
      $("tickerHint").textContent =
        manualMode === "ticker"
          ? "We'll fetch the chart and current price automatically."
          : "Upload your own chart screenshot below. Add a ticker too if you want P/L against your position.";
    });
  });

  $("fileChart").addEventListener("change", () => {
    const file = $("fileChart").files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    $("preview").src = url;
    $("preview").style.display = "block";
  });

  $("btnAnalyzeManual").addEventListener("click", async () => {
    const ticker = $("inpTicker").value.trim().toUpperCase();
    const file = manualMode === "upload" ? $("fileChart").files[0] : null;
    const lots = parseInt($("inpPositionLots").value, 10) || 0;
    const avgPrice = parsePositionAvgPrice();

    if (manualMode === "ticker" && !ticker) {
      alert("Please enter a ticker.");
      return;
    }
    if (manualMode === "upload" && !file) {
      alert("Please upload a chart screenshot first.");
      return;
    }
    if ((lots || avgPrice) && !ticker) {
      alert("A ticker is required to calculate P/L against your position.");
      return;
    }

    const btn = $("btnAnalyzeManual");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner spinner-inline"></span> Analyzing...';
    $("manualResultWrap").style.display = "block";
    $("manualResult").innerHTML = '<div class="empty-state processing"><span class="spinner"></span> Analyzing...</div>';

    const form = new FormData();
    if (file) form.append("file", file);
    form.append("provider", $("selProviderM").value);
    form.append("model_id", $("selModelM").value);
    form.append("prompt", $("selPromptM").value);
    form.append("equity", parseEquity());
    form.append("ticker", ticker);
    if (lots) form.append("lots", lots);
    if (avgPrice) form.append("avg_price", avgPrice);

    try {
      const res = await fetch("/api/analyze", { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || res.statusText);
      }
      const data = await res.json();
      state.lastManualResult = {
        ticker: ticker || null,
        model: `${$("selProviderM").value}/${$("selModelM").value}`,
        strategy: $("selPromptM").value,
        analysis: data.analysis,
      };
      $("manualResultWrap").style.display = "block";
      $("manualResult").innerHTML =
        positionHtml(data.position_pnl) +
        planHtml(data.plan) +
        data.analysis_html +
        `<div class="foot" style="padding-top:14px;"><button class="btn-save" data-action="save-manual-result">+ Journal</button></div>`;
    } catch (e) {
      $("manualResultWrap").style.display = "block";
      $("manualResult").textContent = "Analysis failed: " + e.message;
    } finally {
      btn.disabled = false;
      btn.textContent = "🚀 Run Analysis";
    }
  });

  $("manualResult").addEventListener("click", async (e) => {
    const saveBtn = e.target.closest('[data-action="save-manual-result"]');
    if (!saveBtn || !state.lastManualResult) return;
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";
    try {
      await fetch("/api/journal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(state.lastManualResult),
      });
      state.journal = await fetch("/api/journal").then((r) => r.json());
      renderJournal();
      saveBtn.textContent = "Saved ✓";
    } catch (err) {
      saveBtn.textContent = "Failed";
      saveBtn.disabled = false;
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
