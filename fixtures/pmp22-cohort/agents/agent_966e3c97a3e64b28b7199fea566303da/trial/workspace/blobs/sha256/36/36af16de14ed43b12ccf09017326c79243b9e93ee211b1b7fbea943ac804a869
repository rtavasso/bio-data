"""Read-only JSON/community inspection; never execute inherited scientific code."""
import json
import subprocess
import sys
from pathlib import Path

if sys.argv[1] == 'json':
    obj = json.loads(Path(sys.argv[2]).read_text())
    print(json.dumps(obj, indent=2, ensure_ascii=False))
elif sys.argv[1] == 'search':
    for query in sys.argv[2:]:
        p = subprocess.run(['./bin/bio', 'community', 'search', '--text', query, '--limit', '100'], capture_output=True, text=True, check=True)
        obj = json.loads(p.stdout)
        dest = Path(__file__).resolve().parents[1] / 'inputs' / 'community'
        dest.mkdir(parents=True, exist_ok=True)
        (dest / (query.replace(' ', '_') + '.json')).write_text(p.stdout)
        print(query, 'total', obj['total'], 'next_offset', obj['next_offset'])
        for x in obj['items']:
            print(x['subject'], x['title'], 'superseded', x['superseded_by'])
