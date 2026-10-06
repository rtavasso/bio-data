"""Extract readable paragraphs and link inventories from acquired primary text."""
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from defusedxml import ElementTree as ET
ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'inputs/public'

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.links = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag in {'script', 'style'}:
            self.skip += 1
        if tag == 'a' and 'href' in attr:
            self.links.append(attr['href'])
        if tag in {'p', 'div', 'h1', 'h2', 'h3', 'li', 'br'}:
            self.text.append('\n')
    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self.skip -= 1
    def handle_data(self, text):
        if not self.skip:
            self.text.append(text)

for name in (sys.argv[1:] or ['JCI201297.html', 'PMC6979480.xml', 'PMC7771966.xml']):
    if name.endswith('.html'):
        parser = Page()
        parser.feed((P/name).read_text())
        lines = [' '.join(x.split()) for x in ''.join(parser.text).splitlines() if x.strip()]
        links = list(dict.fromkeys(parser.links))
    else:
        root = ET.parse(P/name).getroot()
        lines = [f"{node.tag} {node.get('id','')}: "+' '.join(''.join(node.itertext()).split()) for node in root.iter() if node.tag in {'article-title','title','p','caption','supplementary-material','table-wrap'}]
        links = [value for node in root.iter() for attr, value in node.attrib.items() if attr.endswith('href')]
    (P/(name+'.txt')).write_text('\n'.join(lines))
    (P/(name+'.links.json')).write_text(json.dumps(links, indent=2))
    print(name)
    for link in links:
        if any(x in link.lower() for x in ['supp','source','data','xlsx','xls','media','download','zenodo']):
            print(link)
