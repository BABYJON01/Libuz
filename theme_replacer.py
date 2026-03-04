import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Define mapping for hardcoded colors to CSS variables
color_map = {
    r'color:\s*#e2e8f0;': 'color: var(--text-color);',
    r'color:\s*#94a3b8;': 'color: var(--text-muted);',
    r'color:\s*#64748b;': 'color: var(--text-muted);',
    r'color:\s*#cbd5e1;': 'color: var(--text-color);',
    r'color:\s*white;': 'color: var(--text-color); /* white */',
    
    r'background:\s*rgba\(15,\s*23,\s*42,\s*0\.6\);': 'background: var(--input-bg);',
    r'background:\s*rgba\(15,\s*23,\s*42,\s*0\.8\);': 'background: var(--overlay);',
    r'background:\s*rgba\(15,\s*23,\s*42,\s*0\.9\);': 'background: var(--modal-bg);',
    r'background:\s*rgba\(30,\s*41,\s*59,\s*0\.95\);': 'background: var(--modal-bg);',
    
    r'background:\s*rgba\(255,\s*255,\s*255,\s*0\.03\);': 'background: var(--item-bg);',
    r'background:\s*rgba\(255,\s*255,\s*255,\s*0\.08\);': 'background: var(--item-hover-bg);',
    r'background:\s*rgba\(255,\s*255,\s*255,\s*0\.1\);': 'background: var(--item-hover-bg);',
    r'background:\s*rgba\(255,\s*255,\s*255,\s*0\.05\);': 'background: var(--item-hover-bg);',
    
    r'border-color:\s*rgba\(255,\s*255,\s*255,\s*0\.2\);': 'border-color: var(--item-hover-border);',
    r'border-bottom:\s*1px\s*solid\s*rgba\(255,\s*255,\s*255,\s*0\.05\);': 'border-bottom: 1px solid var(--border);',
    r'border:\s*1px\s*solid\s*rgba\(255,\s*255,\s*255,\s*0\.1\);': 'border: 1px solid var(--border);',
    r'background-color:\s*#1e293b;': 'background-color: var(--panel-bg);',
}

# Apply root vars
root_vars = """        :root {
            --bg-color: #0f172a;
            --panel-bg: rgba(30, 41, 59, 0.7);
            --text-color: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --border: rgba(255, 255, 255, 0.1);
            --node-main: #3b82f6;
            --node-ref: #94a3b8;
            
            --input-bg: rgba(15, 23, 42, 0.6);
            --item-bg: rgba(255, 255, 255, 0.03);
            --item-hover-bg: rgba(255, 255, 255, 0.08);
            --item-hover-border: rgba(255, 255, 255, 0.2);
            --modal-bg: rgba(30, 41, 59, 0.95);
            --overlay: rgba(15, 23, 42, 0.8);
        }

        body.light-mode {
            --bg-color: #f8fafc;
            --panel-bg: rgba(255, 255, 255, 0.85);
            --text-color: #0f172a;
            --text-muted: #64748b;
            --border: rgba(0, 0, 0, 0.1);
            
            --input-bg: rgba(255, 255, 255, 1);
            --item-bg: rgba(0, 0, 0, 0.02);
            --item-hover-bg: rgba(0, 0, 0, 0.05);
            --item-hover-border: rgba(0, 0, 0, 0.15);
            --modal-bg: rgba(255, 255, 255, 0.95);
            --overlay: rgba(255, 255, 255, 0.8);
        }"""

# Replace the :root block
content = re.sub(r':root\s*\{[^}]+\}', root_vars, content, count=1)

# Apply color replacements within the style tag
style_start = content.find('<style>')
style_end = content.find('</style>')
style_content = content[style_start:style_end]

for pattern, replacement in color_map.items():
    style_content = re.sub(pattern, replacement, style_content)

content = content[:style_start] + style_content + content[style_end:]

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated CSS with variables.")
