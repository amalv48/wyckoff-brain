import streamlit as st
import google.generativeai as genai
import json
from PIL import Image
from datetime import datetime

# --- 1. KONFIGURASI API ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-3-flash-preview')
except Exception as e:
    st.error(f"Gagal konfigurasi API: {e}")

# --- 2. LOGIKA MEMORI (Session State) ---
# Menggunakan session_state agar data bertahan selama browser tidak di-refresh
if "journal_memory" not in st.session_state:
    st.session_state.journal_memory = []

# --- 3. UI APLIKASI ---
st.set_page_config(page_title="Wyckoff Brain MVP", layout="wide")
st.title("🧠 Wyckoff Brain: Permanent Journal")

with st.sidebar:
    st.header("⚙️ Portofolio & Modal")
    equity = st.number_input("Total Modal (Rp)", value=9500000)
    
    st.divider()
    st.subheader("💾 Backup Data")
    if st.session_state.journal_memory:
        # Fitur download agar user bisa simpan ke Excel/JSON lokal
        json_data = json.dumps(st.session_state.journal_memory, indent=4)
        st.download_button(
            label="Download Semua Jurnal (JSON)",
            data=json_data,
            file_name=f"trading_journal_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json"
        )

st.subheader("📁 Input Analisa Hari Ini")
uploaded_file = st.file_uploader("Upload Screenshot Chart", type=["png", "jpg", "jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="Chart Saham Terkini", use_container_width=True)

    if st.button("🚀 Jalankan Analisa & Self-Improvement"):
        # Mengambil analisa terakhir dari session state
        last_analisa = st.session_state.journal_memory[-1]['analysis'] if st.session_state.journal_memory else "Tidak ada data sebelumnya."
        
        prompt = f"""
        Peran: Ahli Swing Trader Indonesia & Wyckoff Strategist.
        
        TUGAS 1 (EVALUASI):
        Bandingkan chart ini dengan analisa terakhir:
        {last_analisa}
        
        TUGAS 2 (ANALISA BARU):
        Buat trading plan Wyckoff dalam tabel vertikal.
        Aturan: RRR minimal 1:2, gunakan Batas Atas Range Entry untuk Grup 2.
        Modal: Rp {equity}
        """

        with st.spinner("Otak sedang memproses..."):
            try:
                response = model.generate_content([prompt, img])
                output_text = response.text
                
                # Simpan ke Session State
                new_entry = {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "analysis": output_text
                }
                st.session_state.journal_memory.append(new_entry)
                
                st.markdown("### 📊 Hasil Analisa Otak")
                st.markdown(output_text)
                st.success("✅ Analisa berhasil dibuat dan disimpan di memori sesi!")
                
            except Exception as e:
                st.error(f"Error: {e}")

# --- 4. TAMPILKAN RIWAYAT JURNAL ---
st.divider()
st.subheader("📜 Riwayat Jurnal (Sesi Ini)")
if st.session_state.journal_memory:
    for i, m in enumerate(reversed(st.session_state.journal_memory)):
        with st.expander(f"Analisa {m['date']}"):
            st.markdown(m['analysis'])
else:
    st.info("Belum ada riwayat analisa. Silakan upload chart untuk memulai.")
