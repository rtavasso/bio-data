"""Bounded text search and processed matrix header inspection after search_files failure."""
import gzip
import re
import sys
from pathlib import Path

mode = sys.argv[1]
if mode == 'search':
    pattern = re.compile(sys.argv[2], re.I)
    for arg in sys.argv[3:]:
        p = Path(arg)
        text = gzip.open(p, 'rt').read() if p.suffix == '.gz' else p.read_text()
        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                print(p.name, i, line)
elif mode == 'header':
    for arg in sys.argv[2:]:
        p = Path(arg)
        with gzip.open(p, 'rt') as f:
            print(p.name)
            for _ in range(4):
                print(f.readline().rstrip())
