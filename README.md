# 📍 MapInsight Pro — Gmaps Business Finder & Analyzer

**MapInsight Pro** is a powerful Python-based tool designed to scrape, analyze, and extract insights from Google Maps business listings. Built with **Streamlit** and **SeleniumBase**, it allows users to find business details and perform deep sentiment analysis on customer reviews, with specific support for Indonesian text processing.

## 🚀 Key Features

### 1. 🔍 Places Database (Scraper)
* **Deep Search:** Search for businesses by keyword, city, and country (e.g., "Cafe in Jakarta").
* **Direct Link Extraction:** Input a specific Google Maps URL (Shortlink or Longlink) to fetch details.
* **Data Extracted:** Business Name, Rating, Category, Address, Phone, Website, and Share Links.

### 2. 📊 Review Analyzer & Logger
* **Automated Scraping:** Fetches reviews dynamically using Selenium (handles infinite scrolling).
* **Sentiment Analysis:** Visualizes rating distributions (1-5 stars).
* **Keyword Extraction:** Uses **NLTK** and **Sastrawi** to identify common topics per rating level, filtering out stop words in both English and Indonesian.
* **🍽️ Menu Detection:** Smart algorithm that identifies potential food and drink items mentioned in reviews by filtering out non-food nouns (like "parkir", "pelayanan", "tempat").

## 🛠️ Tech Stack

* **Frontend:** [Streamlit](https://streamlit.io/)
* **Web Scraping:** [SeleniumBase](https://github.com/seleniumbase/SeleniumBase) (Undetected Driver mode)
* **Data Manipulation:** Pandas
* **NLP:** NLTK, Sastrawi (Stemming & Stopword removal for Indonesian)

## 📦 Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/gmaps-business-finder.git](https://github.com/your-username/gmaps-business-finder.git)
    cd gmaps-business-finder
    ```

2.  **Set up a virtual environment (Recommended):**
    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # Mac/Linux
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

    *Note: The app will automatically download necessary NLTK corpora (stopwords, punkt) on the first run.*

## 🖥️ Usage

1.  **Run the Streamlit application:**
    ```bash
    streamlit run app.py
    ```

2.  **Navigate the App:**
    * **Tab 1 (Search Places):** Use this to build your list of businesses. You can copy the URLs from the results table.
    * **Tab 2 (Review Analyzer):** Paste a specific Google Maps URL here to deep-dive into customer sentiment and find out what food people are talking about.

## ⚠️ Disclaimer

This tool is for educational and research purposes only. Please respect Google Maps' Terms of Service and use scraping responsibly. Avoid aggressive scraping that may overwhelm servers.

## 🤝 Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.