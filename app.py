import streamlit as st
import pandas as pd
import time
import re
import datetime
import sys
import logging
from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from collections import Counter
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from dataclasses import dataclass, asdict

# --- KONFIGURASI AWAL ---
st.set_page_config(page_title="MapInsight Pro Scraper", layout="wide")

# Konfigurasi Logger
logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("scraper")

# Inisialisasi NLTK
@st.cache_resource
def init_nltk():
    try:
        nltk.download('stopwords', quiet=True)
        nltk.download('punkt', quiet=True)
        nltk.download('punkt_tab', quiet=True)
    except LookupError: pass

init_nltk()

# Data Class Bisnis (Updated dengan Field Lengkap)
# --- UPDATE DI BAGIAN ATAS (Business Class) ---
@dataclass
class Business:
    name: str = ""
    rating: str = ""
    category: str = ""
    address: str = ""
    phone: str = ""
    website: str = ""
    url: str = ""          # Long Link (URL Browser)
    share_link: str = ""   # Short Link (maps.app.goo.gl) -> BARU
    scraped_at_utc: str = ""

# Kata kunci ulasan
REVIEW_WORDS = {
    "ulasan", "reviews", "review", "tinjauan", "reseñas", "avis", "bewertungen", "recensioni"
}
BAD_WORDS = {"tulis", "write", "nulis", "add", "tambahkan", "crear", "schreiben"}

# --- FUNGSI HELPER ---
def get_driver(headless=True):
    driver = Driver(uc=True, headless=headless, incognito=True)
    driver.set_window_size(1400, 900)
    return driver

# GANTI/TAMBAHKAN FUNGSI HELPER INI:
def safe_get_text(driver, selector):
    try: return driver.find_element(By.CSS_SELECTOR, selector).text.strip()
    except: return ""

def safe_get_attribute(driver, selector, attr):
    try: return driver.find_element(By.CSS_SELECTOR, selector).get_attribute(attr)
    except: return ""

def extract_business_info(driver):
    """Mengambil detail bisnis TERMASUK Short Link dari tombol Share"""
    info = {
        "name": "", "rating": "", "category": "", 
        "address": "", "phone": "", "website": "", "share_link": ""
    }
    
    try:
        # Tunggu Nama Bisnis
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1.DUwDvf")))
        
        info["name"] = safe_get_text(driver, "h1.DUwDvf")
        info["rating"] = safe_get_text(driver, "div.F7nice span[aria-hidden='true']")
        info["category"] = safe_get_text(driver, "button.DkEaL")
        
        # Alamat
        address = safe_get_attribute(driver, 'button[data-item-id="address"]', "aria-label")
        info["address"] = address.replace("Address: ", "").replace("Alamat: ", "") if address else ""
        
        # Telepon
        phone = safe_get_attribute(driver, 'button[data-item-id*="phone"]', "aria-label")
        info["phone"] = phone.replace("Phone: ", "").replace("Telepon: ", "") if phone else ""
        
        # Website
        info["website"] = safe_get_attribute(driver, 'a[data-item-id="authority"]', "href")
        
        # --- LOGIKA BARU: AMBIL SHORT LINK ---
        try:
            # 1. Cari Tombol Share (Bisa bahasa Indo 'Bagikan' atau Inggris 'Share')
            # Kita cari tombol yang punya data-value="Share" atau icon share
            share_btn = driver.find_elements(By.CSS_SELECTOR, "button[data-value='Share'], button[aria-label*='Bagikan'], button[aria-label*='Share']")
            
            if share_btn:
                # Klik tombol share
                driver.execute_script("arguments[0].click();", share_btn[0])
                
                # 2. Tunggu Dialog Muncul & Cari Input Link
                # Input biasanya ada di dalam dialog modal
                wait = WebDriverWait(driver, 3)
                input_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='dialog'] input.vrsrZe")))
                
                # 3. Ambil value dari input
                short_link = input_el.get_attribute("value")
                info["share_link"] = short_link
                
                # (Opsional) Tutup dialog dengan tekan ESC atau klik tutup, 
                # tapi karena kita akan navigasi ke URL lain/quit setelah ini, tidak wajib.
        except Exception as e:
            # Jangan biarkan error share link menghentikan scraping data lain
            pass

    except:
        return None
        
    return info

# --- SCRAPER TAB 1: INPUT LINK LANGSUNG (Updated) ---
def scrape_single_url_detailed(url):
    driver = get_driver()
    business = None
    try:
        driver.get(url)
        time.sleep(4) 
        
        # Panggil fungsi ekstraksi shared
        details = extract_business_info(driver)
        
        if details:
            business = Business(
                name=details['name'], 
                rating=details['rating'], 
                category=details['category'], 
                address=details['address'], 
                phone=details['phone'],
                website=details['website'], 
                url=driver.current_url,
                share_link=details['share_link'],
                scraped_at_utc=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            )
    finally: driver.quit()
    return [business] if business else []

# --- SCRAPER TAB 1: CARI GLOBAL (Deep Search Updated) ---
def scrape_search_results(query, city="", country="", lat="", lon="", limit=5):
    """
    Sekarang melakukan DEEP SCRAPING untuk setiap hasil pencarian.
    Akan membuka setiap link untuk mengambil detail lengkap.
    """
    results = []
    driver = get_driver(headless=True)
    
    # Progress Bar di Streamlit (karena proses ini butuh waktu)
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        # 1. Lakukan Pencarian
        full_query = f"{query} {city} {country}".strip()
        encoded_query = full_query.replace(' ', '+')
        base_url = f"https://www.google.com/maps/search/{encoded_query}"
        final_url = f"{base_url}/@{lat},{lon},14z" if lat and lon else base_url

        status_text.text(f"🔍 Mencari '{full_query}'...")
        driver.get(final_url)
        time.sleep(5)
        
        # 2. Scroll Feed untuk memuat daftar
        for _ in range(3):
            try:
                driver.execute_script("document.querySelector('div[role=\"feed\"]').scrollBy(0, 2000);")
                time.sleep(2)
            except: pass
            
        # 3. Kumpulkan URL Hasil Pencarian
        listings = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/maps/place/"]')
        found_urls = []
        for l in listings[:limit]:
            url = l.get_attribute("href")
            if url: found_urls.append(url)
            
        status_text.text(f"✅ Ditemukan {len(found_urls)} tempat. Mulai mengambil detail...")
        
        # 4. LOOPING DEEP SCRAPING (Buka satu per satu)
        for i, url in enumerate(found_urls):
            try:
                # Update Progress
                progress = (i + 1) / len(found_urls)
                progress_bar.progress(progress)
                status_text.text(f"⏳ Mengambil data {i+1}/{len(found_urls)}...")
                
                # Navigasi ke URL bisnis tersebut
                driver.get(url)
                time.sleep(3) # Tunggu loading detail
                
                # Ekstraksi Detail
                details = extract_business_info(driver)
                
                if details:
                    results.append(Business(
                        name=details['name'],
                        rating=details['rating'],
                        category=details['category'],
                        address=details['address'],
                        phone=details['phone'],
                        website=details['website'],
                        url=url,
                        share_link=details['share_link'],
                        scraped_at_utc=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    ))
            except Exception as e:
                print(f"Gagal scrape {url}: {e}")
                continue
                
    finally:
        driver.quit()
        progress_bar.empty()
        status_text.empty()
        
    return results

def scrape_reviews_with_ratings(url, num_reviews=30):
    reviews_data = [] 
    seen_texts = set()
    
    # Batch Settings
    BATCH_SIZE = 10  # Proses per 10 ulasan
    
    log_area = st.empty()
    logs = []

    def update_log(msg, type="info"):
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        icon = "✅" if type == "success" else "⚠️" if type == "warn" else "❌" if type == "error" else "ℹ️"
        logs.append(f"[{timestamp}] {icon} {msg}")
        log_area.code("\n".join(logs[-15:]), language="log")

    driver = get_driver(headless=True)
    wait = WebDriverWait(driver, 20)
    
    try:
        update_log(f"Membuka URL...", "info")
        driver.get(url)
        
        # 1. Dismiss Cookies
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[aria-label*="Accept"], button[jsname="hZCF7e"]'))
            ).click()
        except: pass

        # ============================================================
        # NAVIGASI TAB (SAMA SEPERTI SEBELUMNYA - SUDAH STABIL)
        # ============================================================
        update_log("Menyiapkan navigasi...", "info")
        found_tab = False
        
        try:
            # Tunggu Tablist
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="tablist"]')))
            
            # Cek Tab Utama
            tabs = driver.find_elements(By.CSS_SELECTOR, 'div[role="tablist"] button[role="tab"]')
            if not tabs: tabs = driver.find_elements(By.CSS_SELECTOR, 'button[role="tab"]')

            if tabs:
                try: tabs.sort(key=lambda x: int(x.get_attribute("data-tab-index") or 99))
                except: pass

                for tab in tabs:
                    label = (tab.get_attribute("aria-label") or tab.text or "").lower()
                    is_selected = tab.get_attribute("aria-selected") == "true"
                    
                    if any(w in label for w in REVIEW_WORDS) and not any(b in label for b in BAD_WORDS):
                        if is_selected:
                            update_log(f"Tab '{label}' sudah aktif.", "success")
                            found_tab = True
                        else:
                            driver.execute_script("arguments[0].click();", tab)
                            found_tab = True
                            update_log(f"Klik Tab: '{label}'", "success")
                            time.sleep(3)
                        break
            
            # Cek Shortcut jika tab utama gagal
            if not found_tab:
                more_btns = driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='Ulasan'], button[aria-label*='reviews']")
                for btn in more_btns:
                    lbl = btn.get_attribute("aria-label").lower()
                    if ("lainnya" in lbl or "more" in lbl) and "tulis" not in lbl:
                        driver.execute_script("arguments[0].click();", btn)
                        found_tab = True
                        update_log(f"Klik Shortcut: '{lbl}'", "success")
                        time.sleep(3)
                        break

        except Exception as e:
            update_log(f"Navigasi warning: {str(e)}", "warn")

        # 3. CARI PANEL SCROLL & VERIFIKASI
        update_log("Mencari area scroll...", "info")
        pane = None
        
        # Cek tombol urutkan untuk memastikan kita di page ulasan
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'button[aria-label*="Urutkan"], button[data-value="Urutkan"]'))
            )
        except: pass

        target_pane_selector = 'div.m6QErb.DxyBCb.kA9KIf.dS8AEf'
        try:
            pane = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, target_pane_selector)))
        except:
            selectors = ['div[role="main"] div[tabindex="-1"]', 'div[aria-label*="Ulasan"]']
            for sel in selectors:
                try:
                    elems = driver.find_elements(By.CSS_SELECTOR, sel)
                    if elems:
                        pane = elems[0]
                        break
                except: continue

        if not pane: pane = driver.find_element(By.TAG_NAME, "body")

        # ============================================================
        # 4. SCROLLING & EKSTRAKSI DENGAN LOGIKA BATCH (PER 10)
        # ============================================================
        update_log(f"Mulai scraping {num_reviews} data (Mode Batch)...", "info")
        
        consecutive_failures = 0
        last_count = 0
        
        # Loop akan berjalan sampai target tercapai atau error scroll 5x berturut-turut
        while len(reviews_data) < num_reviews:
            
            # 1. Scroll Kebawah
            driver.execute_script("arguments[0].scrollBy(0, 4000);", pane)
            time.sleep(2) # Tunggu loading konten
            
            # 2. Ambil Kartu
            cards = driver.find_elements(By.CSS_SELECTOR, 'div.jftiEf, div[data-review-id]')
            
            # 3. Proses Kartu (Hanya yang baru terlihat di DOM)
            # Tips: Kita iterate reversed (dari bawah ke atas) agar lebih cepat dapat yang baru
            # Tapi untuk urutan data, kita tetap append normal
            
            new_in_batch = 0
            
            for card in cards:
                # Jika kuota terpenuhi, stop loop kartu
                if len(reviews_data) >= num_reviews: break
                
                try:
                    text_content = ""
                    # Cek Teks
                    text_selectors = ['span.wiI7pd', 'div[data-expandable-section]']
                    for txt_sel in text_selectors:
                        try:
                            el = card.find_element(By.CSS_SELECTOR, txt_sel)
                            if el.text.strip():
                                text_content = el.text.strip()
                                break
                        except: continue

                    # Validasi Unik
                    if not text_content or text_content in seen_texts: continue

                    # Klik More jika perlu
                    if "..." in text_content:
                        try:
                            more_btn = card.find_element(By.CSS_SELECTOR, "button.kyuRq")
                            driver.execute_script("arguments[0].click();", more_btn)
                            time.sleep(0.2)
                            text_content = card.find_element(By.CSS_SELECTOR, 'span.wiI7pd').text.strip()
                        except: pass
                    
                    # Ambil Rating
                    rating_val = 0
                    try:
                        star_el = card.find_element(By.CSS_SELECTOR, 'span[role="img"]')
                        label_rating = star_el.get_attribute("aria-label")
                        match = re.search(r'\d+', label_rating)
                        if match: rating_val = int(match.group())
                    except: pass

                    seen_texts.add(text_content)
                    reviews_data.append({"rating": rating_val, "text": text_content})
                    new_in_batch += 1
                    
                except: continue

            # 4. LOGIKA BATCH & BREAK
            current_total = len(reviews_data)
            
            # Cek apakah batch saat ini sudah kelipatan 10 (atau target tercapai)
            if current_total % BATCH_SIZE == 0 and current_total > last_count:
                update_log(f"📦 Batch Selesai: {current_total}/{num_reviews} ulasan terkumpul.", "success")
                # ISTIRAHAT SEBENTAR (PENTING AGAR TIDAK CRASH)
                time.sleep(2) 
            elif current_total != last_count:
                 update_log(f"Progress: {current_total}/{num_reviews}...", "info")

            # Cek Stagnasi (Jika scroll tidak menghasilkan data baru)
            if current_total == last_count:
                consecutive_failures += 1
                update_log(f"Scroll loading... (Percobaan {consecutive_failures}/5)", "warn")
                time.sleep(2) # Tunggu lebih lama jika macet
            else:
                consecutive_failures = 0 # Reset jika ada data baru
                
            last_count = current_total
            
            # Stop jika macet total 5x scroll berturut-turut
            if consecutive_failures >= 5:
                update_log("Tidak ada ulasan baru ditemukan. Berhenti.", "warn")
                break

        update_log(f"🏁 Selesai! {len(reviews_data)} data berhasil diambil.", "success")
            
        if len(reviews_data) == 0:
            update_log("❌ Hasil Kosong. Navigasi gagal atau tidak ada ulasan.", "error")
            update_log("💡 SARAN: Link mungkin expired. Silakan COPY LINK BARU dari Google Maps.", "warn")
        else:
            update_log(f"🏁 Selesai! {len(reviews_data)} data berhasil diambil.", "success")
            
    except Exception as e:
        err = str(e).split("Stacktrace")[0][:100]
        update_log(f"ERROR: {err}", "error")
    finally:
        driver.quit()
        update_log("Browser ditutup.", "info")
    
    return reviews_data


# TAMBAHKAN FUNGSI HELPER BARU INI UNTUK ANALISIS KEYWORD:
def get_keywords(text_series):
    all_text = " ".join(text_series).lower()
    all_text = re.sub(r'[^\w\s]', '', all_text)
    tokens = word_tokenize(all_text)
    stops = set(stopwords.words('indonesian') + stopwords.words('english'))
    custom_stops = {'yg', 'dan', 'di', 'ke', 'dari', 'enak', 'banget', 'tempatnya', 'untuk', 'saya', 'nya', 'ini', 'itu', 'ada', 'juga', 'ga', 'gak', 'mau', 'sih', 'bisa', 'karena', 'tapi'}
    stops.update(custom_stops)
    filtered = [w for w in tokens if w not in stops and len(w) > 3]
    return Counter(filtered).most_common(5)

# --- FUNGSI BARU: ANALISIS MENU MAKANAN ---
def analyze_menu_mentions(text_series):
    """
    Mendeteksi kata yang kemungkinan adalah nama makanan/minuman
    dengan membuang kata sifat, kerja, dan stopwords.
    """
    all_text = " ".join(text_series).lower()
    # Hapus angka dan simbol
    all_text = re.sub(r'[^\w\s]', '', all_text)
    tokens = word_tokenize(all_text)
    
    # 1. Stopwords Dasar (Indo & English)
    stops = set(stopwords.words('indonesian') + stopwords.words('english'))
    
    # 2. Blacklist Kata Umum (Bukan Makanan)
    # Kita buang kata sifat, tempat, pelayanan, dll.
    non_food_words = {
        # Kata Sambung & Umum
        'yg', 'dan', 'di', 'ke', 'dari', 'ini', 'itu', 'ada', 'juga', 'ga', 'gak', 'tidak', 'mau', 
        'sih', 'bisa', 'karena', 'tapi', 'agak', 'cukup', 'buat', 'sama', 'banyak', 'sedikit',
        'lagi', 'sudah', 'belum', 'kalau', 'kalo', 'untuk', 'bagi', 'pada', 'adalah', 'iya',
        
        # Tempat & Fasilitas
        'tempat', 'tempatnya', 'lokasi', 'parkir', 'parkiran', 'toilet', 'wc', 'meja', 'kursi', 
        'ruangan', 'lantai', 'ac', 'indoor', 'outdoor', 'kasir', 'mushola', 'area', 'suasana', 
        'view', 'pemandangan', 'jalan', 'akses', 'mobil', 'motor', 'resto', 'cafe', 'warung',
        
        # Pelayanan & Orang
        'pelayanan', 'pelayan', 'staff', 'karyawan', 'orang', 'mbak', 'mas', 'bapak', 'ibu',
        'satpam', 'waiters', 'owner', 'anak', 'keluarga', 'teman', 'pacar', 'ramah', 'judes',
        'lambat', 'cepat', 'sigap', 'lelet', 'sopan', 'senyum', 'antri', 'antrian',
        
        # Kata Kerja (Aktivitas)
        'makan', 'minum', 'beli', 'pesan', 'order', 'bayar', 'tunggu', 'datang', 'pulang', 
        'buka', 'tutup', 'coba', 'nyoba', 'rasa', 'rasanya', 'bawa', 'kasih', 'dapat', 'lihat',
        
        # Kata Sifat (Kualitas/Harga)
        'enak', 'sedap', 'lezat', 'mantap', 'oke', 'bagus', 'keren', 'jelek', 'parah', 'kecewa',
        'mahal', 'murah', 'terjangkau', 'standar', 'worth', 'bersih', 'kotor', 'bau', 'wangi',
        'panas', 'dingin', 'hangat', 'segar', 'seger', 'manis', 'asin', 'pedas', 'gurih', 
        'pahit', 'hambar', 'empuk', 'keras', 'alot', 'crispy', 'garing', 'lembut',
        
        # Lainnya
        'bintang', 'star', 'review', 'ulasan', 'rekomendasi', 'recommended', 'banget', 'sekali',
        'sangat', 'menu', 'makanan', 'minuman', 'daftar', 'harga', 'total', 'porsi', 'potongan'
    }
    
    stops.update(non_food_words)
    
    # Filter: Ambil kata yang BUKAN stopword dan panjangnya > 2 huruf
    filtered = [w for w in tokens if w not in stops and len(w) > 2]
    
    # Ambil 10 kata terbanyak
    return Counter(filtered).most_common(10)

def analyze_text_data(reviews):
    all_text = " ".join(reviews).lower()
    all_text = re.sub(r'[^\w\s]', '', all_text)
    tokens = word_tokenize(all_text)
    stops = set(stopwords.words('indonesian') + stopwords.words('english'))
    custom_stops = {'yg', 'dan', 'di', 'ke', 'dari', 'enak', 'banget', 'tempatnya', 'untuk', 'saya', 'nya', 'ini', 'itu', 'ada', 'juga', 'ga', 'gak', 'mau', 'sih', 'bisa', 'karena', 'tapi', 'agak', 'cukup'}
    stops.update(custom_stops)
    filtered_words = [w for w in tokens if w not in stops and len(w) > 3]
    word_counts = Counter(filtered_words).most_common(15)
    return word_counts

# --- UI STREAMLIT ---
st.title("📍 MapInsight Pro (Final Version)")
st.markdown("Aplikasi analisis bisnis Google Maps.")

tab1, tab2 = st.tabs(["🔍 Cari Bisnis / Link Detail", "📊 Review Analyzer & Logger"])

# === TAB 1 UI ===
with tab1:
    st.markdown("### 🏢 Database Bisnis")
    mode = st.radio("Metode Input:", ["🔗 Input Link Spesifik", "🔎 Cari Global (Deep Search)"], horizontal=True)
    data = [] 

    if mode == "🔗 Input Link Spesifik":
        st.info("Masukkan link Google Maps (Shortlink/Longlink) untuk mengambil data detail satu tempat.")
        direct_url = st.text_input("Paste Link:", placeholder="https://maps.app.goo.gl/...")
        
        if st.button("Ambil Data Detail", type="primary"):
            if not direct_url:
                st.warning("Link kosong.")
            else:
                with st.spinner("Mengakses link dan mengekstrak data..."):
                    data = scrape_single_url_detailed(direct_url)

    else:
        st.info("Mencari daftar bisnis dan **mengambil detail lengkap** (Alamat, Telp, Rating) untuk setiap hasil.")
        col1, col2 = st.columns([3, 1])
        q_in = col1.text_input("Kata Kunci (e.g. Cafe)", key="q1")
        lim_in = col2.number_input("Limit Hasil", 1, 20, 5, key="l1")
        
        col3, col4 = st.columns(2)
        city_in = col3.text_input("Kota (Opsional)", key="c1")
        country_in = col4.text_input("Negara (Opsional)", key="co1")
        
        if st.button("Jalankan Pencarian", type="primary"):
            if not q_in:
                st.warning("Masukkan kata kunci.")
            else:
                # Fungsi scrape_search_results sekarang sudah ada progress bar di dalamnya
                data = scrape_search_results(q_in, city=city_in, country=country_in, limit=lim_in)

    # --- MENAMPILKAN HASIL TAB 1 ---
    if data:
        st.success(f"Berhasil mengumpulkan {len(data)} data bisnis lengkap!")
        df = pd.DataFrame([asdict(b) for b in data])
        
        # Tampilkan Tabel dengan Kolom Lengkap
        st.dataframe(
            df, 
            column_config={
                "name": "Nama Bisnis",
                "category": "Kategori",
                "rating": "⭐ Rating",
                "phone": "📞 Telepon",
                "address": "🏠 Alamat",
                "url": st.column_config.LinkColumn("Maps Link"), 
                "share_link": st.column_config.LinkColumn("🔗 Short Link (Share)"),
                "website": st.column_config.LinkColumn("Website")
            },
            width="stretch" 
        )
        st.info("💡 Tips: Salin URL dari tabel di atas untuk melakukan analisis ulasan mendalam di Tab 2.")

with tab2:
    st.header("Analisis Sentimen Berbasis Bintang")
    
    col_in, col_opt = st.columns([3, 1])
    target_url = col_in.text_input("URL Google Maps:", placeholder="Paste link di sini...")
    num_rev = col_opt.number_input("Jml Ulasan", 10, 500, 30, step=10)
    
    if st.button("🚀 Mulai Analisis"):
        if not target_url:
            st.warning("Masukkan URL.")
        else:
            st.subheader("1. Live Log")
            # Jalankan Scraper
            raw_data = scrape_reviews_with_ratings(target_url, num_rev)
            
            # CEK APAKAH DATA ADA ATAU KOSONG
            if raw_data:
                df_rev = pd.DataFrame(raw_data)
                
                st.divider()
                st.subheader("2. Dashboard Analisis")
                
                st.write("### 📊 Distribusi Kepuasan")
                rating_counts = df_rev['rating'].value_counts().sort_index()
                st.bar_chart(rating_counts, color="#FFC107")
                
                st.write("### 🧠 Analisis Kata Kunci per Rating")
                
                # Buat Tab untuk setiap Bintang
                star_tabs = st.tabs(["⭐ 1", "⭐ 2", "⭐ 3", "⭐ 4", "⭐ 5"])
                
                for i, star_tab in enumerate(star_tabs):
                    star_val = i + 1
                    subset = df_rev[df_rev['rating'] == star_val]
                    
                    with star_tab:
                        if subset.empty:
                            st.info(f"Belum ada data ulasan bintang {star_val}.")
                        else:
                            st.metric("Jumlah Ulasan", len(subset))
                            
                            # Analisis Keyword Umum
                            keywords = get_keywords(subset['text'])
                            kw_df = pd.DataFrame(keywords, columns=['Kata Kunci', 'Frekuensi'])
                            
                            col_a, col_b = st.columns(2)
                            
                            with col_a:
                                st.write("**Topik Umum:**")
                                st.dataframe(kw_df, use_container_width=True, hide_index=True)
                                
                            with col_b:
                                st.write("**Contoh Ulasan:**")
                                for txt in subset['text'].head(3):
                                    st.caption(f"💬 \"{txt[:150]}...\"")

                            # --- FITUR BARU: EXPANDER DETEKSI MENU ---
                            with st.expander(f"🍽️ Lihat Menu/Makanan yang sering disebut di Bintang {star_val}"):
                                st.caption("Sistem mendeteksi kata benda yang kemungkinan adalah nama makanan/minuman.")
                                
                                # Panggil fungsi analisis menu baru
                                menu_items = analyze_menu_mentions(subset['text'])
                                
                                if menu_items:
                                    menu_df = pd.DataFrame(menu_items, columns=['Nama Menu', 'Disebut (Kali)'])
                                    
                                    # Tampilkan dengan format Bar Chart horizontal agar beda
                                    st.dataframe(menu_df, use_container_width=True, hide_index=True)
                                    
                                    # Opsional: Tampilkan chart kecil
                                    st.bar_chart(menu_df.set_index('Nama Menu'), color="#4CAF50") # Warna hijau utk makanan
                                else:
                                    st.warning("Tidak ditemukan nama menu yang spesifik pada rating ini.")

                with st.expander("📄 Lihat Data Mentah"):
                    st.dataframe(df_rev, use_container_width=True)

            else:
                # INI BAGIAN PESAN ERROR "GANTI LINK"
                st.error("⚠️ Gagal mengambil data ulasan (0 Data).")
                st.warning("""
                **Kemungkinan penyebab:**
                1. **Link Expired/Rusak:** Link Google Maps (terutama shortlink/proxy) sering kadaluarsa.
                2. **Salah Halaman:** Link tidak mengarah ke profil bisnis yang benar.
                
                **👉 SOLUSI: Buka Google Maps lagi, cari tempatnya, Copy Link yang baru, dan coba lagi.**
                """)
# FOOTER
st.markdown("---")
st.caption(f"🕒 UTC Time: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")