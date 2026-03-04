import urllib.parse
from app import get_wikipedia_summary, resolve_author_info

queries = ["erkin vohidov", "hamza"]
for q in queries:
    canonical_name, _ = resolve_author_info(q)
    if not canonical_name:
        canonical_name = q
    wiki = get_wikipedia_summary(canonical_name)
    print(f"[{q}] wiki snippet:", wiki[:100] if wiki else "None")

