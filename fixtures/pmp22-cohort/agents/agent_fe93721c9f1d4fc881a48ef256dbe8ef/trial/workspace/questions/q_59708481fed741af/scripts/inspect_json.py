import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
data = json.loads(source.read_text())
text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)
if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(text + '\n')
    print(f'Pretty-printed {source.name} to {sys.argv[2]}')
else:
    print(text)
