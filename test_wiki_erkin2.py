import sys
sys.path.append('.')
from app import get_wikipedia_summary
import requests

def test_wiki(author_name):
    headers = {'User-Agent': 'LitmapsClone/1.0 (contact@example.com)'}
    uz_wiki_url = f"https://uz.wikipedia.org/api/rest_v1/page/summary/{author_name.title()}"
    print(f"URL: {uz_wiki_url}")
    try:
        resp = requests.get(uz_wiki_url, headers=headers, timeout=3)
        print(f"UZ status: {resp.status_code}")
        if resp.status_code == 200:
            extract = resp.json().get('extract')
            print(f"Got extract: {bool(extract)}")
            return extract
    except Exception as e:
        print(f"UZ error: {e}")
    
    return None

test_wiki("erkin vohidov")
