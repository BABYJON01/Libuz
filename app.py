import os
import json
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
import urllib.parse

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
    
    # Track search queries for Hybrid Recommendation system
    c.execute('''CREATE TABLE IF NOT EXISTS user_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL,
                  query TEXT NOT NULL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
                  
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

# Semantic Data for Categorical Entities mapped from Wikipedia profiles
CATEGORY_DATA = {
    "siyosatchilar": {
        "title": "Siyosatchilar",
        "groups": [
            {"name": "Davlat rahbarlari", "people": ["Shavkat Mirziyoyev", "Vladimir Putin", "Rejep Tayyip Erdog'an"]},
            {"name": "Parlament a'zolari", "people": ["Tanzila Norboyeva", "Nurdinjon Ismoilov", "Alisher Qodirov"]},
            {"name": "Diplomatlar", "people": ["Baxtiyor Saidov", "Abdulaziz Komilov"]}
        ]
    },
    "ijodkorlar": {
        "title": "Ijodkorlar",
        "groups": [
            {"name": "Yozuvchilar", "people": ["Abdulla Qodiriy", "O'tkir Hoshimov", "Pirimqul Qodirov"]},
            {"name": "Shoirlar", "people": ["Erkin Vohidov", "Abdulla Oripov", "Muhammad Yusuf"]},
            {"name": "Rassomlar", "people": ["Chingiz Ahmarov", "O'rol Tansiqboyev", "Akmal Nur"]},
            {"name": "Rejissyorlar", "people": ["Shuhrat Abbosov", "Zulfiqor Musoqov", "Rihsiboy Muhammadjonov"]}
        ]
    },
    "media shaxslari": {
        "title": "Media Shaxslari",
        "groups": [
            {"name": "Aktyorlar", "people": ["Yodgor Sa'diyev", "Murod Rajabov", "Ubaydulla Omon"]},
            {"name": "Blogerlar", "people": ["Xushnudbek Xudoyberdiyev", "Aziza Umarova", "Umid Gafurov"]},
            {"name": "Jurnalistlar va boshlovchilar", "people": ["Qahramon Aslanov", "Alisher Uzoqov", "Rizanova"]}
        ]
    },
    "ilmiy va akademik shaxslar": {
        "title": "Ilmiy va Akademik shaxslar",
        "groups": [
            {"name": "Olimlar", "people": ["Abu Rayhon Beruniy", "Al-Xorazmiy", "Mirzo Ulug'bek", "Ibn Sino"]},
            {"name": "Professorlar/Akademiklar", "people": ["Behzod Yo'ldoshev", "Po'lat Habibullayev", "Mahmud Salohiddinov"]}
        ]
    },
    "sportchilar": {
        "title": "Sportchilar",
        "groups": [
            {"name": "Futbolchilar", "people": ["Odil Ahmedov", "Eldor Shomurodov", "Maksim Shatskix"]},
            {"name": "Bokschi va kurashchilar", "people": ["Bahodir Jalolov", "Hasanboy Do'smatov", "Artur Taymazov"]},
            {"name": "Shaxmatchilar", "people": ["Rustam Qosimjonov", "Nodirbek Abdusattorov"]}
        ]
    }
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
    username = request.args.get('username', '').strip()
    year_start = request.args.get('year_start', '')
    year_end = request.args.get('year_end', '')
    authors = request.args.get('authors', '').strip()
    journals = request.args.get('journals', '').strip()
    lang = request.args.get('lang', '')
    min_citations = request.args.get('min_cites', '')
    max_citations = request.args.get('max_cites', '')
    work_type = request.args.get('work_type', '').strip()
    
    user_past_queries = []
    if query and username:
        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO user_history (username, query) VALUES (?, ?)", (username, query))
            conn.commit()
            history = conn.execute("SELECT query FROM user_history WHERE username = ? ORDER BY timestamp DESC LIMIT 20", (username,)).fetchall()
            user_past_queries = [h['query'].lower() for h in history]
        except Exception as e:
            print(f"History tracking error: {e}")
        finally:
            conn.close()

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
        filters.append(f"type:{work_type}")
        
    filter_string = ",".join(filters)
        
    api_url = f"{OPENALEX_API_URL}/works?per-page=40"
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
        
        def process_work(work):
            original_title = work.get("title", "Untitled")
            uz_title = safe_translate(original_title, 'uz')
            
            oa_url = None
            if work.get("open_access", {}).get("is_oa"):
                oa_url = work.get("open_access", {}).get("oa_url")
            
            return {
                "id": work.get("id"),
                "title": uz_title,
                "original_title": str(original_title),
                "publication_year": work.get("publication_year"),
                "cited_by_count": work.get("cited_by_count", 0),
                "relevance_score": float(work.get("relevance_score") or 0),
                "authors": [author.get("author", {}).get("display_name") for author in work.get("authorships", [])],
                "download_url": oa_url,
                "source": "OpenAlex"
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            works = data.get('results', [])
            results = list(executor.map(process_work, works))

        cyber_results = get_cyberleninka_results(query)
        if cyber_results:
             for cr in cyber_results:
                 cr['title'] = safe_translate(cr['original_title'], 'uz')
                 cr['relevance_score'] = 100.0 if query.lower() in str(cr['original_title']).lower() else 50.0
             results.extend(cyber_results)
             
        if len(results) <= 3 and not (authors or journals):
            books = get_google_books_results(query)
            for b in books:
                b['relevance_score'] = 80.0 if query.lower() in str(b['original_title']).lower() else 40.0
            results.extend(books)

        # Hybrid Recommendation Ranking
        max_cites = max([r.get('cited_by_count', 0) for r in results] + [1])
        max_rel = max([r.get('relevance_score', 0) for r in results] + [1.0])
        
        exact_matches = []
        related_results = []
        recommended = []
        
        q_lower = query.lower()
        
        for r in results:
            rel = r.get("relevance_score", 0) / max_rel
            title_lower = r.get("original_title", "").lower()
            
            if q_lower in title_lower:
                rel = max(rel, 0.9)
                
            pop = r.get("cited_by_count", 0) / max_cites
            
            year = r.get("publication_year")
            if not str(year).isdigit(): year = 2000
            year = int(year)
            rec = max(0, min(1, (year - 1950) / 75))
            
            u_int = 0
            for pq in user_past_queries:
                if pq in title_lower or pq in q_lower:
                    u_int += 0.2
            u_int = min(1.0, u_int)
            
            final_score = (0.5 * rel) + (0.2 * pop) + (0.2 * rec) + (0.1 * u_int)
            r["hybrid_score"] = float(f"{final_score:.3f}")
            
            is_exact = (q_lower == title_lower) or any(q_lower == str(a).lower() for a in r.get("authors", []))
            
            if is_exact or rel > 0.85:
                exact_matches.append(r)
            elif rel > 0.4:
                related_results.append(r)
            else:
                recommended.append(r)
                
        exact_matches.sort(key=lambda x: x["hybrid_score"], reverse=True)
        related_results.sort(key=lambda x: x["hybrid_score"], reverse=True)
        recommended.sort(key=lambda x: x["hybrid_score"], reverse=True)
        
        if not recommended and len(related_results) > 6:
            split_idx = len(related_results) // 2
            recommended = related_results[split_idx:]
            related_results = related_results[:split_idx]
            
        if not related_results and len(recommended) > 6:
            split_idx = len(recommended) // 2
            related_results = recommended[:split_idx]
            recommended = recommended[split_idx:]

        return jsonify({
            "exact_matches": exact_matches,
            "related_results": related_results,
            "recommended": recommended,
            "author_profile": author_profile
        })
    else:
        return jsonify({"error": "Failed to fetch data from OpenAlex"}), 500

@app.route('/api/paper/<path:paper_id>/network', methods=['GET'])
def get_paper_network(paper_id):
    paper_id = urllib.parse.unquote(paper_id)
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
    author_name = urllib.parse.unquote(author_name)
    query_lower = author_name.lower().strip()
    canonical_name, _ = resolve_author_info(query_lower)
    if not canonical_name:
        canonical_name = query_lower

    semantic_data = AUTHOR_SEMANTIC_DATA.get(canonical_name)
    
    if not semantic_data:
        # Generate generic fallback semantic profile
        wiki_bio = get_wikipedia_summary(canonical_name)
        
        bio_text = wiki_bio if wiki_bio else "Biografiya ma'lumotlari mavjud emas."
        
        # Extract professions based on open source bio
        bio_lower = bio_text.lower()
        professions = set()
        
        if any(word in bio_lower for word in ['siyosat', 'davlat', 'prezident', 'parlament', 'diplomat', 'vazir', 'hokim']):
            professions.add("Siyosatchilar")
        if any(word in bio_lower for word in ['yozuvchi', 'shoir', 'rassom', 'rejissyor', 'ijodkor', 'yozgan']):
            professions.add("Ijodkorlar")
        if any(word in bio_lower for word in ['aktyor', 'aktrisa', 'bloger', 'boshlovchi', 'jurnalist', "qo'shiqchi", "san'atkor"]):
            professions.add("Media shaxslari")
        if any(word in bio_lower for word in ['olim', 'tadqiqotchi', 'professor', 'akademik', 'fan ', 'ilmiy', 'dotsent']):
            professions.add("Ilmiy va akademik shaxslar")
        if any(word in bio_lower for word in ['sportchi', 'futbolchi', 'tennischi', 'baksyor', 'chempion']):
            professions.add("Sportchilar")
            
        if not professions:
            professions.add("Ochiq manbalar orqali topish")
            
        # Optional truncating for the bio label inside the graph node
        bio_preview = bio_text
        if len(bio_preview) > 60:
             bio_preview = bio_preview[:57] + "..."
             
        semantic_data = {
            "name": author_name.title(),
            "names": [author_name.title(), author_name.upper()],
            "identifiers": ["Wikipedia Id: " + author_name.replace(' ', '_')],
            "bio": [bio_preview],
            "profession": list(professions),
            "works": [f"{author_name.title()} asarlari"],
            "organizations": ["Wikipedia orqali ma'lumotlar"]
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
        ("names", "Nomlar / Taxalluslar", "cat_author"),
        ("identifiers", "Identifikatorlar", "cat_reference"),
        ("bio", "Biografiya", "cat_author"),
        ("profession", "Kasb va Mavzular", "cat_cited_by"),
        ("works", "Asarlar", "cat_reference"),
        ("organizations", "Tashkilotlar", "cat_cited_by")
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
            "value": 15
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

@app.route('/api/category/<path:category_name>/network', methods=['GET'])
def get_category_network(category_name):
    cat_name = urllib.parse.unquote(category_name).lower().strip()
    
    cat_data = CATEGORY_DATA.get(cat_name)
    if not cat_data:
        return jsonify({"error": "Kategoriya topilmadi."}), 404
        
    nodes = []
    edges = []
    
    main_id = "cat_main_" + cat_name.replace(" ", "_").replace("'", "")
    nodes.append({
        "id": main_id,
        "label": cat_data["title"],
        "title": cat_data["title"],
        "group": "main",
        "value": 30,
        "x": 0,
        "y": 0,
        "fixed": {"x": True, "y": True}
    })
    
    uid = 0
    for group in cat_data["groups"]:
        uid += 1
        group_id = f"group_{uid}_{main_id}"
        nodes.append({
            "id": group_id,
            "label": group["name"],
            "title": f"Turkum: {group['name']}",
            "group": "cat_author",
            "value": 20
        })
        edges.append({
            "from": main_id,
            "to": group_id,
            "arrows": "to"
        })
        
        for person in group["people"]:
            uid += 1
            person_id = f"person_{uid}_{main_id}"
            nodes.append({
                "id": person_id,
                "label": person,
                "title": f"Shaxs: {person}",
                "group": "cat_reference",
                "value": 15
            })
            edges.append({
                "from": group_id,
                "to": person_id,
                "arrows": "to"
            })
            
    return jsonify({
        "nodes": nodes,
        "edges": edges
    })

# Simple in-memory cache for Wikidata (Faza 2: Optimizatsiya)
WIKIDATA_CACHE = {}

def load_local_authors():
    try:
        with open('local_authors.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Baza yuklashda xato: {e}")
        return []

LOCAL_AUTHORS_DB = load_local_authors()

def find_local_author(name):
    def simplify(text):
        if not text: return ""
        # Remove apostrophes and standardize common confusing letters
        t = text.lower().replace("'", "").replace("‘", "").replace("’", "").replace("`", "")
        t = t.replace("o", "a").replace("u", "a").replace("ў", "у").replace("ё", "йо")
        return t

    name_lower = name.lower()
    name_translit = uz_transliterate(name).lower()
    
    matches_simp = [simplify(name_lower), simplify(name_translit)]
    
    for author in LOCAL_AUTHORS_DB:
        author_name = author.get('name', '').lower()
        author_name_translit = uz_transliterate(author_name).lower()
        
        targets_simp = [simplify(author_name), simplify(author_name_translit)]
        
        aliases = author.get('alias', '')
        if aliases:
            aliases_str = " ".join(aliases).lower() if isinstance(aliases, list) else str(aliases).lower()
            aliases_translit = uz_transliterate(aliases_str).lower()
            targets_simp.extend([simplify(aliases_str), simplify(aliases_translit)])
            
        other_names = author.get('other_names', [])
        if other_names:
            other_names_str = " ".join(other_names).lower() if isinstance(other_names, list) else str(other_names).lower()
            other_names_translit = uz_transliterate(other_names_str).lower()
            targets_simp.extend([simplify(other_names_str), simplify(other_names_translit)])
            
        for m in matches_simp:
            if not m: continue
            for t in targets_simp:
                if not t: continue
                if m in t:
                    return author
    return None

def search_wikidata_entity(name):
    # Keshni tekshirish
    cache_key = f"search_{name}"
    if cache_key in WIKIDATA_CACHE:
        return WIKIDATA_CACHE[cache_key]
        
    url = f"https://www.wikidata.org/w/api.php?action=wbsearchentities&search={urllib.parse.quote(name)}&language=uz&uselang=en&format=json"
    headers = {'User-Agent': 'LibUZ/1.0 (https://libuz.vercel.app)'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("search") and len(data["search"]) > 0:
                entities = data["search"]
                target_entity = entities[0] # Default to first
                
                # Odam yoki Yozuvchini topishga harakat
                for e in entities:
                    desc = str(e.get('description', '')).lower()
                    if 'human' in desc or 'poet' in desc or 'writer' in desc or 'politician' in desc or 'scientist' in desc:
                        target_entity = e
                        break
                        
                WIKIDATA_CACHE[cache_key] = target_entity
                return target_entity
    except Exception as e:
        print(f"Wikidata Search Error: {e}")
    return None

def get_wikidata_network(entity_id, max_nodes=30):
    cache_key = f"network_{entity_id}"
    if cache_key in WIKIDATA_CACHE:
        return WIKIDATA_CACHE[cache_key]
        
    query = """
    SELECT ?rel ?relLabel ?item ?itemLabel ?itemDescription ?dir WHERE {
      VALUES ?relProp { wdt:P737 wdt:P802 wdt:P1066 wdt:P800 wdt:P69 wdt:P26 wdt:P40 wdt:P22 wdt:P25 wdt:P3373 wdt:P1038 wdt:P106 }
      
      { 
        wd:%s ?relProp ?item . 
        BIND("to_item" AS ?dir)
      }
      UNION
      { 
        ?item ?relProp wd:%s . 
        BIND("from_item" AS ?dir)
      }
      
      ?rel wikibase:directClaim ?relProp .
      
      SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],uz,en,ru". }
    } LIMIT %d
    """ % (entity_id, entity_id, max_nodes)
    
    url = "https://query.wikidata.org/sparql"
    headers = {
        'User-Agent': 'LibUZ/1.0 (https://libuz.vercel.app)',
        'Accept': 'application/sparql-results+json'
    }
    try:
        response = requests.get(url, params={'query': query}, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            WIKIDATA_CACHE[cache_key] = data
            return data
    except Exception as e:
        print(f"SPARQL Error: {e}")
    return None

@app.route('/api/person_graph/<path:name>', methods=['GET'])
def get_person_graph(name):
    person_name = urllib.parse.unquote(name).title()
    
    # 0. Check local database first
    local_author = find_local_author(person_name)
    if local_author:
        main_id = local_author['id']
        main_label = local_author['name']
        main_desc = local_author['description'] or local_author.get('alias') or "Jadvaldan kiritilgan mahalliy ma'lumot"
        
        nodes = [{
            "id": main_id,
            "label": main_label,
            "title": f"Shaxs: {main_label}",
            "group": "main",
            "value": 40,
            "description": main_desc,
            "wikidataUrl": "",
            "wikipediaUrl": ""
        }]
        
        edges = []
        
        # Asarlari tugunlari
        for i, work in enumerate(local_author.get('works', [])):
            work_id = f"{main_id}_work_{i}"
            nodes.append({
                "id": work_id,
                "label": work[:30] + '...' if len(work) > 30 else work,
                "title": f"Asar: {work}",
                "group": "book",
                "value": 20,
                "description": ""
            })
            edges.append({
                "from": main_id,
                "to": work_id,
                "label": "yozgan",
                "arrows": "to",
                "color": "#9ca3af"
            })
            
        # Kalit so'zlar / Aloqador shaxslar
        for i, kw in enumerate(local_author.get('keywords', [])):
            kw_id = f"{main_id}_kw_{i}"
            nodes.append({
                "id": kw_id,
                "label": kw[:30] + '...' if len(kw) > 30 else kw,
                "title": f"Aloqador: {kw}",
                "group": "institution",
                "value": 20,
                "description": ""
            })
            edges.append({
                "from": main_id,
                "to": kw_id,
                "label": "aloqador",
                "arrows": "to",
                "color": "#9ca3af"
            })
            
        return jsonify({
            "nodes": nodes,
            "edges": edges
        })
    
    # 1. Ask Wikidata for the Q-ID (Fallback)
    entity = search_wikidata_entity(person_name)
    
    if not entity:
        return jsonify({"error": f"{person_name} nomli shaxs Wikidata va mahalliy bazadan topilmadi."}), 404
        
    main_id = entity['id']
    main_label = entity.get('label', person_name)
    main_desc = entity.get('description', 'Ma\'lumot yo\'q')
    
    nodes = [{
        "id": main_id,
        "label": main_label,
        "title": f"Shaxs: {main_label}",
        "group": "main",
        "value": 40,
        "description": main_desc,
        "wikidataUrl": f"https://www.wikidata.org/wiki/{main_id}",
        "wikipediaUrl": f"https://uz.wikipedia.org/wiki/{main_label.replace(' ', '_')}"
    }]
    edges = []
    
    # 2. Extract network relationships via SPARQL
    network_data = get_wikidata_network(main_id)
    
    if network_data and 'results' in network_data and 'bindings' in network_data['results']:
        results = network_data['results']['bindings']
        added_nodes = set([main_id])
        
        for r in results:
            item_id = r.get('item', {}).get('value', '').split('/')[-1]
            if not item_id or item_id in added_nodes:
                continue
                
            item_label = r.get('itemLabel', {}).get('value', item_id)
            item_desc = r.get('itemDescription', {}).get('value', '')
            rel_label = r.get('relLabel', {}).get('value', 'related')
            direction = r.get('dir', {}).get('value', 'to_item')
            
            # Categorize nodes
            group = "cat_reference" # default
            if 'influenced by' in rel_label or 'student of' in rel_label or 'educated at' in rel_label:
                group = "cat_author" # Mentors / Predecessors
            elif 'influenced' in rel_label:
                group = "cat_cited_by" # Students / Successors
            elif 'child' in rel_label or 'spouse' in rel_label or 'father' in rel_label or 'mother' in rel_label or 'relative' in rel_label:
                group = "category" # Family
                
            nodes.append({
                "id": item_id,
                "label": item_label[:15] + ".." if len(item_label) > 15 else item_label,
                "title": f"Munosabat: {rel_label}\nNomi: {item_label}",
                "group": group,
                "value": 15,
                "description": f"{item_label} - {item_desc}",
                "wikidataUrl": f"https://www.wikidata.org/wiki/{item_id}"
            })
            added_nodes.add(item_id)
            
            # Edge direction
            if direction == 'to_item':
                edges.append({
                    "from": main_id, "to": item_id, "arrows": "to", "label": rel_label
                })
            else:
                edges.append({
                    "from": item_id, "to": main_id, "arrows": "to", "label": rel_label
                })
                
    if len(nodes) == 1:
        # No relationships found, add a placeholder node to indicate emptiness
        nodes.append({
            "id": "empty",
            "label": "Taqqoslash ob'ekti yo'q",
            "title": "Wikidata da ushbu shaxs uchun bog'lanishlar kiritilmagan",
            "group": "cat_reference",
            "value": 10
        })
        edges.append({
            "from": main_id, "to": "empty", "arrows": ""
        })

    return jsonify({
        "nodes": nodes,
        "edges": edges
    })

@app.route('/')
@app.route('/<path:path>')
def serve_index_and_static(path='index.html'):
    directory = os.path.dirname(os.path.abspath(__file__))
    # Ruxsat etilgan fayl turlarini xavfsizlik uchun tekshiramiz
    if path != 'index.html' and not path.endswith('.js') and not path.endswith('.css') and not path.endswith('.html'):
        return jsonify({"error": "Not found"}), 404
        
    served_path = path
    if not os.path.exists(os.path.join(directory, path)):
        served_path = 'index.html'
        
    response = send_from_directory(directory, served_path)
    if served_path == 'index.html':
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    app.run(debug=True)
