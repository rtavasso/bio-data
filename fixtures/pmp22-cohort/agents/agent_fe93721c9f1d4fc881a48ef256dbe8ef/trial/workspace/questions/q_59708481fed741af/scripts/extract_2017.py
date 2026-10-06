from html.parser import HTMLParser
from pathlib import Path
import json

q = Path(__file__).resolve().parents[1]
class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self.skip += 1
        if tag in {'p', 'h1', 'h2', 'h3', 'h4', 'li', 'section', 'figure'}:
            self.parts.append('\n')
        for key, val in attrs:
            if key == 'href' and val:
                self.links.append(val)
    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self.skip -= 1
        if tag in {'p', 'h1', 'h2', 'h3', 'h4', 'li'}:
            self.parts.append('\n')
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)
p = Parser()
p.feed((q / 'inputs/public/PMC5800313.html').read_text())
text = '\n'.join(' '.join(line.split()) for line in ''.join(p.parts).splitlines() if line.strip())
(q / 'outputs/PMC5800313.source.txt').write_text(text + '\n')
print(json.dumps([x for x in p.links if '.pdf' in x]))
