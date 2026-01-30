import streamlit as st
import google.generativeai as genai
import json
import os
from PIL import Image
from datetime import datetime

# --- 1. FUNGSI PEMBACA FILE EKSTERNAL ---
def load_json_file(file_path, default_value):
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return default_value

# --- 2. KONFIGURASI UI & SESSION STATE ---
st.set_page_config(page_title="Wyckoff Modular Brain", layout="wide")

if "journal_memory" not in st.session_state:
    st.session_state.journal_memory = []

# Load data model dan prompt
model_options = load_json_file("models.json", ["gemini-3-flash-preview"])
prompt_options = load_json_file("prompts.json", {"Default": "Buat analisa Wyckoff dari {equity}."})

# --- 3. SIDEBAR (KONTROL MODULAR) ---
with st.sidebar:
    st.header("🎮 Control Panel")
    
    # Dropdown Pilih Model
    selected_model_name = st.selectbox("Pilih Model AI:", model_options)
    
    # Dropdown Pilih Prompt
    selected_prompt_key = st.selectbox("Pilih Strategi Prompt:", list(prompt_options.keys()))
    
    st.divider()
    st.header("⚙️ Portofolio")
    equity = st.number_input("Total Modal (Rp)", value=9500000)
    
    st.divider()
    if st.session_state.journal_memory:
        json_data = json.dumps(st.session_state.journal_memory, indent=4)
        st.download_button(
            label="📥 Download Jurnal (JSON)",
            data=json_data,
            file_name=f"wyckoff_journal_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json"
        )

# --- 4. KONFIGURASI API ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel(selected_model_name)
except Exception as e:
    st.error(f"Gagal inisialisasi Model {selected_model_name}: {e}")

# --- 5. MAIN INTERFACE ---
st.title("🧠 Wyckoff Brain: Modular Version")
st.info(f"Model Aktif: **{selected_model_name}** | Strategi: **{selected_prompt_key}**")

uploaded_file = st.file_uploader("Upload Screenshot Chart", type=["png", "jpg", "jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="Chart Saham", use_container_width=True)

    if st.button("🚀 Jalankan Analisa"):
        last_analisa = st.session_state.journal_memory[-1]['analysis'] if st.session_state.journal_memory else "Tidak ada data sebelumnya."
        
        # Ambil template prompt dan suntikkan variabel
        raw_prompt = prompt_options[selected_prompt_key]
        final_prompt = raw_prompt.format(last_analisa=last_analisa, equity=equity)

        with st.spinner(f"Otak ({selected_model_name}) sedang berpikir..."):
            try:
                response = model.generate_content([final_prompt, img])
                output_text = response.text
                
                # Simpan ke Memori
                st.session_state.journal_memory.append({
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "model": selected_model_name,
                    "strategy": selected_prompt_key,
                    "analysis": output_text
                })
                
                st.markdown(f"### 📊 Hasil Analisa: {selected_prompt_key}")
                st.markdown(output_text)
                st.success("Analisa tersimpan dalam sesi ini!")
                
            except Exception as e:
                st.error(f"Analisa Gagal: {e}")

# --- 6. RIWAYAT ---
st.divider()
st.subheader("📜 Riwayat Analisa")
if st.session_state.journal_memory:
    for m in reversed(st.session_state.journal_memory):
        with st.expander(f"{m['date']} | {m['strategy']} ({m['model']})"):
            st.markdown(m['analysis'])
