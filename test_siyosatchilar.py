import requests
import urllib.parse

# 1. Search for 'Siyosatchilar'
print("Searching for Siyosatchilar...")
search_res = requests.get('http://127.0.0.1:5000/api/search?q=Siyosatchilar')
if search_res.status_code == 200:
    data = search_res.json()
    results = data.get('results', [])
    if results:
        first_paper = results[0]
        print(f"First result ID: {first_paper.get('id')}")
        
        # 2. Try to get its network
        # The frontend uses encodeURIComponent
        encoded_id = urllib.parse.quote(first_paper.get('id', ''), safe='')
        print(f"Encoded ID sent to API: {encoded_id}")
        
        network_url = f'http://127.0.0.1:5000/api/paper/{encoded_id}/network'
        print(f"Fetching network from: {network_url}")
        
        net_res = requests.get(network_url)
        print(f"Network status: {net_res.status_code}")
        print(f"Network response: {net_res.text}")
    else:
        print("No results found in search.")
else:
    print(f"Search failed: {search_res.status_code}")
