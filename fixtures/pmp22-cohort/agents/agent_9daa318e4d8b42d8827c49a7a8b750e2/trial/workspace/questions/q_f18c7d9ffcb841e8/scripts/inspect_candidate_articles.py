"""Identify the two article-like blob hits without executing their content."""
import json
from html.parser import HTMLParser
from pathlib import Path
from defusedxml import ElementTree as ET

q = Path(__file__).resolve().parents[1]
w = q.parents[1]
xh = 'd6e5c0718b0497db3ee434ca389047945e908ffb635824409d8e736eabf45730'
hh = '7b0a5fe4f9c5cdee5f5c45046457dc74a9716945bb88f7aff0f982ce844280ac'
tree = ET.parse(w / 'blobs/sha256' / xh[:2] / xh)
ids = [{'type': x.get('pub-id-type'), 'id': ''.join(x.itertext())} for x in tree.findall('./front/article-meta/article-id')]
print('XML ARTICLE IDENTIFIERS', json.dumps(ids))
assert not any(x['id'] in {'6623163', 'PMC6623163', '21715627'} for x in ids)


class Meta(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('name') in {'citation_title', 'citation_pmid', 'citation_doi', 'citation_pmcid'}:
            self.fields.append(attrs)


parser = Meta()
parser.feed((w / 'blobs/sha256' / hh[:2] / hh).read_text())
print('HTML ARTICLE IDENTIFIERS', json.dumps(parser.fields))
assert parser.fields
assert not any(x.get('content') in {'6623163', 'PMC6623163', '21715627'} for x in parser.fields)
