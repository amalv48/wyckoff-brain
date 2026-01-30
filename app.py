import streamlit as st
import google.generativeai as genai
import json
import os
from PIL import Image
from datetime import datetime

# --- 1. KONFIGURASI API & MODEL ---
# Pastikan GEMINI_API_KEY sudah diset di Streamlit Cloud Secrets
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    # Menggunakan nama model standar yang paling kompatibel
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"Gagal konfigurasi API: {e}")

# --- 2. FUNGSI MEMORI (DATABASE) ---
def load_memory():
    if os.path.exists("journal.json"):
        try:
            with open("journal.json", "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_memory(data):
    with open("journal.json", "w") as f:
        json.dump(data, f)

# --- 3. UI APLIKASI ---
st.set_page_config(page_title="Wyckoff Brain MVP", layout="wide")
st.title("🧠 Wyckoff Brain: Self-Improving Analyst")

# Load data lama
memory = load_memory()
last_analysis = memory[-1]["analysis"] if memory else "Belum ada analisa sebelumnya (D-0)."

with st.sidebar:
    st.header("⚙️ Portofolio & Modal")
    equity = st.number_input("Total Modal (Rp)", value=9500000, step=50000)
    st.info(f"Analisa terakhir tersimpan: {len(memory)} entri")

st.subheader("📁 Input Analisa Hari Ini")
uploaded_file = st.file_uploader("Upload Screenshot Chart (Daily)", type=["png", "jpg", "jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="Chart Saham Terkini", use_container_width=True)

    if st.button("🚀 Jalankan Analisa & Self-Improvement"):
        # TEMPLATE PROMPT (OTAK)
        prompt = f"""
        Peran: Ahli Swing Trader Pasar Saham Indonesia & Wyckoff Strategist (>10 thn exp).
        Disiplin: Sangat Konservatif, Manajemen Risiko Ketat.

        TUGAS 1 (EVALUASI SELF-IMPROVEMENT): 
        Bandingkan pergerakan harga pada gambar ini dengan analisa terakhir Anda berikut: 
        ---
        {last_analysis}
        ---
        Jelaskan kesalahan atau ketepatan analisa tersebut berdasarkan kondisi harga sekarang. 
        Gunakan ini sebagai pelajaran untuk memperbaiki analisa hari ini.

        TUGAS 2 (ANALISA TRADING PLAN BARU):
        Identifikasi Fase Wyckoff (Accumulation, Markup, Distribution, atau Markdown).
        Buat rencana trading dengan aturan WAJIB:
        1. Format: Satu tabel vertikal (Parameter | Nilai/Keterangan).
        2. Perhitungan Grup 2: Gunakan harga BATAS ATAS dari Range Entry sebagai dasar.
        3. Risk Reward Ratio (RRR): WAJIB Minimal 1:2. Sesuaikan Entry atau SL agar tercapai.
        4. Komponen Tabel: 
           - GRUP 1: Fase Wyckoff, Trend, Range Entry, TP1, SL, Konfirmasi Entry.
           - GRUP 2: Alokasi Dana, Harga Entri (Worst Case), Jumlah Lot, Potensi Rugi Rp, Potensi Profit Rp, RRR.
           - GRUP 3: Law of Effort vs Result (Volume), Pemicu Batalkan Ide.

        Kondisi Modal Aktual: Rp {equity}
        """

        with st.spinner("Otak sedang memproses data dan memori..."):
            try:
                # Memanggil API Gemini
                response = model.generate_content([prompt, img])
                
                if response.text:
                    output_text = response.text
                    st.markdown("### 📊 Hasil Analisa Otak")
                    st.markdown(output_text)
                    
                    # Simpan hasil ke journal.json
                    new_entry = {
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "analysis": output_text
                    }
                    memory.append(new_entry)
                    save_memory(memory)
                    st.success("✅ Berhasil! Analisa disimpan untuk pembelajaran besok.")
                else:
                    st.error("Gagal menerima teks dari AI. Silakan coba lagi.")

            except Exception as e:
                st.error(f"⚠️ Error API: {str(e)}")
                st.info("Saran: Cek apakah API Key di Secrets sudah benar dan model 'gemini-1.5-flash' tersedia di akun Anda.")
