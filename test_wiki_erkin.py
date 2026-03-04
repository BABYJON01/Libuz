import requests

print(requests.get("https://uz.wikipedia.org/api/rest_v1/page/summary/Erkin_Vohidov", headers={'User-Agent': 'LitmapsClone/1.0 (contact@example.com)'}).status_code)
print(requests.get("https://uz.wikipedia.org/api/rest_v1/page/summary/Erkin_Vohidov", headers={'User-Agent': 'LitmapsClone/1.0 (contact@example.com)'}).json().get('title'))

print(requests.get("https://uz.wikipedia.org/api/rest_v1/page/summary/Erkin Vohidov", headers={'User-Agent': 'LitmapsClone/1.0 (contact@example.com)'}).status_code)

print(requests.get("https://en.wikipedia.org/api/rest_v1/page/summary/Erkin Vohidov", headers={'User-Agent': 'LitmapsClone/1.0 (contact@example.com)'}).status_code)
