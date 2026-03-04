import requests
import urllib.parse
import json

def search_wikidata_entity(name):
    # Search for Q-ID by name
    url = f"https://www.wikidata.org/w/api.php?action=wbsearchentities&search={urllib.parse.quote(name)}&language=en&format=json"
    headers = {'User-Agent': 'LibUZ/1.0 (https://libuz.vercel.app)'}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data.get("search") and len(data["search"]) > 0:
            return data["search"][:5] # Return the first matching entity
    return []

def get_wikidata_network(entity_id, max_nodes=20):
    query = """
    SELECT ?rel ?relLabel ?item ?itemLabel ?itemDescription ?dir WHERE {
      VALUES ?relProp { wdt:P737 wdt:P802 wdt:P1066 wdt:P800 wdt:P69 wdt:P26 wdt:P40 wdt:P22 wdt:P25 wdt:P3373 wdt:P1038 }
      
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
      
      SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en,ru,uz". }
    } LIMIT %d
    """ % (entity_id, entity_id, max_nodes)
    
    url = "https://query.wikidata.org/sparql"
    headers = {
        'User-Agent': 'LibUZ/1.0 (https://libuz.vercel.app)',
        'Accept': 'application/sparql-results+json'
    }
    response = requests.get(url, params={'query': query}, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error {response.status_code}: {response.text}")
        return None

if __name__ == "__main__":
    name = "Albert Einstein"
    print(f"Searching for {name}...")
    entities = search_wikidata_entity(name)
    if entities:
        for i, entity in enumerate(entities):
            print(f"{i+1}. Found: {entity['id']} - {entity.get('label')} ({entity.get('description')})")
        
        # Test query with the first one that is a human
        target_entity = entities[0]
        for e in entities:
            if 'human' in str(e.get('description', '')).lower() or 'poet' in str(e.get('description', '')).lower():
                target_entity = e
                break
                
        print(f"\nUsing {target_entity['id']} ({target_entity.get('label')})")
        print("Fetching network...")
        network = get_wikidata_network(target_entity['id'])
        if network:
            import json
            with open('wiki_out.json', 'w', encoding='utf-8') as f:
                json.dump(network, f, indent=2, ensure_ascii=False)
            print("Saved to wiki_out.json")
    else:
        print("Not found.")
