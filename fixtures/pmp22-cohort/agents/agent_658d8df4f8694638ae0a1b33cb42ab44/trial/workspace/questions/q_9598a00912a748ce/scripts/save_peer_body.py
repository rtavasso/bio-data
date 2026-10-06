import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
data = json.loads((root/'inputs/community/parent-critique.json').read_text())
(root/'inputs/community/parent-critique.txt').write_text(data['content']['body'])
print(data['content']['body'])
