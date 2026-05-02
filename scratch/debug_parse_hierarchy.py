import sys
sys.path.insert(0, r'e:\Project\auto\karate_graph\src')

# Simulate parse_api_hierarchy logic

test_inputs = [
    "${t24Url}/api/v2/payment",
    "${t24Url}",
    "https://t24.com/api/v2/payment",
    "ecommerce.api.com/api/v1/orders",
    "/api/v2/payment",
]

def parse_api_hierarchy_sim(endpoint):
    if not endpoint or endpoint == '/':
        return []
    
    endpoint_clean = endpoint.replace('http://', '').replace('https://', '')
    if endpoint_clean.startswith('localhost'):
        endpoint_clean = endpoint_clean[len('localhost'):].lstrip(':0123456789')
    
    if not endpoint_clean or endpoint_clean == '/':
        return []
    
    # BUG HERE: endpoint_clean is overwritten with original endpoint!
    endpoint_clean = endpoint.strip()  # <-- This resets to original!
    domain = None
    
    # Handle protocol
    protocol = ""
    if "://" in endpoint_clean:
        parts = endpoint_clean.split("://", 1)
        protocol = parts[0] + "://"
        endpoint_clean = parts[1]
    
    print(f"\n  Input: {repr(endpoint)}")
    print(f"  After protocol strip: endpoint_clean={repr(endpoint_clean)}, protocol={repr(protocol)}")
    
    if endpoint_clean.startswith('/'):
        domain, path = None, endpoint_clean
        print(f"  => Path only: domain=None, path={repr(path)}")
    else:
        parts = endpoint_clean.split('/', 1)
        first_part = parts[0]
        path = '/' + parts[1] if len(parts) > 1 else ""
        print(f"  first_part={repr(first_part)}, path={repr(path)}")
        
        # Skip rev_map for sim - check if first_part starts with ${}
        if '.' in first_part or first_part.startswith('${'):
            domain = first_part
        else:
            domain, path = None, '/' + endpoint_clean
        
        print(f"  domain={repr(domain)}")
    
    segments = []
    if domain: segments.append(domain)
    if path: segments.extend([p for p in path.split('/') if p])
    print(f"  => segments: {segments}")
    return segments

for inp in test_inputs:
    parse_api_hierarchy_sim(inp)

print("\n\n=== KEY BUG ===")
print("Line: endpoint_clean = endpoint.strip()  <-- RESETS endpoint_clean to ORIGINAL with ${...}!")
print("So '${t24Url}/api/v2/payment'.startswith('/') is FALSE")
print("Then split('/',1) => ['${t24Url}', 'api/v2/payment']")
print("first_part = '${t24Url}'  => has '${'  => domain = '${t24Url}' ✓")
print("But wait, does it actually work? Let me check...")

ep = "${t24Url}/api/v2/payment"
endpoint_clean = ep.strip()  # = "${t24Url}/api/v2/payment"
parts = endpoint_clean.split('/', 1)
print(f"\nparts = {parts}")
print(f"first_part = {repr(parts[0])}")
print(f"starts with '${{{' = {parts[0].startswith('${')}") 
