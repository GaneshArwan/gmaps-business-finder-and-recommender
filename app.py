import streamlit as st
import pandas as pd
import time
import re
import datetime
import sys
from seleniumbase import Driver
from selenium.webdriver.common.by import By
from collections import Counter
import nltk
from nltk.corpus import stopwords
from dataclasses import dataclass, asdict, field

# --- KONFIGURASI AWAL ---
st.set_page_config(page_title="MapInsight Pro Scraper", layout="wide")

# Inisialisasi NLTK
@st.cache_resource
def init_nltk():
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords')
        nltk.download('punkt')

init_nltk()

# Data Class Bisnis (SOP MapInsight)
@dataclass
class Business:
    name: str = ""
    address: str = ""
    website: str = ""
    phone: str = ""
    rating: str = ""
    url: str = ""
    scraped_at_utc: str = ""

# Kata kunci ulasan multi-bahasa dari scraper pro
REVIEW_WORDS = {
    "reviews", "review", "ulasan", "tinjauan", "komentar", "penilaian", 
    "ratings", "rating", "avis", "reseñas", "recensioni", "bewertungen"
}

# --- FUNGSI SCRAPER UTAMA (Inspirasi dari scraper.py & models.py) ---
def get_driver(headless=True):
    # Menggunakan SeleniumBase UC Mode untuk anti-detection
    return Driver(uc=True, headless=headless, incognito=True)

def scrape_search_results(query, limit=5):
    """Mencari daftar bisnis di Tab 1"""
    results = []
    driver = get_driver()
    try:
        search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
        driver.get(search_url)
        time.sleep(5)
        
        # Auto-scroll untuk memuat hasil
        for _ in range(3):
            driver.execute_script("document.querySelector('div[role=\"feed\"]').scrollBy(0, 2000);")
            time.sleep(2)
            
        listings = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/maps/place/"]')
        for listing in listings[:limit]:
            try:
                name = listing.get_attribute("aria-label")
                url = listing.get_attribute("href")
                if name and url:
                    results.append(Business(name=name, url=url, scraped_at_utc=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
            except: continue
    finally:
        driver.quit()
    return results

def scrape_detailed_reviews(url, num_reviews=30):
    """Analisis ulasan mendalam di Tab 2 menggunakan logika Pro Scraper"""
    reviews_list = []
    driver = get_driver()
    try:
        driver.get(url)
        time.sleep(5)
        
        # 1. Dismiss Cookies
        for btn_selector in ['button[aria-label*="Accept" i]', 'button[jsname="hZCF7e"]']:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, btn_selector)
                for el in elements:
                    if el.is_displayed(): el.click()
            except: pass

        # 2. Klik Tab Ulasan (Logika Multi-bahasa dari scraper.py)
        found_tab = False
        tabs = driver.find_elements(By.CSS_SELECTOR, '[role="tab"], button')
        for tab in tabs:
            label = (tab.get_attribute("aria-label") or tab.text or "").lower()
            if any(word in label for word in REVIEW_WORDS):
                driver.execute_script("arguments[0].click();", tab)
                found_tab = True
                break
        
        if not found_tab:
            st.error("Gagal menemukan tab ulasan. Mencoba navigasi langsung...")
            if "/place/" in url:
                driver.get(url.split('?')[0] + "/reviews")
        
        time.sleep(3)
        
        # 3. Scrolling (PANE_SEL dari scraper.py)
        pane_selector = 'div.m6QErb.DxyBCb.kA9KIf.dS8AEf'
        for _ in range(int(num_reviews/10) + 1):
            try:
                driver.execute_script(f"document.querySelector('{pane_selector}').scrollBy(0, 3000);")
                time.sleep(2)
            except: break

        # 4. Ekstrak Teks (wiI7pd dari models.py)
        cards = driver.find_elements(By.CSS_SELECTOR, 'div[data-review-id]')
        for card in cards[:num_reviews]:
            try:
                # Expand "More" button
                try:
                    more_btn = card.find_element(By.CSS_SELECTOR, "button.kyuRq")
                    driver.execute_script("arguments[0].click();", more_btn)
                except: pass
                
                text_el = card.find_element(By.CSS_SELECTOR, 'span.wiI7pd')
                if text_el.text:
                    reviews_list.append(text_el.text)
            except: continue
            
    finally:
        driver.quit()
    return reviews_list

# --- UI STREAMLIT ---
st.title("📍 MapInsight Pro (No-DB Version)")
st.markdown("Aplikasi analisis bisnis menggunakan SeleniumBase UC Mode untuk hasil paling akurat.")

tab1, tab2 = st.tabs(["🔍 Search Business", "⭐ Review Analyzer"])

with tab1:
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Cari Bisnis (e.g. Cafe di Jakarta Selatan)")
    with col2:
        limit = st.number_input("Limit Hasil", 1, 50, 5)
    
    if st.button("Jalankan Pencarian"):
        with st.spinner("Mencari tempat..."):
            data = scrape_search_results(query, limit)
            if data:
                df = pd.DataFrame([asdict(b) for b in data])
                st.session_state['search_results'] = df
                st.success(f"Ditemukan {len(data)} tempat!")
            else:
                st.error("Tidak ada hasil.")

    if 'search_results' in st.session_state:
        st.dataframe(st.session_state['search_results'], width='stretch')
        st.info("💡 Copy URL dari tabel di atas untuk digunakan di Tab 'Review Analyzer'.")

with tab2:
    target_url = st.text_input("Masukkan URL Google Maps:")
    num_rev = st.slider("Jumlah ulasan yang dianalisis", 10, 100, 30)
    
    if st.button("Mulai Analisis AI"):
        if not target_url:
            st.warning("Masukkan URL terlebih dahulu.")
        else:
            with st.spinner("Mengekstrak ulasan (On Progress)..."):
                raw_reviews = scrape_detailed_reviews(target_url, num_rev)
                
                if raw_reviews:
                    st.success(f"Berhasil menganalisis {len(raw_reviews)} ulasan!")
                    
                    # Analisis Frekuensi Kata (BAU)
                    all_text = " ".join(raw_reviews).lower()
                    words = nltk.word_tokenize(re.sub(r'[^a-z\s]', '', all_text))
                    stop_words = set(stopwords.words('indonesian'))
                    stop_words.update(['yg', 'dan', 'di', 'ke', 'dari', 'enak', 'banget', 'tempatnya', 'untuk', 'saya'])
                    
                    filtered = [w for w in words if w not in stop_words and len(w) > 3]
                    common = Counter(filtered).most_common(10)
                    
                    st.subheader("🍴 Rekomendasi Menu / Kata Kunci Populer:")
                    for i, (word, count) in enumerate(common):
                        st.write(f"{i+1}. **{word.capitalize()}** (disebut {count} kali)")
                else:
                    st.error("Gagal mendapatkan ulasan. Pastikan URL valid.")

# FOOTER
st.markdown("---")
st.caption(f"🕒 UTC Time: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")