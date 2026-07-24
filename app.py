import json
import os
from datetime import datetime

import streamlit as st
from PIL import Image

from providers import call_model
from screener import fetch_ohlcv, load_indices, render_chart, shortlist

JOURNAL_PATH = "journal.json"


# --- 1. FUNGSI PEMBACA/PENULIS FILE EKSTERNAL ---
def load_json_file(file_path, default_value):
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return default_value


def save_journal():
    with open(JOURNAL_PATH, "w") as f:
        json.dump(st.session_state.journal_memory, f, indent=4)


def add_journal_entry(entry):
    st.session_state.journal_memory.append(entry)
    save_journal()


# --- 2. KONFIGURASI UI & SESSION STATE ---
st.set_page_config(page_title="Wyckoff Modular Brain", layout="wide")

if "journal_memory" not in st.session_state:
    st.session_state.journal_memory = load_json_file(JOURNAL_PATH, [])

model_catalog = load_json_file("models.json", {"Claude": {"Sonnet 5": "claude-sonnet-5"}})
prompt_options = load_json_file("prompts.json", {"Default": "Buat analisa Wyckoff dari {equity}."})
indices = load_indices()

# --- 3. SIDEBAR (KONTROL MODULAR) ---
with st.sidebar:
    st.header("🎮 Control Panel")

    selected_provider = st.selectbox("Provider AI:", list(model_catalog.keys()))
    provider_models = model_catalog[selected_provider]
    selected_model_label = st.selectbox("Pilih Model:", list(provider_models.keys()))
    selected_model_id = provider_models[selected_model_label]

    selected_prompt_key = st.selectbox("Pilih Strategi Prompt:", list(prompt_options.keys()))

    st.divider()
    st.header("⚙️ Portofolio")
    equity = st.number_input("Total Modal (Rp)", min_value=0, value=9500000)

    st.divider()
    if st.session_state.journal_memory:
        json_data = json.dumps(st.session_state.journal_memory, indent=4)
        st.download_button(
            label="📥 Download Jurnal (JSON)",
            data=json_data,
            file_name=f"wyckoff_journal_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
        )

st.title("🧠 Wyckoff Brain: Modular Version")
st.info(f"Model Aktif: **{selected_provider} / {selected_model_label}** | Strategi: **{selected_prompt_key}**")

tab_screener, tab_manual, tab_journal = st.tabs(
    ["🔎 Screener Index", "🖼️ Analisa Manual", "📜 Jurnal & Tracking"]
)


def run_strategy(ticker_context, equity_value):
    raw_prompt = prompt_options[selected_prompt_key]
    # Prompts are in English but equity is always Indonesian Rupiah — a bare
    # number reads as USD to the model, so spell out the currency.
    return raw_prompt.format(last_analisa=ticker_context, equity=f"Rp {equity_value:,.0f}")


# --- TAB 1: SCREENER INDEX ---
with tab_screener:
    st.subheader("Screening Otomatis LQ45 / IDX30")
    st.caption(
        "Filter kuantitatif (volume & posisi harga) mempersempit index ke beberapa "
        "kandidat, lalu AI menjalankan strategi Wyckoff hanya pada kandidat tersebut. "
        "Daftar konstituen index bersifat perkiraan — cek ulang berkala di 'Custom'."
    )

    index_names = [k for k in indices.keys() if not k.startswith("_")]
    selected_index = st.selectbox("Pilih Index:", index_names)

    if selected_index == "Custom":
        custom_input = st.text_area(
            "Ticker Custom (pisahkan dengan koma, tanpa .JK)",
            value=", ".join(indices.get("Custom", [])),
        )
        tickers = [t.strip().upper() for t in custom_input.split(",") if t.strip()]
    else:
        tickers = indices[selected_index]
        st.caption(f"{len(tickers)} saham di {selected_index}")

    top_n = st.slider("Jumlah kandidat yang dianalisa AI", min_value=3, max_value=15, value=8)

    if st.button("🚀 Jalankan Screening", type="primary"):
        if not tickers:
            st.warning("Tidak ada ticker untuk di-screening.")
        else:
            with st.spinner(f"Mengambil data {len(tickers)} saham..."):
                data = fetch_ohlcv(tickers)
            if not data:
                st.error("Gagal mengambil data harga. Coba lagi nanti.")
            else:
                candidates = shortlist(data, top_n=top_n)
                if not candidates:
                    st.info("Tidak ada kandidat yang lolos filter kuantitatif hari ini.")
                st.session_state.screener_results = []
                for cand in candidates:
                    ticker = cand["ticker"]
                    df = data[ticker]
                    with st.spinner(f"Analisa AI untuk {ticker}..."):
                        chart_img = render_chart(df, ticker)
                        context_note = (
                            f"Ini hasil screening otomatis untuk saham {ticker}. "
                            f"Belum ada analisa manual sebelumnya. Sinyal kuantitatif "
                            f"yang terdeteksi: {'; '.join(cand['signals'])}. "
                            f"Harga close terakhir: {cand['last_close']}."
                        )
                        prompt = run_strategy(context_note, equity)
                        try:
                            analysis = call_model(
                                selected_provider, selected_model_id, prompt, image=chart_img
                            )
                        except Exception as e:
                            analysis = f"Analisa gagal: {e}"
                    st.session_state.screener_results.append(
                        {
                            "ticker": ticker,
                            "score": cand["score"],
                            "signals": cand["signals"],
                            "chart": chart_img,
                            "analysis": analysis,
                        }
                    )

    for i, result in enumerate(st.session_state.get("screener_results", [])):
        with st.expander(f"📊 {result['ticker']} (skor kuantitatif: {result['score']})"):
            col1, col2 = st.columns([1, 1])
            with col1:
                st.image(result["chart"], use_container_width=True)
                st.markdown("**Sinyal kuantitatif:**")
                for s in result["signals"]:
                    st.markdown(f"- {s}")
            with col2:
                st.markdown(result["analysis"])
            if st.button(f"💾 Simpan {result['ticker']} ke Jurnal", key=f"save_screen_{i}"):
                add_journal_entry(
                    {
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "model": f"{selected_provider}/{selected_model_id}",
                        "strategy": selected_prompt_key,
                        "ticker": result["ticker"],
                        "analysis": result["analysis"],
                        "trade": {
                            "status": "Planned",
                            "entry_price": None,
                            "exit_price": None,
                            "qty": None,
                            "notes": "",
                            "pnl": None,
                        },
                    }
                )
                st.success(f"{result['ticker']} disimpan ke jurnal.")


# --- TAB 2: ANALISA MANUAL (upload screenshot chart) ---
with tab_manual:
    st.subheader("Upload Screenshot Chart")
    uploaded_file = st.file_uploader("Upload Screenshot Chart", type=["png", "jpg", "jpeg"])

    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, caption="Chart Saham", use_container_width=True)
        manual_ticker = st.text_input("Ticker (opsional, untuk label jurnal)", value="")

        if st.button("🚀 Jalankan Analisa"):
            last_entries = [
                e for e in st.session_state.journal_memory if e.get("ticker") == manual_ticker
            ] if manual_ticker else []
            last_analisa = last_entries[-1]["analysis"] if last_entries else "Tidak ada data sebelumnya."

            prompt = run_strategy(last_analisa, equity)

            with st.spinner(f"Otak ({selected_provider}/{selected_model_label}) sedang berpikir..."):
                try:
                    output_text = call_model(selected_provider, selected_model_id, prompt, image=img)
                    add_journal_entry(
                        {
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "model": f"{selected_provider}/{selected_model_id}",
                            "strategy": selected_prompt_key,
                            "ticker": manual_ticker or None,
                            "analysis": output_text,
                            "trade": {
                                "status": "Planned",
                                "entry_price": None,
                                "exit_price": None,
                                "qty": None,
                                "notes": "",
                                "pnl": None,
                            },
                        }
                    )
                    st.markdown(f"### 📊 Hasil Analisa: {selected_prompt_key}")
                    st.markdown(output_text)
                    st.success("Analisa tersimpan dalam jurnal!")
                except Exception as e:
                    st.error(f"Analisa Gagal: {e}")


# --- TAB 3: JURNAL & TRACKING ---
with tab_journal:
    st.subheader("📜 Riwayat Analisa & Trade Tracking")

    if not st.session_state.journal_memory:
        st.info("Belum ada entri jurnal.")

    for i, entry in enumerate(reversed(st.session_state.journal_memory)):
        real_idx = len(st.session_state.journal_memory) - 1 - i
        label = f"{entry['date']} | {entry.get('ticker') or entry['strategy']} ({entry['model']})"
        with st.expander(label):
            st.markdown(entry["analysis"])

            trade = entry.setdefault(
                "trade",
                {"status": "Planned", "entry_price": None, "exit_price": None, "qty": None, "notes": "", "pnl": None},
            )

            st.markdown("**Update Hasil Trade (input manual)**")
            c1, c2, c3, c4 = st.columns(4)
            status = c1.selectbox(
                "Status",
                ["Planned", "Open", "Closed", "Skipped"],
                index=["Planned", "Open", "Closed", "Skipped"].index(trade.get("status", "Planned")),
                key=f"status_{real_idx}",
            )
            entry_price = c2.number_input(
                "Harga Entry", min_value=0.0, value=float(trade.get("entry_price") or 0.0), key=f"entry_{real_idx}"
            )
            exit_price = c3.number_input(
                "Harga Exit", min_value=0.0, value=float(trade.get("exit_price") or 0.0), key=f"exit_{real_idx}"
            )
            qty = c4.number_input(
                "Qty (lot)", min_value=0, value=int(trade.get("qty") or 0), key=f"qty_{real_idx}"
            )
            notes = st.text_input("Catatan", value=trade.get("notes", ""), key=f"notes_{real_idx}")

            if st.button("💾 Update Trade", key=f"update_{real_idx}"):
                pnl = None
                if status == "Closed" and entry_price and exit_price and qty:
                    pnl = round((exit_price - entry_price) * qty, 2)
                entry["trade"] = {
                    "status": status,
                    "entry_price": entry_price or None,
                    "exit_price": exit_price or None,
                    "qty": qty or None,
                    "notes": notes,
                    "pnl": pnl,
                }
                st.session_state.journal_memory[real_idx] = entry
                save_journal()
                st.success("Trade diperbarui.")

            if trade.get("pnl") is not None:
                pnl_color = "green" if trade["pnl"] >= 0 else "red"
                st.markdown(f"**P/L: :{pnl_color}[Rp {trade['pnl']:,.0f}]**")
