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
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory
from dataclasses import dataclass, asdict

st.set_page_config(page_title="MapInsight Pro — Places & Reviews", layout="wide")

logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("scraper")

@st.cache_resource
def init_nlp_resources():
    try:
        nltk.download('stopwords', quiet=True)
        nltk.download('punkt', quiet=True)
        nltk.download('punkt_tab', quiet=True)
    except LookupError:
        pass

    stemmer_factory = StemmerFactory()
    stemmer = stemmer_factory.create_stemmer()

    stop_factory = StopWordRemoverFactory()
    sastrawi_stops = set(stop_factory.get_stop_words())

    return stemmer, sastrawi_stops

STEMMER, SASTRAWI_STOPS = init_nlp_resources()

@dataclass
class Business:
    name: str = ""
    rating: str = ""
    category: str = ""
    address: str = ""
    phone: str = ""
    website: str = ""
    url: str = ""
    share_link: str = ""
    scraped_at_utc: str = ""

REVIEW_WORDS = {"ulasan", "reviews", "review", "tinjauan", "reseñas", "avis", "bewertungen", "recensioni"}
BAD_WORDS = {"tulis", "write", "nulis", "add", "tambahkan", "crear", "schreiben"}

def get_driver(headless=True):
    driver = Driver(uc=True, headless=headless, incognito=True)
    driver.set_window_size(1400, 900)
    return driver

def safe_get_text(driver, selector):
    try:
        return driver.find_element(By.CSS_SELECTOR, selector).text.strip()
    except:
        return ""

def safe_get_attribute(driver, selector, attr):
    try:
        return driver.find_element(By.CSS_SELECTOR, selector).get_attribute(attr)
    except:
        return ""

def extract_business_info(driver):
    """Extracts business details INCLUDING Short Link from the Share button"""
    info = {"name": "", "rating": "", "category": "", "address": "", "phone": "", "website": "", "share_link": ""}

    try:
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1.DUwDvf")))

        info["name"] = safe_get_text(driver, "h1.DUwDvf")
        info["rating"] = safe_get_text(driver, "div.F7nice span[aria-hidden='true']")
        info["category"] = safe_get_text(driver, "button.DkEaL")

        address = safe_get_attribute(driver, 'button[data-item-id="address"]', "aria-label")
        if address:
            info["address"] = address.replace("Address: ", "").replace("Alamat: ", "")

        phone = safe_get_attribute(driver, 'button[data-item-id*="phone"]', "aria-label")
        if phone:
            info["phone"] = phone.replace("Phone: ", "").replace("Telepon: ", "")

        info["website"] = safe_get_attribute(driver, 'a[data-item-id="authority"]', "href")

        try:
            share_btn = driver.find_elements(By.CSS_SELECTOR, "button[data-value='Share'], button[aria-label*='Bagikan'], button[aria-label*='Share']")
            if share_btn:
                driver.execute_script("arguments[0].click();", share_btn[0])
                wait = WebDriverWait(driver, 3)
                input_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='dialog'] input.vrsrZe")))
                short_link = input_el.get_attribute("value")
                info["share_link"] = short_link
        except Exception:
            pass

    except:
        return None

    return info

def scrape_single_url_detailed(url):
    driver = get_driver()
    business = None
    try:
        driver.get(url)
        time.sleep(4)

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
                scraped_at_utc=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            )
    finally:
        driver.quit()
    return [business] if business else []

def scrape_search_results(query, city="", country="", lat="", lon="", limit=5):
    """Performs deep scraping for each search result and returns detailed Business objects."""
    results = []
    driver = get_driver(headless=True)

    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        full_query = f"{query} {city} {country}".strip()
        encoded_query = full_query.replace(' ', '+')
        base_url = f"https://www.google.com/maps/search/{encoded_query}"
        final_url = f"{base_url}/@{lat},{lon},14z" if lat and lon else base_url

        status_text.text(f"🔍 Searching for '{full_query}'...")
        driver.get(final_url)
        time.sleep(5)

        for _ in range(3):
            try:
                driver.execute_script("document.querySelector('div[role=\"feed\"]').scrollBy(0, 2000);")
                time.sleep(2)
            except:
                pass

        listings = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/maps/place/"]')
        found_urls = []
        for l in listings[:limit]:
            url = l.get_attribute("href")
            if url:
                found_urls.append(url)

        status_text.text(f"✅ Found {len(found_urls)} places. Starting to extract details...")

        for i, url in enumerate(found_urls):
            try:
                progress = (i + 1) / len(found_urls)
                progress_bar.progress(progress)
                status_text.text(f"⏳ Extracting data {i+1}/{len(found_urls)}...")

                driver.get(url)
                time.sleep(10)

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
                        scraped_at_utc=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    ))
            except Exception as e:
                print(f"Failed to scrape {url}: {e}")
                continue

    finally:
        driver.quit()
        progress_bar.empty()
        status_text.empty()

    return results

def scrape_reviews_with_ratings(url, num_reviews=30):
    reviews_data = []
    seen_texts = set()

    BATCH_SIZE = 10

    log_area = st.empty()
    logs = []

    def update_log(msg, type="info"):
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        icon = "✅" if type == "success" else "⚠️" if type == "warn" else "❌" if type == "error" else "ℹ️"
        logs.append(f"[{timestamp}] {icon} {msg}")
        log_area.code("\n".join(logs[-15:]), language="log")

    driver = get_driver(headless=True)
    wait = WebDriverWait(driver, 30)

    try:
        update_log("Opening URL...", "info")
        driver.get(url)

        try:
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[aria-label*="Accept"], button[jsname="hZCF7e"]'))
            ).click()
        except:
            pass

        update_log("Preparing navigation...", "info")
        found_tab = False

        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="tablist"]')))

            tabs = driver.find_elements(By.CSS_SELECTOR, 'div[role="tablist"] button[role="tab"]')
            if not tabs:
                tabs = driver.find_elements(By.CSS_SELECTOR, 'button[role="tab"]')

            if tabs:
                try:
                    tabs.sort(key=lambda x: int(x.get_attribute("data-tab-index") or 99))
                except:
                    pass

                for tab in tabs:
                    label = (tab.get_attribute("aria-label") or tab.text or "").lower()
                    is_selected = tab.get_attribute("aria-selected") == "true"

                    if any(w in label for w in REVIEW_WORDS) and not any(b in label for b in BAD_WORDS):
                        if is_selected:
                            update_log(f"Tab '{label}' is already active.", "success")
                            found_tab = True
                        else:
                            driver.execute_script("arguments[0].click();", tab)
                            found_tab = True
                            update_log(f"Clicked Tab: '{label}'", "success")
                            time.sleep(3)
                        break

            if not found_tab:
                more_btns = driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='Ulasan'], button[aria-label*='reviews']")
                for btn in more_btns:
                    lbl = btn.get_attribute("aria-label").lower()
                    if ("lainnya" in lbl or "more" in lbl) and "tulis" not in lbl:
                        driver.execute_script("arguments[0].click();", btn)
                        found_tab = True
                        update_log(f"Clicked Shortcut: '{lbl}'", "success")
                        time.sleep(3)
                        break

        except Exception as e:
            update_log(f"Navigation warning: {str(e)}", "warn")

        update_log("Looking for scroll area...", "info")
        pane = None

        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'button[aria-label*="Urutkan"], button[data-value="Urutkan"]'))
            )
        except:
            pass

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
                except:
                    continue

        if not pane:
            pane = driver.find_element(By.TAG_NAME, "body")

        update_log(f"Starting scrape of {num_reviews} reviews (Batch Mode)...", "info")

        consecutive_failures = 0
        last_count = 0

        while len(reviews_data) < num_reviews:
            driver.execute_script("arguments[0].scrollBy(0, 4000);", pane)
            time.sleep(2)

            cards = driver.find_elements(By.CSS_SELECTOR, 'div.jftiEf, div[data-review-id]')

            new_in_batch = 0

            for card in cards:
                if len(reviews_data) >= num_reviews:
                    break

                try:
                    text_content = ""
                    text_selectors = ['span.wiI7pd', 'div[data-expandable-section]']
                    for txt_sel in text_selectors:
                        try:
                            el = card.find_element(By.CSS_SELECTOR, txt_sel)
                            if el.text.strip():
                                text_content = el.text.strip()
                                break
                        except:
                            continue

                    if not text_content or text_content in seen_texts:
                        continue

                    if "..." in text_content:
                        try:
                            more_btn = card.find_element(By.CSS_SELECTOR, "button.kyuRq")
                            driver.execute_script("arguments[0].click();", more_btn)
                            time.sleep(0.2)
                            text_content = card.find_element(By.CSS_SELECTOR, 'span.wiI7pd').text.strip()
                        except:
                            pass

                    rating_val = 0
                    try:
                        star_el = card.find_element(By.CSS_SELECTOR, 'span[role="img"]')
                        label_rating = star_el.get_attribute("aria-label")
                        match = re.search(r'\d+', label_rating)
                        if match:
                            rating_val = int(match.group())
                    except:
                        pass

                    seen_texts.add(text_content)
                    reviews_data.append({"rating": rating_val, "text": text_content})
                    new_in_batch += 1

                except:
                    continue

            current_total = len(reviews_data)

            if current_total % BATCH_SIZE == 0 and current_total > last_count:
                update_log(f"📦 Batch Complete: {current_total}/{num_reviews} reviews collected.", "success")
                time.sleep(2)
            elif current_total != last_count:
                update_log(f"Progress: {current_total}/{num_reviews}...", "info")

            if current_total == last_count:
                consecutive_failures += 1
                update_log(f"Scroll loading... (Attempt {consecutive_failures}/5)", "warn")
                time.sleep(2)
            else:
                consecutive_failures = 0

            last_count = current_total

            if consecutive_failures >= 5:
                update_log("No new reviews found. Stopping.", "warn")
                break

        update_log(f"🏁 Finished! {len(reviews_data)} data successfully collected.", "success")

        if len(reviews_data) == 0:
            update_log("❌ Empty Result. Navigation failed or no reviews.", "error")
            update_log("💡 SUGGESTION: Link might be expired. Please COPY NEW LINK from Google Maps.", "warn")
        else:
            update_log(f"🏁 Finished! {len(reviews_data)} data successfully collected.", "success")

    except Exception as e:
        err = str(e).split("Stacktrace")[0][:100]
        update_log(f"ERROR: {err}", "error")
    finally:
        driver.quit()
        update_log("Browser closed.", "info")

    return reviews_data


# HELPER FUNCTION FOR KEYWORD ANALYSIS
def get_keywords(text_series):
    all_text = " ".join(text_series).lower()
    all_text = re.sub(r'[^\w\s]', '', all_text)
    tokens = word_tokenize(all_text)
    stops = set(stopwords.words('indonesian') + stopwords.words('english'))
    stops.update(SASTRAWI_STOPS)
    # Added English stop words to custom list
    custom_stops = {
        'yg', 'dan', 'di', 'ke', 'dari', 'enak', 'banget', 'tempatnya', 'untuk', 'saya', 'nya', 
        'ini', 'itu', 'ada', 'juga', 'ga', 'gak', 'mau', 'sih', 'bisa', 'karena', 'tapi',
        'the', 'and', 'is', 'to', 'in', 'of', 'it', 'for', 'with', 'on', 'was', 'very', 'place', 'this', 'that'
    }
    stops.update(custom_stops)
    filtered_and_stemmed = []
    for w in tokens:
        if w not in stops and len(w) > 3:
            # Apply stemming
            stemmed_word = STEMMER.stem(w)
            # Only add if the stemmed word is also not a stopword and long enough
            if stemmed_word not in stops and len(stemmed_word) > 2:
                filtered_and_stemmed.append(stemmed_word)
                
    return Counter(filtered_and_stemmed).most_common(5)

# --- NEW FUNCTION: MENU ANALYSIS ---
def analyze_menu_mentions(text_series):
    """
    Detects nouns likely to be food/drink names by removing adjectives, verbs, and stopwords.
    """
    all_text = " ".join(text_series).lower()
    # Remove numbers and symbols
    all_text = re.sub(r'[^\w\s]', '', all_text)
    tokens = word_tokenize(all_text)
    
    # 1. Basic Stopwords (Indo & English)
    stops = set(stopwords.words('indonesian') + stopwords.words('english'))
    stops.update(SASTRAWI_STOPS)
    
    # 2. Blacklist Common Words (Non-Food)
    # Removing adjectives, places, service, etc. (Includes English equivalents now)
    non_food_words = {
        # Conjunctions & General
        'yg', 'dan', 'di', 'ke', 'dari', 'ini', 'itu', 'ada', 'juga', 'ga', 'gak', 'tidak', 'mau', 
        'sih', 'bisa', 'karena', 'tapi', 'agak', 'cukup', 'buat', 'sama', 'banyak', 'sedikit',
        'lagi', 'sudah', 'belum', 'kalau', 'kalo', 'untuk', 'bagi', 'pada', 'adalah', 'iya',
        'the', 'and', 'is', 'to', 'in', 'of', 'it', 'for', 'with', 'on', 'was', 'very', 'but', 'so',
        
        # Place & Facilities
        'tempat', 'tempatnya', 'lokasi', 'parkir', 'parkiran', 'toilet', 'wc', 'meja', 'kursi', 
        'ruangan', 'lantai', 'ac', 'indoor', 'outdoor', 'kasir', 'mushola', 'area', 'suasana', 
        'view', 'pemandangan', 'jalan', 'akses', 'mobil', 'motor', 'resto', 'cafe', 'warung',
        'place', 'location', 'parking', 'table', 'chair', 'room', 'floor', 'cashier', 'area', 
        'atmosphere', 'view', 'road', 'access', 'car', 'bike', 'restaurant',
        
        # Service & People
        'pelayanan', 'pelayan', 'staff', 'karyawan', 'orang', 'mbak', 'mas', 'bapak', 'ibu',
        'satpam', 'waiters', 'owner', 'anak', 'keluarga', 'teman', 'pacar', 'ramah', 'judes',
        'lambat', 'cepat', 'sigap', 'lelet', 'sopan', 'senyum', 'antri', 'antrian',
        'service', 'waiter', 'waitress', 'employee', 'people', 'man', 'woman', 'security', 
        'owner', 'kid', 'family', 'friend', 'friendly', 'rude', 'slow', 'fast', 'polite', 'queue',
        
        # Verbs (Activities)
        'makan', 'minum', 'beli', 'pesan', 'order', 'bayar', 'tunggu', 'datang', 'pulang', 
        'buka', 'tutup', 'coba', 'nyoba', 'rasa', 'rasanya', 'bawa', 'kasih', 'dapat', 'lihat',
        'eat', 'drink', 'buy', 'order', 'pay', 'wait', 'come', 'go', 'open', 'close', 'try', 
        'taste', 'bring', 'give', 'get', 'see',
        
        # Adjectives (Quality/Price)
        'enak', 'sedap', 'lezat', 'mantap', 'oke', 'bagus', 'keren', 'jelek', 'parah', 'kecewa',
        'mahal', 'murah', 'terjangkau', 'standar', 'worth', 'bersih', 'kotor', 'bau', 'wangi',
        'panas', 'dingin', 'hangat', 'segar', 'seger', 'manis', 'asin', 'pedas', 'gurih', 
        'pahit', 'hambar', 'empuk', 'keras', 'alot', 'crispy', 'garing', 'lembut',
        'good', 'delicious', 'tasty', 'nice', 'great', 'bad', 'terrible', 'disappointed',
        'expensive', 'cheap', 'affordable', 'standard', 'clean', 'dirty', 'smell',
        'hot', 'cold', 'warm', 'fresh', 'sweet', 'salty', 'spicy', 'savory', 
        'bitter', 'plain', 'soft', 'hard', 'tough', 'crispy', 'tender',
        
        # Others
        'bintang', 'star', 'review', 'ulasan', 'rekomendasi', 'recommended', 'banget', 'sekali',
        'sangat', 'menu', 'makanan', 'minuman', 'daftar', 'harga', 'total', 'porsi', 'potongan',
        'stars', 'recommendation', 'very', 'much', 'food', 'drink', 'list', 'price', 'portion'
    }
    
    stops.update(non_food_words)
    
    # Filter: Get words that are NOT stopword and length > 2
    filtered = [w for w in tokens if w not in stops and len(w) > 2]
    
    # Get top 10 most common
    return Counter(filtered).most_common(10)

def analyze_text_data(reviews):
    all_text = " ".join(reviews).lower()
    all_text = re.sub(r'[^\w\s]', '', all_text)
    tokens = word_tokenize(all_text)
    stops = set(stopwords.words('indonesian') + stopwords.words('english'))
    stops.update(SASTRAWI_STOPS)
    custom_stops = {'yg', 'dan', 'di', 'ke', 'dari', 'enak', 'banget', 'tempatnya', 'untuk', 'saya', 'nya', 'ini', 'itu', 'ada', 'juga', 'ga', 'gak', 'mau', 'sih', 'bisa', 'karena', 'tapi', 'agak', 'cukup'}
    stops.update(custom_stops)
    filtered_words = [w for w in tokens if w not in stops and len(w) > 3]
    word_counts = Counter(filtered_words).most_common(15)
    return word_counts

# --- STREAMLIT UI ---
st.title("📍 MapInsight Pro — Places & Reviews")
st.markdown("Google Maps places & reviews analysis — businesses, restaurants, shops.")

tab1, tab2 = st.tabs(["🔍 Search Places / Link Detail", "📊 Review Analyzer & Logger"])

# === TAB 1 UI ===
with tab1:
    st.markdown("### 📚 Places Database")
    mode = st.radio("Input Method:", ["🔗 Specific Link Input", "🔎 Global Search (Deep Search)"], horizontal=True)
    data = [] 

    if mode == "🔗 Specific Link Input":
        st.info("Enter Google Maps link (Shortlink/Longlink) to fetch detailed data for one place.")
        direct_url = st.text_input("Paste Link:", placeholder="https://maps.app.goo.gl/...")
        
        if st.button("Fetch Detailed Data", type="primary"):
            if not direct_url:
                st.warning("Link is empty.")
            else:
                with st.spinner("Accessing link and extracting data..."):
                    data = scrape_single_url_detailed(direct_url)

    else:
        st.info("Search for places (businesses, restaurants, shops) and **fetch full details** (Address, Phone, Rating) for each result.")
        col1, col2 = st.columns([3, 1])
        q_in = col1.text_input("Keywords (e.g. Cafe)", key="q1")
        lim_in = col2.number_input("Limit Results", 1, 20, 5, key="l1")
        
        col3, col4 = st.columns(2)
        city_in = col3.text_input("City (Optional)", key="c1")
        country_in = col4.text_input("Country (Optional)", key="co1")
        
        if st.button("Run Search", type="primary"):
            if not q_in:
                st.warning("Enter keywords.")
            else:
                # Scrape function already has progress bar
                data = scrape_search_results(q_in, city=city_in, country=country_in, limit=lim_in)

    # --- DISPLAY RESULTS TAB 1 ---
    if data:
        st.success(f"Successfully collected {len(data)} place records!")
        df = pd.DataFrame([asdict(b) for b in data])
        
        # Display Table with Full Columns
        st.dataframe(
            df, 
            column_config={
                "name": "Place Name",
                "category": "Category",
                "rating": "⭐ Rating",
                "phone": "📞 Phone",
                "address": "🏠 Address",
                "url": st.column_config.LinkColumn("Maps Link"), 
                "share_link": st.column_config.LinkColumn("🔗 Short Link (Share)"),
                "website": st.column_config.LinkColumn("Website")
            },
            width="stretch" 
        )
        st.info("💡 Tip: Copy URL from the table above to perform deep review analysis in Tab 2.")

with tab2:
    st.header("Star-Based Sentiment Analysis")
    
    col_in, col_opt = st.columns([3, 1])
    target_url = col_in.text_input("Google Maps URL:", placeholder="Paste link here...")
    num_rev = col_opt.number_input("Num Reviews", 10, 500, 30, step=10)
    
    if st.button("🚀 Start Analysis"):
        if not target_url:
            st.warning("Enter URL.")
        else:
            st.subheader("1. Live Log")
            # Run Scraper
            raw_data = scrape_reviews_with_ratings(target_url, num_rev)
            
            # CHECK IF DATA EXISTS OR EMPTY
            if raw_data:
                df_rev = pd.DataFrame(raw_data)
                
                st.divider()
                st.subheader("2. Analysis Dashboard")
                
                st.write("### 📊 Satisfaction Distribution")
                rating_counts = df_rev['rating'].value_counts().sort_index()
                st.bar_chart(rating_counts, color="#FFC107")
                
                st.write("### 🧠 Keyword Analysis per Rating")
                
                # Create Tab for each Star
                star_tabs = st.tabs(["⭐ 1", "⭐ 2", "⭐ 3", "⭐ 4", "⭐ 5"])
                
                for i, star_tab in enumerate(star_tabs):
                    star_val = i + 1
                    subset = df_rev[df_rev['rating'] == star_val]
                    
                    with star_tab:
                        if subset.empty:
                            st.info(f"No review data for {star_val} star(s).")
                        else:
                            st.metric("Total Reviews", len(subset))
                            
                            # General Keyword Analysis
                            keywords = get_keywords(subset['text'])
                            kw_df = pd.DataFrame(keywords, columns=['Keyword', 'Frequency'])
                            
                            col_a, col_b = st.columns(2)
                            
                            with col_a:
                                st.write("**General Topics:**")
                                st.dataframe(kw_df, width="stretch", hide_index=True)
                                
                            with col_b:
                                st.write("**Review Examples:**")
                                for txt in subset['text'].head(3):
                                    st.caption(f"💬 \"{txt[:150]}...\"")

                            # --- MENU DETECTION EXPANDER ---
                            with st.expander(f"🍽️ View Menu/Food mentioned in ⭐ {star_val}"):
                                st.caption("System detects nouns likely to be food/drink names.")
                                
                                # Call menu analysis function
                                menu_items = analyze_menu_mentions(subset['text'])
                                
                                if menu_items:
                                    menu_df = pd.DataFrame(menu_items, columns=['Menu Name', 'Mentioned (Times)'])
                                    
                                    # Display with Horizontal Bar Chart format
                                    st.dataframe(menu_df, width="stretch", hide_index=True)
                                    
                                    # Optional: Display small chart
                                    st.bar_chart(menu_df.set_index('Menu Name'), color="#4CAF50") # Green for food
                                else:
                                    st.warning("No specific menu names found in this rating.")

                with st.expander("📄 View Raw Data"):
                    st.dataframe(df_rev, width="stretch")

            else:
                # ERROR MESSAGE SECTION
                st.error("⚠️ Failed to fetch review data (0 Data).")
                st.warning("""
                **Possible causes:**
                1. **Link Expired/Broken:** Google Maps links (especially shortlinks/proxies) often expire.
                2. **Wrong Page:** Link does not point to a correct business profile.

                **👉 SOLUTION: Open Google Maps by link, find the share button, Copy Short Link, and Paste it again.**
                """)
# FOOTER
st.markdown("---")
st.caption(f"🕒 UTC Time: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")