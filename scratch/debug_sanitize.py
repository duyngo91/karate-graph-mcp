import sys
sys.path.insert(0, r'e:\Project\auto\karate_graph\src')

from karate_graph_analyzer.parser.config_parser import KarateConfigParser
from karate_graph_analyzer.models import ParserConfig
from karate_graph_analyzer.parser.extractors.api_extractor import ApiExtractor
import re

# Setup
root = r'e:\Project\auto\karate-fw\karate-core'
cp = KarateConfigParser(root)
auto_config = cp.get_base_url_mapping()
reverse_config = cp.global_reverse_mapping

parser_config = ParserConfig(
    base_url_mapping=auto_config,
    variable_patterns=auto_config,
    global_reverse_mapping=reverse_config,
)
extractor = ApiExtractor(parser_config)

# Test sanitize_url directly
test_urls = [
    "https://t24.com",
    "https://ecommerce.api.com/api/v1/orders/",
    "/api/v2/payment",
    "t24Url",
]
print("=== sanitize_url results ===")
for url in test_urls:
    result = extractor.sanitize_url(url)
    print(f"  sanitize_url({repr(url)}) => {repr(result)}")

# Test the full regex match + lookup flow manually
print("\n=== Manual step trace for 'url t24Url' ===")
step_text = "url t24Url"
var_url_pattern = re.compile(
    r"""\burl\s+(['"]([^'"]+)['"]\s*\+\s*)?([a-zA-Z_][a-zA-Z0-9_\.]*)""",
    re.IGNORECASE
)
for match in var_url_pattern.finditer(step_text):
    prefix_val = match.group(2)
    var_name = match.group(3)
    print(f"  Match: prefix={repr(prefix_val)}, var_name={repr(var_name)}")
    
    # Skip non-url variables
    if var_name.lower() in ['path', 'method', 'request', 'response', 'headers']:
        print(f"  SKIPPED: in blacklist")
        continue
    
    resolved_url = auto_config.get(var_name) or auto_config.get(f"${{{var_name}}}")
    print(f"  resolved_url = {repr(resolved_url)}")
    
    if resolved_url:
        full_val = resolved_url
        if prefix_val:
            full_val = prefix_val + resolved_url
        print(f"  full_val = {repr(full_val)}")
        
        sanitized = extractor.sanitize_url(full_val)
        print(f"  sanitize_url(full_val) = {repr(sanitized)}")
        
        if sanitized:
            logical = extractor.normalize_logical_url(sanitized)
            print(f"  normalize_logical_url => {repr(logical)}")
        else:
            print(f"  *** BLOCKED BY sanitize_url! Nothing emitted ***")

# Check what the actual sanitize regex is
print("\n=== Checking sanitize_url regex ===")
url = "https://t24.com"
url = url.strip().strip('"').strip("'")
print(f"After strip: {repr(url)}")
regex_check = re.match(r'^[a-zA-Z0-9_\-\.\\/\$\{\}]+$', url)
print(f"Regex match '^[a-zA-Z0-9_\\-\\.\\\\/\\$\\{{\\}}]+$': {regex_check}")
print(f"  (colon ':' is NOT in the allowed chars => BLOCKED)")
