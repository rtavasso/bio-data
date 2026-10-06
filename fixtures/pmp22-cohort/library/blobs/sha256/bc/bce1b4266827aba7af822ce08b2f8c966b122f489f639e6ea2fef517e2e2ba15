"""Preserve actual public HTTP/CLI responses; never execute retrieved content."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib
import httpx

Q = Path(__file__).resolve().parents[1]
ROOT = Q.parents[2]


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(obj, f, indent=2, allow_nan=False)
        f.write('\n')


def http(name, url):
    dest = Q / 'inputs/public' / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or Path(str(dest) + '.receipt.json').exists():
        raise FileExistsError(dest)
    receipt = {'url': url, 'started_utc': dt.datetime.now(dt.UTC).isoformat()}
    config = ROOT / 'workspace/config.toml'
    cfg = tomllib.loads(config.read_text()) if config.exists() else {}
    budget = cfg.get('budgets', {})
    reserve = max(budget.get('reserve_bytes', 5 * 2**30),
                  int(shutil.disk_usage(ROOT).total * budget.get('reserve_fraction', 0)))
    h = hashlib.sha256()
    n = 0
    try:
        with httpx.Client(follow_redirects=True, timeout=120) as client:
            with client.stream('GET', url) as r:
                receipt.update(status=r.status_code, final_url=str(r.url), headers=dict(r.headers))
                with dest.open('xb') as f:
                    for chunk in r.iter_bytes():
                        if shutil.disk_usage(ROOT).free - len(chunk) < reserve:
                            raise OSError('disk reserve')
                        f.write(chunk)
                        h.update(chunk)
                        n += len(chunk)
        receipt['transport_complete'] = True
    except Exception as e:
        receipt.update(error=repr(e), transport_complete=False)
    receipt.update(bytes=n, sha256=h.hexdigest(), ended_utc=dt.datetime.now(dt.UTC).isoformat())
    save(Path(str(dest) + '.receipt.json'), receipt)
    print(json.dumps({'name': name, **{k: receipt.get(k) for k in ('status','bytes','sha256','error')}}))


def bio(name, args):
    path = Q / 'inputs/community' / (name + '.json')
    if path.exists():
        raise FileExistsError(path)
    r = subprocess.run(['./bin/bio', *args], cwd=ROOT, capture_output=True, text=True)
    save(Path(str(path) + '.receipt.json'), {'command': ['./bin/bio', *args], 'exit_code': r.returncode,
         'stderr': r.stderr, 'time': dt.datetime.now(dt.UTC).isoformat(),
         'stdout_sha256': hashlib.sha256(r.stdout.encode()).hexdigest()})
    try:
        obj = json.loads(r.stdout)
    except json.JSONDecodeError:
        obj = {'stdout': r.stdout}
    save(path, obj)
    if isinstance(obj, dict) and 'items' in obj:
        print(json.dumps({'name': name, 'total': obj.get('total'), 'next_offset': obj.get('next_offset'),
              'items': [{k:x.get(k) for k in ('subject','title','superseded_by')} for x in obj['items']]}))
    elif isinstance(obj, dict) and 'content' in obj:
        print(json.dumps({'name': name, 'id': obj['id'], 'title': obj['content']['title'],
                          'body': obj['content']['body'], 'replies': obj.get('replies'),
                          'superseded_by': obj.get('superseded_by')}))
    else:
        print(json.dumps(obj))
    r.check_returncode()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['http','bio'])
    p.add_argument('name')
    p.add_argument('args', nargs=argparse.REMAINDER)
    a = p.parse_args()
    if a.mode == 'http':
        http(a.name, a.args[0])
    else:
        bio(a.name, a.args)
