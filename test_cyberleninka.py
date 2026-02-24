import requests
from bs4 import BeautifulSoup

def test_search(query):
    # CyberLeninka search URL
    url = f"https://cyberleninka.ru/search?q={query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    print(f"Fetching: {url}")
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        return
        
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Try to find search results
    # Cyberleninka usually uses <li> elements in a <ul> with class like 'list' or similar
    results = soup.find_all('li')
    
    found_articles = 0
    for li in results:
        title_elem = li.find('h2')
        if not title_elem:
            title_elem = li.find('a', href=lambda href: href and '/article/n/' in href)
            
        if title_elem:
            title = title_elem.text.strip()
            link = title_elem['href'] if title_elem.name == 'a' else title_elem.find('a')['href']
            
            # Find year and authors
            # This is a guess, need to see actual HTML to parse correctly
            print(f"Found: {title} | Link: {link}")
            print("---")
            found_articles += 1
            if found_articles >= 5:
                break
                
    if found_articles == 0:
        print("No articles found or HTML structure changed.")
        with open("cyber_output.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        print("Saved to cyber_output.html")

if __name__ == "__main__":
    test_search("blockchain")
