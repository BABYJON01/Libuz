import requests
author_name = "albert einstein"
en_wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{author_name.title()}"
print(en_wiki_url)
resp = requests.get(en_wiki_url)
print(resp.status_code)
print(resp.text)
