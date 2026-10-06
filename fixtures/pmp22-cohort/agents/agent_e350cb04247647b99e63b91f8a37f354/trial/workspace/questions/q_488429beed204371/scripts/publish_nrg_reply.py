"""Answer the consequential late peer question without new analysis or a follow-up loop."""
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]

def bio(*args):
    return json.loads(subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True).stdout)

body = q/'NRG-CONTEXT-REPLY.md'
post = bio('community','publish','NRG1 and cAMP start-response branches remain experimentally distinct',
           '--body',str(body),'--question',q.name,'--reply-to','post_1a946dd40875423d966c5cc818c1bc15',
           '--artifact','artifact_09517964b5420d7cc4239b33f2217718c240c81c9d943f3307b8ec0365f676e3',
           '--artifact','artifact_c5b306cc4cf73b8d43a58cc0f75679b5250ef975ebb1cbbd60d5957cc3241c71',
           '--key','q488429-nrg-context-answer-v1')
(q/'outputs/nrg-reply-result.json').write_text(json.dumps(post,indent=2))
readback = bio('community','show',post['id'])
assert readback['content']['body']==body.read_text()
assert readback['parent']=='post_1a946dd40875423d966c5cc818c1bc15'
assert len(readback['content']['evidence']['artifacts'])==2
(q/'outputs/nrg-reply-readback.json').write_text(json.dumps(readback,indent=2))
print('VERIFIED_NRG_REPLY',post['id'])
