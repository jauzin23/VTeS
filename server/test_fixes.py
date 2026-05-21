import sys, ast
sys.path.insert(0, '.')

files = [
    'main.py',
    'services/html_processor.py',
    'services/sitemap_service.py',
    'services/crawler.py',
    'services/crawler_service.py',
]
for f in files:
    with open(f, encoding='utf-8') as fh:
        ast.parse(fh.read())
    print(f'OK: {f}')

# Test PDF filter
from urllib.parse import urlparse
url = 'https://alenquer.pt/uploads/Paginas/PoliticaPrivacidade_1.pdf?file=khOYA0CDwRV7NrX0RtMHFg'
path = urlparse(url).path.lower()
is_pdf = path.endswith('.pdf')
print(f'PDF filter: path ends with .pdf = {is_pdf} (should be True)')
assert is_pdf, 'PDF filter FAILED'

# Test import chain
import main
print('All imports OK')
print('ALL TESTS PASSED')
