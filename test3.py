import requests
resp = requests.get("https://api.openalex.org/works?search=machine+learning&per-page=10")
data = resp.json()
print("Top 10 OA status:")
for work in data['results']:
    oa = work.get('open_access', {})
    is_oa = oa.get('is_oa')
    url = oa.get('oa_url')
    print(f"OA: {is_oa}, URL: {url}")
