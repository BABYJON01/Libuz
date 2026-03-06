import json
import re

def parse_authors():
    with open('local_authors_raw.txt', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    authors = []
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('Буюк юрт алломалари'):
            continue
            
        parts = line.split('\t')
        if len(parts) >= 2:
            # First part is number (e.g. 1.), second part might be empty, third is name
            name = ""
            for p in parts[1:]:
                if p.strip() and not p.strip().isdigit():
                    name = p.strip()
                    break
                    
            if not name:
                continue
                
            # If line just has numbers and names, we handle loosely
            if len(parts) < 3:
                authors.append({
                    "id": f"local_{len(authors)}",
                    "name": name,
                    "description": "",
                    "alias": "",
                    "works": [],
                    "locations": [],
                    "keywords": []
                })
                continue
            
            # Extract elements based on tabs (approximate structure of the copied table)
            # Column 1: Number
            # Column 2: Name
            # Column 3: Birth dates / places
            # Column 4: Alias / Full Name
            # Column 5: Works
            # Column 6: Affiliations / Cities
            # Column 7: Keywords / Mentors / Students
            
            # The split by tab might be inconsistent, so we clean up empty strings
            clean_parts = [p.strip() for p in parts if p.strip() and not re.match(r'^\d+\.$', p.strip())]
            
            if len(clean_parts) == 0:
                continue
                
            actual_name = clean_parts[0]
            dates_places = clean_parts[1] if len(clean_parts) > 1 else ""
            alias = clean_parts[2] if len(clean_parts) > 2 else ""
            works_raw = clean_parts[3] if len(clean_parts) > 3 else ""
            afilliation = clean_parts[4] if len(clean_parts) > 4 else ""
            keywords = clean_parts[5] if len(clean_parts) > 5 else ""
            
            works = [w.strip() for w in works_raw.split(',') if w.strip() and w.strip() != 'йўқ']
            kw = [k.strip() for k in keywords.split(',') if k.strip()]
            
            authors.append({
                "id": f"local_{len(authors)}",
                "name": actual_name,
                "description": dates_places,
                "alias": alias,
                "works": works,
                "locations": afilliation,
                "keywords": kw
            })

    with open('local_authors.json', 'w', encoding='utf-8') as f:
        json.dump(authors, f, ensure_ascii=False, indent=2)
        
    print(f"Parsed {len(authors)} authors successfully.")

if __name__ == '__main__':
    parse_authors()
