import streamlit as st
import google.generativeai as genai
import json
import os
from PIL import Image

# --- KONFIGURASI API ---
# Ambil API Key dari Streamlit Secrets
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

# --- LOGIKA MEMORI ---
def load_memory():
    if os.path.exists("journal.json"):
        with open("journal.json", "r") as f:
            return json.load(f)
    return []

def save_memory(data):
    with open("journal.json", "w") as f:
        json.dump(data, f)

# --- UI APP ---
st.set_page_config(page_title="Wyckoff Brain MVP", layout="wide")
st.title("🧠 Wyckoff Brain: Self-Improving Analyst")

memory = load_memory()
last_analysis = memory[-1]["analysis"] if memory else "Belum ada analisa sebelumnya."

with st.sidebar:
    st.header("Konfigurasi Portofolio")
    equity = st.number_input("Total Modal (Rp)", value=9500000)
    cash = st.number_input("Sisa Cash (Rp)", value=9500000)
    
st.subheader("Analisa Hari Ini (D+n)")
uploaded_file = st.file_uploader("Upload Screenshot Chart", type=["png", "jpg", "jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="Chart Terkini", use_container_width=True)

    if st.button("Jalankan Analisa & Self-Improvement"):
        # PROMPT OTAK
        prompt = f"""
        Peran: Ahli Swing Trader Indonesia & Wyckoff Strategist (>10 thn exp).
        
        TUGAS 1 (EVALUASI): 
        Bandingkan chart ini dengan analisa terakhir berikut: {last_analysis}. 
        Jelaskan apa yang benar/salah dari analisa tersebut untuk perbaikan hari ini.

        TUGAS 2 (ANALISA BARU):
        Berikan trading plan baru sesuai aturan:
        1. Format: Tabel vertikal (Parameter | Nilai).
        2. Gunakan Batas Atas Range Entry sebagai dasar hitung di Grup 2.
        3. RRR WAJIB MINIMAL 1:2 (Sesuaikan Entry/SL jika perlu).
        4. Grup 1: Strategi (Fase Wyckoff, Range Entry, TP1, TP2, SL, Konfirmasi).
        5. Grup 2: Manajemen Risiko (Alokasi Dana, Lot, Potensi Rugi/Profit Net Fee).
        
        Kondisi Modal: Rp {equity}
        """

        with st.spinner("Otak sedang berpikir..."):
            response = model.generate_content([prompt, img])
            output_text = response.text
            
            st.markdown("### Hasil Analisa Otak")
            st.markdown(output_text)
            
            # Simpan ke memori
            memory.append({"date": str(st.session_state.get('date')), "analysis": output_text})
            save_memory(memory)
            st.success("Analisa disimpan ke memori untuk perbaikan besok!")
