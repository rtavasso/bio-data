"""Prepare a byte-identical PDF view for the local document reader."""
from pathlib import Path
q = Path(__file__).resolve().parents[1]
p = q / 'inputs/primary/Hollien2009-full-pdf.source'
dest = q / 'inputs/primary/Hollien2009-full.pdf'
assert p.read_bytes().startswith(b'%PDF-')
dest.write_bytes(p.read_bytes())
print(dest)
