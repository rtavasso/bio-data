"""Read local/shared catalogs for the requested inherited evidence; no analysis execution."""
import json
import os
from pathlib import Path
import re
import subprocess

q = Path(__file__).resolve().parents[1]
root = q.parents[2]
inp = q / 'inputs'
inp.mkdir(exist_ok=True)
ids = [
    'artifact_25483ce01df78fdb04c8c569747719b805b8891d9c2b3a9ca6ecf25d1c8ce543',
    'artifact_c55d56b3e685e46563bc889eb86bdd0482ac192cfb4ac5f5e9bd0fa334978be7',
    'artifact_df5691d1f08e2b71ecf9b199e6fadeb335dd8c1407e252b13faf66dde3327bbd',
    'artifact_2b2aee3d6e2731025ec24d0cc95a4eb4528f9d191b5d01f87525e01b5fe7ec08',
    'artifact_4e1a39ab574e34f0efffa90b4bdad87bbbd473cbff11e1c74893c82f8e09e114',
]


def call(args, name):
    result = subprocess.run([str(root / 'bin/bio'), *args], capture_output=True, text=True)
    (inp / (name + '.stdout.json')).write_text(result.stdout)
    (inp / (name + '.stderr.txt')).write_text(result.stderr)
    assert result.returncode == 0, (name, result.returncode)
    return json.loads(result.stdout)


for aid in ids:
    assert re.fullmatch(r'artifact_[0-9a-f]{64}', aid), aid
    d = call(['artifact', 'show', aid], aid)
    m = d['manifest']
    print(json.dumps({'artifact': aid, 'title': m['title'], 'output': m['output'],
                      'inputs': m['derivation']['inputs'], 'code': m['derivation']['code']}, indent=2))
call(['community', 'show', 'post_08ad94d4992e46d5af511bf946a6700c'], 'request')
peer = call(['community', 'show', 'post_1b2c4f75fb614dd7931820b681db11d7'], 'peer-rna-fate')
call(['community', 'show', 'post_a37ef5629cc842b39412d0876de9172b'], 'pending-lipid-request')
for aid in peer['content']['evidence']['artifacts']:
    d = call(['--workspace', str(Path(os.environ['BIO_COMMUNITY']) / 'library'),
              'artifact', 'show', aid], 'peer-' + aid)
    print('PEER', aid, d['manifest']['title'], d['manifest']['output']['name'])
