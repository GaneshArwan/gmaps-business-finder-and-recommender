import streamlit as st
import pandas as pd
import asyncio
import os
import re
import time
import datetime
import sys
from playwright.async_api import async_playwright
from collections import Counter
import nltk
from nltk.corpus import stopwords
from dataclasses import dataclass, asdict, field

# --- KONFIGURASI AWAL ---
st.set_page_config(page_title="MapInsight AI Scraper", layout="wide")

# FIX UNTUK WINDOWS: Mencegah NotImplementedError pada Python 3.8+ di Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Inisialisasi NLTK untuk pemrosesan bahasa alami
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')
    nltk.download('punkt')

# --- DATA CLASSES ---
@dataclass
class Business:
    """Menyimpan detail data bisnis"""
    name: str = ""
    address: str = ""
    website: str = ""
    phone_number: str = ""
    reviews_average: str = ""
    url: str = ""
    scraped_at_utc: str = ""

@dataclass
class BusinessList:
    """Mengelola daftar bisnis dan konversi ke DataFrame"""
    business_list: list[Business] = field(default_factory=list)
    def dataframe(self):
        return pd.json_normalize((asdict(b) for b in self.business_list), sep="_")

# --- FUNGSI SCRAPER 1: PENCARIAN & EKSTRAKSI DETAIL ---
async def scrape_business_list(search_query, total):
    async with async_playwright() as p:
        # Menjalankan browser secara headless
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = await context.new_page()

        try:
            # Gunakan URL Maps langsung untuk menghindari domain proxy googleusercontent
            search_url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
            await page.goto(search_url, timeout=60000)
            
            # Tunggu elemen hasil pencarian muncul
            try:
                await page.wait_for_selector('a[href*="/maps/place/"]', timeout=15000)
            except:
                st.warning("Tidak ada hasil ditemukan. Periksa kata kunci atau lokasi Anda.")
                return BusinessList()

            business_results = BusinessList()
            previously_counted = 0
            
            # Auto-scroll untuk memuat lebih banyak hasil
            while True:
                await page.mouse.wheel(0, 5000)
                await asyncio.sleep(2)
                current_count = await page.locator('a[href*="/maps/place/"]').count()
                if current_count >= total or current_count == previously_counted:
                    break
                previously_counted = current_count

            listings = await page.locator('a[href*="/maps/place/"]').all()
            
            for listing in listings[:total]:
                try:
                    # KLIK LISTING: Penting untuk memuat detail seperti alamat & telepon
                    await listing.click()
                    await asyncio.sleep(4) # Memberi waktu ekstra agar panel detail dan URL berubah

                    business = Business()
                    
                    # --- LOGIKA CLEAN URL ---
                    # Kita ambil URL langsung dari address bar browser setelah klik listing
                    current_url = page.url
                    if "google.com/maps/place" in current_url:
                        business.url = current_url
                    else:
                        # Fallback: Ambil href asli dan bersihkan domainnya
                        raw_href = await listing.get_attribute('href')
                        if raw_href:
                            business.url = f"https://www.google.com{raw_href.split('?')[0]}"

                    business.scraped_at_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

                    # Ekstraksi Nama Bisnis
                    if await page.locator('h1.DUwDvf').count() > 0:
                        business.name = await page.locator('h1.DUwDvf').first.inner_text()
                    
                    # Ekstraksi Alamat
                    addr_loc = page.locator('//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]')
                    if await addr_loc.count() > 0:
                        business.address = await addr_loc.first.inner_text()

                    # Ekstraksi Website
                    web_loc = page.locator('//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]')
                    if await web_loc.count() > 0:
                        business.website = await web_loc.first.inner_text()

                    # Ekstraksi Telepon
                    phone_loc = page.locator('//button[contains(@data-item-id, "phone")]//div[contains(@class, "fontBodyMedium")]')
                    if await phone_loc.count() > 0:
                        business.phone_number = await phone_loc.first.inner_text()

                    # Ekstraksi Rating
                    rating_loc = page.locator('//div[@jsaction="pane.reviewChart.moreReviews"]//div[@role="img"]')
                    if await rating_loc.count() > 0:
                        rating_text = await rating_loc.first.get_attribute('aria-label')
                        business.reviews_average = rating_text.split()[0] if rating_text else ""

                    business_results.business_list.append(business)
                except:
                    continue
            
            await browser.close()
            return business_results
        except Exception as e:
            st.error(f"Error Scrapping: {e}")
            await browser.close()
            return BusinessList()

# --- FUNGSI SCRAPER 2: ANALISIS ULASAN ---
async def scrape_and_analyze_reviews(url, num_reviews=50):
    reviews_text = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, timeout=60000)
            
            # Tutup Pop-up Cookie
            try:
                cookie_button = page.get_by_role("button", name=re.compile("Reject all|Tolak semua|Accept all|Setuju", re.IGNORECASE))
                await cookie_button.first.click(timeout=5000)
            except: pass

            # Klik tab ulasan
            try:
                review_btn = page.get_by_text(re.compile(r'\d+ ulasan|\d+ reviews', re.IGNORECASE)).first
                await review_btn.click(timeout=10000)
            except:
                st.warning("Gagal menemukan tab ulasan. Coba URL lain.")
                return []

            # Scroll untuk memuat ulasan
            scroll_panel = 'div.m6QErb.DxyBCb'
            await page.wait_for_selector(scroll_panel, timeout=10000)
            for _ in range(int(num_reviews/10)):
                await page.locator(scroll_panel).first.evaluate('(el) => el.scrollTop = el.scrollHeight')
                await asyncio.sleep(2)

            # Ekstrak ulasan
            elements = await page.locator('span.wiI7pd').all()
            for el in elements:
                reviews_text.append(await el.inner_text())
                
        except Exception as e:
            st.error(f"Error Review: {e}")
        finally:
            await browser.close()
    return reviews_text

# --- LOGIKA REKOMENDASI ---
def get_recommendations(reviews):
    if not reviews: return []
    text = ' '.join(reviews).lower()
    text = re.sub(r'[^a-z\s]', '', text)
    words = nltk.word_tokenize(text)
    
    stop_words = set(stopwords.words('indonesian'))
    custom_stops = {'yg', 'dan', 'di', 'ke', 'dari', 'enak', 'banget', 'mantap', 'disini', 'saya', 'pesan', 'makan', 'minum', 'tempatnya', 'rasanya'}
    stop_words.update(custom_stops)
    
    filtered = [w for w in words if w not in stop_words and len(w) > 3]
    return Counter(filtered).most_common(10)

# --- ANTARMUKA STREAMLIT ---
st.title("📍 MapInsight AI Scraper")

tab1, tab2 = st.tabs(["🔍 Search Business", "⭐ Review Analyzer"])

with tab1:
    st.subheader("Cari Bisnis & Lokasi")
    
    col_input1, col_input2 = st.columns([3, 1])
    with col_input1:
        base_query = st.text_input("Kategori / Bisnis (Wajib)", placeholder="e.g. Coffee Shop, Barber Shop")
    with col_input2:
        limit = st.number_input("Jumlah Hasil", min_value=1, max_value=50, value=5)

    st.markdown("---")
    st.caption("📍 Detail Lokasi Opsional")
    l_col1, l_col2 = st.columns(2)
    with l_col1:
        city = st.text_input("Kota", placeholder="e.g. Jakarta Selatan")
    with l_col2:
        country = st.text_input("Negara", placeholder="e.g. Indonesia")

    c_col1, c_col2 = st.columns(2)
    with c_col1:
        lat = st.text_input("Latitude", placeholder="e.g. -6.2088")
    with c_col2:
        long = st.text_input("Longitude", placeholder="e.g. 106.8456")

    if st.button("Start Searching"):
        if not base_query:
            st.error("Isi kategori bisnis terlebih dahulu!")
        else:
            # Bangun kueri pencarian otomatis
            full_query = base_query
            if city: full_query += f" in {city}"
            if country: full_query += f" {country}"
            if lat and long: full_query += f" near {lat}, {long}"
            
            with st.spinner(f"Mencari '{full_query}'..."):
                results = asyncio.run(scrape_business_list(full_query, limit))
                st.session_state['search_results'] = results.dataframe()
                st.success(f"Ditemukan {len(results.business_list)} hasil!")

    if 'search_results' in st.session_state:
        # Menggunakan width='stretch' sebagai pengganti use_container_width
        st.dataframe(st.session_state['search_results'], width='stretch')
        st.info("💡 Salin URL di atas ke Tab 2 untuk analisis ulasan.")

with tab2:
    st.subheader("Analisis Menu Berdasarkan Ulasan")
    target_url = st.text_input("Masukkan Clean URL dari Tab 1:")
    
    num_rev = st.slider("Jumlah ulasan untuk dianalisis", 10, 100, 50)
    
    if st.button("Analyze & Recommend"):
        if not target_url:
            st.error("Masukkan URL terlebih dahulu!")
        else:
            with st.spinner("Menganalisis ulasan favorit pelanggan..."):
                reviews = asyncio.run(scrape_and_analyze_reviews(target_url, num_rev))
                recs = get_recommendations(reviews)
                
                if recs:
                    st.success("Selesai!")
                    st.write("### 🍴 Rekomendasi Populer:")
                    for i, (item, count) in enumerate(recs):
                        st.write(f"{i+1}. **{item.capitalize()}** (disebut dalam {count} ulasan)")
                else:
                    st.warning("Tidak cukup data ulasan.")

# --- FOOTER ---
st.markdown("---")
st.caption(f"🕒 UTC System Time: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")