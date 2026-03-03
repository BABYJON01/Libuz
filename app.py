import os
import sqlite3
import requests
import concurrent.futures
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from deep_translator import GoogleTranslator
import random
import time
import secrets
import smtplib
from email.message import EmailMessage

# Load .env variables manually to avoid extra pip dependencies
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip()

app = Flask(__name__)
CORS(app) # Enable CORS for frontend communication

@app.route('/')
@app.route('/<path:path>')
def serve_index_and_static(path='index.html'):
    directory = os.path.dirname(os.path.abspath(__file__))
    # Ruxsat etilgan fayl turlarini xavfsizlik uchun tekshiramiz
    if path != 'index.html' and not path.endswith('.js') and not path.endswith('.css') and not path.endswith('.html'):
        return jsonify({"error": "Not found"}), 404
        
    if os.path.exists(os.path.join(directory, path)):
        return send_from_directory(directory, path)
    return send_from_directory(directory, 'index.html')

# Vercel Serverless environment has a read-only filesystem except for /tmp
if os.environ.get('VERCEL') == '1':
    DB_FILE = "/tmp/litmaps_clone.db"
    original_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "litmaps_clone.db")
    if os.path.exists(original_db) and not os.path.exists(DB_FILE):
        import shutil
        try:
            shutil.copy2(original_db, DB_FILE)
        except Exception:
            pass
else:
    DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "litmaps_clone.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  role TEXT DEFAULT 'user')''')
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                  ('admin', generate_password_hash('admin123'), 'admin'))
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"error": "Foydalanuvchi nomi va parol kiritilishi shart"}), 400
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                     (username, generate_password_hash(password)))
        conn.commit()
        return jsonify({"success": "Muvaffaqiyatli ro'yxatdan o'tdingiz"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Bu nomli foydalanuvchi allaqachon mavjud"}), 400
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if user and check_password_hash(user['password'], password):
        return jsonify({"success": True, "username": user['username'], "role": user['role']})
    else:
        return jsonify({"error": "Noto'g'ri logn yoki parol"}), 401

# --------------------------
# EMAIL OTP AUTHENTICATION
# --------------------------

# In-memory store for OTPs. Format: { "email@example.com": {"otp": "123456", "expires": timestamp} }
OTP_STORE = {}

# Email settings (Placeholder or App Password configurations loaded from .env)
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 465
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '').strip()
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '').replace(' ', '') # remove spaces if any

def send_otp_via_email(to_email, otp_code):
    try:
        # If credentials are provided and not placeholders, try to actually send the email
        is_placeholder = 'sizning' in MAIL_USERNAME or 'xxxx' in MAIL_PASSWORD
        if MAIL_USERNAME and MAIL_PASSWORD and not is_placeholder:
            msg = EmailMessage()
            msg.set_content(f"Sizning tizimga kirish kodingiz (OTP): {otp_code}\nUshbu kod 5 daqiqa davomida reyterli (amal) qiladi.")
            msg['Subject'] = "Antigravity - Kirish Kodi"
            msg['From'] = f"Antigravity Tizimi <{MAIL_USERNAME}>"
            msg['To'] = to_email
            
            with smtplib.SMTP_SSL(MAIL_SERVER, MAIL_PORT) as server:
                server.login(MAIL_USERNAME, MAIL_PASSWORD)
                server.send_message(msg)
            print(f"✅ OTP email orqali muvaffaqiyatli jo'natildi: {to_email}")
            return True
        else:
            # For development without credentials, just print it to the console
            print("="*40)
            print(f"📧 DIQQAT: Email sozlanmagan!")
            print(f"📧 {to_email} uchun OTP kod: {otp_code}")
            print("="*40)
            return True
    except Exception as e:
        print(f"❌ Email yuborishda xatolik: {e}")
        # Print to console anyway so the user isn't stuck during testing
        print(f"📧 Fallback OTP kod: {otp_code}")
        return False

@app.route('/api/auth/send-otp', methods=['POST'])
def send_otp():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    if not email or '@' not in email:
        return jsonify({"error": "Yaroqli email manzilini kiriting"}), 400
        
    otp_code = str(random.randint(100000, 999999))
    expires = time.time() + 300 # 5 minutes expiration
    
    OTP_STORE[email] = {
        "otp": otp_code,
        "expires": expires
    }
    
    # Send email (or print to console if no credentials)
    send_otp_via_email(email, otp_code)
    
    is_placeholder = 'sizning' in MAIL_USERNAME or 'xxxx' in MAIL_PASSWORD
    if MAIL_USERNAME and MAIL_PASSWORD and not is_placeholder:
        return jsonify({"success": f"{email} manziliga kod yuborildi."}), 200
    else:
        # Development mode fallback: return OTP to frontend for easy testing
        return jsonify({
            "success": f"Test rejim: {email} ga xat jo'natilmadi. Kod avtomatik kiritildi.",
            "dev_otp": otp_code
        }), 200

@app.route('/api/auth/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    otp_input = data.get('otp', '').strip()
    
    if not email or not otp_input:
        return jsonify({"error": "Email va OTP kod kiritilishi shart"}), 400
        
    stored_data = OTP_STORE.get(email)
    
    if not stored_data:
        return jsonify({"error": "Bu email uchun kod so'ralmagan yoki vaqti o'tib ketgan."}), 400
        
    if time.time() > stored_data['expires']:
        del OTP_STORE[email]
        return jsonify({"error": "Kodning vaqti (5 daqiqa) tugagan. Yangi kod so'rang."}), 400
        
    if stored_data['otp'] != otp_input:
        return jsonify({"error": "Kod noto'g'ri."}), 401
        
    # Code is valid! Clear it
    del OTP_STORE[email]
    
    # Log the user in or auto-register them
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (email,)).fetchone()
    
    if not user:
        # Auto-register
        import secrets
        dummy_pw = secrets.token_hex(16)
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                     (email, generate_password_hash(dummy_pw), 'user'))
        conn.commit()
        user_role = 'user'
    else:
        user_role = user['role']
        
    conn.close()
    
    return jsonify({"success": True, "username": email, "role": user_role}), 200

@app.route('/api/admin/users', methods=['GET'])
def get_users():
    conn = get_db_connection()
    users = conn.execute("SELECT id, username, role FROM users").fetchall()
    conn.close()
    return jsonify({"users": [dict(u) for u in users]})

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": "Foydalanuvchi o'chirildi"})

OPENALEX_API_URL = "https://api.openalex.org"

AUTHOR_ALIASES = {
    "abdulla qodiriy": ["julqunboy", "dumbul", "ovsar", "obid ketmon", "shig'ayboy"],
    "alisher navoiy": ["foniy", "navoiy"],
    "zahiriddin muhammad bobur": ["bobur"],
    "cho'lpon": ["abdulhamid sulaymon o'g'li"],
    "fitrat": ["abdurauf fitrat"],
    "oybek": ["muso toshmuhammad o'g'li"],
    "amir temur": ["temurbek", "sohibqiron"],
    "fazliddin ravshanov": ["fazliddin ravshanovich ravshanov", "ravshanov"]
}

# Semantic Data for Author Profile Knowledge Graph
AUTHOR_SEMANTIC_DATA = {
    "alisher navoiy": {
        "name": "Alisher Navoiy",
        "names": ["Navoiy", "Foni", "Nizomiddin Mir Alisher", "Almiser Navoyi"],
        "identifiers": ["VIAF: 95137156", "ISNI: 000000121345678", "Wikidata: Q29547"],
        "bio": ["Tug'ilgan: 1441, Hirot", "Vafoti: 1501, Hirot", "Shohrux Mirzo davri"],
        "profession": ["Shoir, mutafakkir", "Davlat arbobi", "Turkiy adabiyot asoschisi"],
        "works": [
            {"name": "Xamsa", "translations": ["Ingliz tili", "Rus tili", "Turk tili"]},
            "Muhokamat ul-lug'atayn", 
            {"name": "Xazoyin ul-ma'oniy", "translations": ["Fors tili"]},
            "Majolis un-nafois", 
            "Lison ut-tayr"
        ],
        "organizations": ["Temuriylar saroyi", "Sulton Husayn Boyqaro vaziri"]
    },
    "amir temur": {
        "name": "Amir Temur",
        "names": ["Temurbek", "Sohibqiron", "Tamerlan", "Timur"],
        "identifiers": ["VIAF: 62828062", "Wikidata: Q8467"],
        "bio": ["Tug'ilgan: 1336, Xo'ja Ilg'or qishlog'i (Kesh)", "Vafoti: 1405, O'tror"],
        "profession": ["Davlat arbobi", "Buyuk sarkarda", "Turon sultoni", "Temuriylar imperiyasi asoschisi"],
        "works": ["Temur tuzuklari (Tuzukoti Temuriy)"],
        "organizations": ["Temuriylar davlati", "Chig'atoy ulusi amiri"]
    },
    "zahiriddin muhammad bobur": {
        "name": "Zahiriddin Muhammad Bobur",
        "names": ["Bobur", "Zahiriddin"],
        "identifiers": ["VIAF: 10696985"],
        "bio": ["Tug'ilgan: 1483, Andijon", "Vafoti: 1530, Agra"],
        "profession": ["Shoir, mutafakkir", "Davlat arbobi", "Sarkarda", "Boburiylar sulolasi asoschisi"],
        "works": [
            {"name": "Boburnoma", "translations": ["Ingliz tili", "Fransuz tili", "Rus tili", "Yapon tili"]},
            "Mubayyin", 
            "Xatti Boburiy", 
            "Harb ishi", 
            "Aruz risolasi"
        ],
        "organizations": ["Temuriylar saroyi", "Boburiylar imperiyasi"]
    },
    "fazliddin ravshanov": {
        "name": "Fazliddin Ravshanovich Ravshanov",
        "names": ["Fazliddin Ravshanov", "Ravshanov", "F.R. Ravshanov"],
        "identifiers": ["ORCID: 0000-xxxx", "Scopus ID: xxxxx"],
        "bio": ["Zamonaviy olim", "Tadqiqotchi"],
        "profession": ["Olim", "O'qituvchi", "Tadqiqot ustasi"],
        "works": [
            {"name": "TOLERANCE: HISTORY AND DEVELOPMENT", "editions": ["2018", "The Light of Islam"]},
            {"name": "ABU NASR FARABI ON THE HARMONY OF SOCIETY...", "editions": ["2020", "PDF Available"]},
            {"name": "Danger and Security: History and Present", "editions": ["2021", "International Journal"]}
        ],
        "organizations": ["O'zbekiston Milliy Universiteti", "Tadqiqot markazlari"]
    }
}

def resolve_author_info(query):
    query_lower = query.lower()
    canonical_name = None
    aliases = []
    
    if query_lower in AUTHOR_ALIASES:
        canonical_name = query_lower
        aliases = AUTHOR_ALIASES[query_lower]
    else:
        for name, als in AUTHOR_ALIASES.items():
            if query_lower in als:
                canonical_name = name
                aliases = als
                break
                
    return canonical_name, aliases

def get_wikipedia_summary(author_name):
    """Try uz.wikipedia first. If no extract, try en.wikipedia and translate into Uzbek."""
    headers = {'User-Agent': 'LitmapsClone/1.0 (contact@example.com)'}
    
    # Try UZ first
    uz_wiki_url = f"https://uz.wikipedia.org/api/rest_v1/page/summary/{author_name.title()}"
    try:
        resp = requests.get(uz_wiki_url, headers=headers, timeout=3)
        if resp.status_code == 200:
            extract = resp.json().get('extract')
            if extract:
                return extract
    except:
        pass
        
    # Fallback to EN and translate
    en_wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{author_name.title()}"
    try:
        resp = requests.get(en_wiki_url, headers=headers, timeout=3)
        if resp.status_code == 200:
            extract_en = resp.json().get('extract')
            if extract_en:
                return safe_translate(extract_en, 'uz')
    except:
        pass
        
    return None

def safe_translate(text, tgt_lang):
    if not text: return ""
    try:
        return GoogleTranslator(source='auto', target=tgt_lang).translate(text)
    except Exception:
        return text

def get_cyberleninka_results(query, max_results=5):
    """Fetch search results from CyberLeninka."""
    url = f"https://cyberleninka.ru/search?q={query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            return []
            
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        results = soup.find_all('li')
        
        cyber_articles = []
        for li in results:
            title_elem = li.find('h2')
            if not title_elem:
                title_elem = li.find('a', href=lambda href: href and '/article/n/' in href)
                
            if title_elem:
                title = title_elem.text.strip()
                link = title_elem['href'] if title_elem.name == 'a' else title_elem.find('a')['href']
                full_link = f"https://cyberleninka.ru{link}" if link.startswith('/') else link
                
                cyber_articles.append({
                    "id": f"cyberleninka_{len(cyber_articles)}",
                    "title": title,
                    "original_title": title,
                    "publication_year": "N/A",  # Hard to parse consistently without entering the article
                    "cited_by_count": 0,
                    "authors": ["CyberLeninka Article"],
                    "download_url": full_link,
                    "source": "CyberLeninka"
                })
                
                if len(cyber_articles) >= max_results:
                    break
        return cyber_articles
    except Exception as e:
        print(f"CyberLeninka error: {e}")
        return []

def get_google_books_results(query, max_results=10):
    """Fetch books matching the query from Google Books API."""
    url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults={max_results}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            items = response.json().get('items', [])
            books = []
            for item in items:
                vol = item.get('volumeInfo', {})
                original_title = vol.get('title', 'Noma\'lum Kitob')
                # Translate book title to Uzbek
                uz_title = safe_translate(original_title, 'uz')
                
                authors = vol.get('authors', ['Noma\'lum'])
                year = vol.get('publishedDate', 'YYYY')[:4]
                link = vol.get('infoLink', '#')
                
                books.append({
                    "id": f"gbooks_{item.get('id')}",
                    "title": uz_title,
                    "original_title": original_title,
                    "publication_year": year,
                    "cited_by_count": 0, # Books API doesn't return citations easily here
                    "authors": authors,
                    "download_url": link,
                    "source": "Google Books"
                })
            return books
    except Exception as e:
        print(f"Google Books error: {e}")
    return []

@app.route('/api/suggest', methods=['GET'])
def suggest_papers():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"results": []})
        
    api_url = f"{OPENALEX_API_URL}/autocomplete/works?q={query}"
    response = requests.get(api_url)
    if response.status_code == 200:
        return jsonify(response.json())
    return jsonify({"results": []})

def uz_transliterate(text):
    if not text: return text
    
    l2c = {
        "sh": "ш", "ch": "ч", "ya": "я", "yo": "ё", "yu": "ю", "o'": "ў", "g'": "ғ",
        "shch": "щ",
        "a": "а", "b": "б", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "ҳ",
        "i": "и", "j": "ж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о",
        "p": "п", "q": "қ", "r": "р", "s": "с", "t": "т", "u": "у", "v": "в",
        "x": "х", "y": "й", "z": "з", "c": "ц",
        "SH": "Ш", "CH": "Ч", "YA": "Я", "YO": "Ё", "YU": "Ю", "O'": "Ў", "G'": "Ғ",
        "A": "А", "B": "Б", "D": "Д", "E": "Е", "F": "Ф", "G": "Г", "H": "Ҳ",
        "I": "И", "J": "Ж", "K": "К", "L": "Л", "M": "М", "N": "Н", "O": "О",
        "P": "П", "Q": "Қ", "R": "Р", "S": "С", "T": "Т", "U": "У", "V": "В",
        "X": "Х", "Y": "Й", "Z": "З", "C": "Ц", "'": "ъ"
    }
    c2l = {v: k for k, v in l2c.items()}
    # Hardcoded fixes for some edge cases
    c2l['э'] = 'e'
    c2l['Э'] = 'E'
    c2l['ы'] = 'y'
    c2l['Ы'] = 'Y'
    
    is_cyrillic = any('\u0400' <= char <= '\u04FF' for char in text)
    res = text
    
    if is_cyrillic:
        # Cyrillic to Latin
        # Single characters are fine to replace mapping iteration
        for cyr, lat in sorted(c2l.items(), key=lambda x: len(x[0]), reverse=True):
            res = res.replace(cyr, lat)
    else:
        # Latin to Cyrillic
        for lat, cyr in sorted(l2c.items(), key=lambda x: len(x[0]), reverse=True):
            res = res.replace(lat, cyr)
            
    return res

@app.route('/api/search', methods=['GET'])
def search_papers():
    query = request.args.get('q', '').strip()
    year_start = request.args.get('year_start', '')
    year_end = request.args.get('year_end', '')
    authors = request.args.get('authors', '').strip()
    journals = request.args.get('journals', '').strip()
    lang = request.args.get('lang', '')
    min_citations = request.args.get('min_cites', '')
    max_citations = request.args.get('max_cites', '')
    work_type = request.args.get('work_type', '').strip()
    
    # Expand query intelligently
    q_expanded = ""
    author_profile = None

    if query:
        # 1. Always check Wikipedia first to see if it's a known entity
        wiki_bio = get_wikipedia_summary(query)
        
        # 2. Check pseudonyms
        canonical_author, aliases = resolve_author_info(query)
        
        if canonical_author:
            # We found a hardcoded pseudonym match
            search_terms = [canonical_author] + aliases
            terms_str = " OR ".join([f'"{t}"' for t in search_terms])
            q_expanded = terms_str 
            
            # If wiki didn't find the exact query, try the canonical name
            if not wiki_bio:
                wiki_bio = get_wikipedia_summary(canonical_author)
                
            author_profile = {
                "name": canonical_author.title(),
                "aliases": [a.title() for a in aliases],
                "bio": wiki_bio or "Ma'lumot topilmadi."
            }
        else:
            # Not a hardcoded pseudonym. 
            # Standard translation expansion for openalex
            q_en = safe_translate(query, 'en')
            q_ru = safe_translate(query, 'ru')
            q_translit = uz_transliterate(query)
            
            terms = [f'"{query}"']
            if q_en and q_en.lower() != query.lower(): terms.append(f'"{q_en}"')
            if q_ru and q_ru.lower() != query.lower(): terms.append(f'"{q_ru}"')
            if q_translit and q_translit.lower() != query.lower(): terms.append(f'"{q_translit}"')
            
            q_expanded = " OR ".join(terms)
            
            # If Wikipedia had something for this random query, show universal knowledge card
            if wiki_bio:
                author_profile = {
                    "name": query.title(),
                    "aliases": [],
                    "bio": wiki_bio
                }

    # Build exact filters
    filters = []
    if year_start and year_end:
        filters.append(f"publication_year:{year_start}-{year_end}")
    elif year_start:
        filters.append(f"publication_year:{year_start}-")
    elif year_end:
        filters.append(f"publication_year:-{year_end}")
        
    if lang:
        filters.append(f"language:{lang}")
        
    if authors:
        filters.append(f"authorships.author.display_name.search:{authors}")
        
    if journals:
        filters.append(f"primary_location.source.display_name.search:{journals}")
        
    if min_citations and max_citations:
        filters.append(f"cited_by_count:{min_citations}-{max_citations}")
    elif min_citations:
        filters.append(f"cited_by_count:>{min_citations}")
    elif max_citations:
        filters.append(f"cited_by_count:<{max_citations}")
        
    if work_type:
        # e.g. article => journal-article, book => book, poetry => book?
        # we can just pass the raw type to OpenAlex
        filters.append(f"type:{work_type}")
        
    filter_string = ",".join(filters)
        
    api_url = f"{OPENALEX_API_URL}/works?per-page=20"
    if q_expanded:
        api_url += f"&search={q_expanded}"
    if filter_string:
        api_url += f"&filter={filter_string}"
        
    if not q_expanded and not filter_string and not authors and not journals:
        return jsonify({"error": "Iltimos qidiruv mezoni kiriting"}), 400

    response = requests.get(api_url)
    
    if response.status_code == 200:
        data = response.json()
        results = []
        
        # Parallel translate titles to Uzbek for fast UI response
        def process_work(work):
            original_title = work.get("title", "Untitled")
            uz_title = safe_translate(original_title, 'uz')
            
            # Check for open access download link
            oa_url = None
            if work.get("open_access", {}).get("is_oa"):
                oa_url = work.get("open_access", {}).get("oa_url")
            
            return {
                "id": work.get("id"),
                "title": uz_title,
                "original_title": original_title,
                "publication_year": work.get("publication_year"),
                "cited_by_count": work.get("cited_by_count", 0),
                "authors": [author.get("author", {}).get("display_name") for author in work.get("authorships", [])],
                "download_url": oa_url
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            works = data.get('results', [])
            results = list(executor.map(process_work, works))

        # Fetch CyberLeninka results
        cyber_results = get_cyberleninka_results(query)
        if cyber_results:
             # Translate CyberLeninka titles to Uzbek as well
             for cr in cyber_results:
                 cr['title'] = safe_translate(cr['original_title'], 'uz')
             results.extend(cyber_results)
             
        # Broad Entity Fallback: If academic papers are scarce (e.g., searching for politicians/actors)
        if len(results) <= 3 and not (authors or journals):
            books = get_google_books_results(query)
            results.extend(books)

        return jsonify({
            "results": results,
            "author_profile": author_profile
        })
    else:
        return jsonify({"error": "Failed to fetch data from OpenAlex"}), 500

@app.route('/api/paper/<path:paper_id>/network', methods=['GET'])
def get_paper_network(paper_id):
    # Extract just the ID part if the full OpenAlex URI is passed
    if "openalex.org/" in paper_id:
         paper_id = paper_id.split("openalex.org/")[-1]
         
    # Fetch the main paper
    main_paper_response = requests.get(f"{OPENALEX_API_URL}/works/{paper_id}")
    if main_paper_response.status_code != 200:
        return jsonify({"error": "Paper not found"}), 404
        
    main_paper = main_paper_response.json()
    
    nodes = []
    edges = []
    
    # Add main node
    nodes.append({
        "id": main_paper.get("id"),
        "label": _truncate_title(main_paper.get("title", "Untitled"), 25),
        "title": main_paper.get("title", "Untitled"),
        "group": "main",
        "value": main_paper.get("cited_by_count", 0) + 5,  # Give it a larger size
        "x": 0,
        "y": 0,
        "fixed": {"x": True, "y": True}
    })
    
    # Add Author nodes for the main paper
    for author_obj in main_paper.get("authorships", []):
        author_info = author_obj.get("author", {})
        author_id = author_info.get("id")
        author_name = author_info.get("display_name", "Unknown Author")
        if author_id:
            nodes.append({
                "id": f"author_{author_id.split('/')[-1]}",
                "label": author_name,
                "title": f"Muallif: {author_name}",
                "group": "author",
                "value": 3
            })
            # Link author to main paper
            edges.append({
                "from": f"author_{author_id.split('/')[-1]}",
                "to": main_paper.get("id"),
                "arrows": "to"
            })
    
    # Fetch works that CITE this paper (kimlar bu kitob/maqola haqida yozgan)
    cited_by_url = f"{OPENALEX_API_URL}/works?filter=cites:{main_paper.get('id')}&per-page=15"
    try:
        cites_res = requests.get(cited_by_url, timeout=5)
        if cites_res.status_code == 200:
            cites_data = cites_res.json().get("results", [])
            for cite in cites_data:
                nodes.append({
                    "id": cite.get("id"),
                    "label": get_author_label(cite),
                    "title": cite.get("title", "Untitled"),
                    "group": "cited_by",
                    "value": cite.get("cited_by_count", 0) + 1
                })
                # Edge from citing work -> main paper
                edges.append({
                    "from": cite.get("id"),
                    "to": main_paper.get("id"),
                    "arrows": "to"
                })
    except Exception as e:
        print(f"Error fetching cited by: {e}")

    # Fetch referenced works (papers this paper cites)
    referenced_works = main_paper.get("referenced_works", [])[:10] # Limit to 10
    
    for ref_id in referenced_works:
        ref_response = requests.get(f"{OPENALEX_API_URL}/works/{ref_id.split('openalex.org/')[-1]}")
        if ref_response.status_code == 200:
            ref_data = ref_response.json()
            nodes.append({
                "id": ref_data.get("id"),
                "label": get_author_label(ref_data),
                "title": ref_data.get("title", "Untitled"),
                "group": "reference",
                "value": ref_data.get("cited_by_count", 0) + 1
            })
            edges.append({
                "from": main_paper.get("id"),
                "to": ref_data.get("id"),
                "arrows": "to"
            })
            
    return jsonify({
        "nodes": nodes,
        "edges": edges
    })

@app.route('/api/author/<author_name>/network', methods=['GET'])
def get_author_network(author_name):
    query_lower = author_name.lower().strip()
    canonical_name, _ = resolve_author_info(query_lower)
    if not canonical_name:
        canonical_name = query_lower

    semantic_data = AUTHOR_SEMANTIC_DATA.get(canonical_name)
    
    if not semantic_data:
        # Generate generic fallback semantic profile
        semantic_data = {
            "name": author_name.title(),
            "names": [author_name.title()],
            "identifiers": ["Qidiruv orqali topilgan"],
            "bio": ["Tug'ilgan va vafoti: Noma'lum"],
            "profession": ["Muallif", "Olim/Tadqiqotchi"],
            "works": [f"{author_name.title()} asarlari"],
            "organizations": ["Ilmiy baza orqali bog'langan"]
        }

    nodes = []
    edges = []
    
    # 1. Main Author Node
    main_id = "author_main_" + canonical_name.replace(" ", "_")
    nodes.append({
        "id": main_id,
        "label": semantic_data["name"],
        "title": semantic_data["name"] + " profili",
        "group": "main",
        "value": 30,
        "x": 0,
        "y": 0,
        "fixed": {"x": True, "y": True}
    })

    # Categories Mapping (Key -> Display Category -> Group)
    categories = [
        ("names", "Nomlar / Taxalluslar", "author"),
        ("identifiers", "Identifikatorlar", "reference"),
        ("bio", "Biografiya", "author"),
        ("profession", "Kasb va Mavzular", "cited_by"),
        ("works", "Asarlar", "reference"),
        ("organizations", "Tashkilotlar", "cited_by")
    ]
    
    uid = 0
    for key, cat_label, cat_group in categories:
        items = semantic_data.get(key, [])
        if not items:
            continue
            
        # Create Category Node (Optional, but looks like Image 3 diagram)
        cat_node_id = f"cat_{key}_{main_id}"
        nodes.append({
            "id": cat_node_id,
            "label": cat_label,
            "title": f"Turkum: {cat_label}",
            "group": cat_group,
            "value": 15,
            "shape": "box" # Makes category nodes stand out
        })
        # Edge from Author to Category
        edges.append({
            "from": main_id,
            "to": cat_node_id,
            "arrows": "to",
            "label": "hasAttribute"
        })
        
        # Add actual items connected to the category node
        for item in items:
            uid += 1
            item_id = f"item_{key}_{uid}"
            
            # Check if this item is a dictionary (nested relationship)
            if isinstance(item, dict):
                # E.g., item = {"name": "Xamsa", "translations": ["En", "Ru"]}
                display_name = item.get("name", "Unknown")
                nodes.append({
                    "id": item_id,
                    "label": _truncate_title(display_name, 20),
                    "title": display_name,
                    "group": "reference",
                    "value": 8
                })
                # Edge from Category to Item
                edges.append({
                    "from": cat_node_id,
                    "to": item_id,
                    "arrows": "to"
                })
                
                # Check for sub-items (e.g., translations, editions)
                for sub_key in ["translations", "editions"]:
                    if sub_key in item:
                        sub_items = item[sub_key]
                        for sub_item in sub_items:
                            uid += 1
                            sub_item_id = f"sub_{sub_key}_{uid}"
                            nodes.append({
                                "id": sub_item_id,
                                "label": sub_item,
                                "title": f"{sub_key.title()}: {sub_item}",
                                "group": "cited_by", # distinctive color
                                "value": 5
                            })
                            edges.append({
                                "from": item_id,
                                "to": sub_item_id,
                                "arrows": "to",
                                "label": sub_key
                            })
            else:
                # Standard flat string item
                nodes.append({
                    "id": item_id,
                    "label": _truncate_title(item, 20),
                    "title": item,
                    "group": "reference",
                    "value": 8
                })
                # Edge from Category to Item
                edges.append({
                    "from": cat_node_id,
                    "to": item_id,
                    "arrows": "to"
                })

    return jsonify({
        "nodes": nodes,
        "edges": edges
    })

def get_author_label(work):
    authors = work.get("authorships", [])
    if authors:
        first_author = authors[0].get("author", {}).get("display_name", "")
        last_name = first_author.split()[-1] if first_author else "Unknown"
    else:
        last_name = "Unknown"
    year = work.get("publication_year", "YYYY")
    return f"{last_name}, {year}"

def _truncate_title(title, max_length=30):
    if not title: return "Untitled"
    return title[:max_length] + "..." if len(title) > max_length else title

if __name__ == '__main__':
    app.run(debug=True)
