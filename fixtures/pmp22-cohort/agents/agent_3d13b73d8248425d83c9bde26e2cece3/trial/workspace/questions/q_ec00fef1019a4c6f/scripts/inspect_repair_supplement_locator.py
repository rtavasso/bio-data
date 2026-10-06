"""Inspect the native supplement element shape without running document code."""
import os
from pathlib import Path
from defusedxml import ElementTree as ET
h='97346c435e332d809322247b90f7c7aded6bb61d0b2c1fe9415ef55e2cbaf3d3'
p=Path(os.environ['BIO_WORKSPACE'])/'blobs/sha256'/h[:2]/h
root=ET.parse(p).getroot()
assert root is not None
for node in root.iter('supplementary-material'):
    text=' '.join(''.join(node.itertext()).split())
    if 'All FPKM data' in text:
        print(ET.tostring(node,encoding='unicode'))
