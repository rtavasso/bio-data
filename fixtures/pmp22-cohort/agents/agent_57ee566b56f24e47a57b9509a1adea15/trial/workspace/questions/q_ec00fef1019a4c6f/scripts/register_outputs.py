"""Register executed products and read each exact artifact back. No model dispatch."""
import hashlib
import json
import os
import subprocess
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_ec00fef1019a4c6f'
qid=q.name
out=q/'outputs'
def call(args,dest):
    run=subprocess.run(['./bin/bio',*args],capture_output=True,text=True)
    dest.write_text(run.stdout)
    if run.stderr:
        dest.with_suffix(dest.suffix+'.stderr').write_text(run.stderr)
    if run.returncode:
        raise RuntimeError(f'CLI failed: {args}: {run.stdout} {run.stderr}')
    return json.loads(run.stdout)
def preserve(p,role='source'):
    return call(['object','add',str(p),'--classification',role],out/f'object-{p.name}.json')['blob']
def verify(rec,name):
    obj=call(['artifact','show',rec['artifact']],out/f'verified-{name}.json')
    assert obj['output_blob']==rec['output_blob']
    assert hashlib.sha256(Path(obj['path']).read_bytes()).hexdigest()==rec['output_blob']
    assert any(r['question_id']==qid and r['relationship']=='produced' for r in obj['questions'])
    return {'artifact':rec['artifact'],'output_blob':rec['output_blob'],'readback_verified':True}
registrations={}
first=json.loads((out/'register-paired-summary.json').read_text())
assert not first['conflicting_outputs'] and first['warning'] is None
registrations['paired-audit-summary.json']=verify(first,'paired-summary')
audit=json.loads((out/'sample-unit-audit.json').read_text())
ainputs=[preserve(q/item['path']) for item in audit['input_manifest']]
ainputs.extend(preserve(q/'inputs/public'/name) for name in ['repair-supp4.xlsx','repair-supp4-pmc.response','repair-publisher.html'])
aref=preserve(out/'audit-execution-r001.json','reference')
paired_input= json.loads((out/'object-p5-metadata.json').read_text())['blob']
for filename,title,role,code,inputs,ref,params in [
 ('paired-gate-results.tsv','P5 paired gate gene and pseudocount sensitivity table','paired-gate-sensitivity-tsv','paired_gate_audit.py',['1327d696aef274054f77adee2331a90dd2a0d88d7be3ba2bd119ea44598d4aba',paired_input,'artifact_cf14cda0f514a5bfad505daa46f56be382ca83f46a523d05f1fff58a3023527e'],'c46b6aaf3b4f3cf2ad173df1b41ac5e04a5f0287a49d1a0e83f107b42e3bafac',{'retrospective':True,'contrast':'nmSC_minus_mSC','pseudocounts_rpkm':[0,0.1,1]}),
 ('sample-unit-audit.json','PMP22 compartment sample-unit and eligibility audit','sample-unit-audit-json','assemble_audit.py',ainputs,aref,{'judgments':'agent-authored; native fields preserved','gene_rna_not_promoter':True}),
 ('sample-units.tsv','PMP22 source sample units with donor and compartment restrictions','sample-unit-map-tsv','assemble_audit.py',ainputs,aref,{'judgments':'agent-authored; native fields preserved','gene_rna_not_promoter':True}),
 ('applicability.tsv','PMP22 eight-context applicability and blocked inference table','context-applicability-tsv','assemble_audit.py',ainputs,aref,{'judgments':'agent-authored; native fields preserved','gene_rna_not_promoter':True})]:
    receipt=out/f'register-{filename}.json'
    assert not receipt.exists(),receipt
    args=['register',str(out/filename),'--question',qid,'--title',title,'--summary','Source-backed bounded audit; null/unknown units retained; no cell-fraction fit or genotype-matched P7 causal inference.','--code',str(q/'scripts'/code),'--output-role',role,'--reference',ref,'--parameters',json.dumps(params),'--environment',str(out/'environment.json')]
    for item in inputs:
        args+=['--input',item]
    rec=call(args,receipt)
    assert not rec['conflicting_outputs'] and rec['warning'] is None,rec
    registrations[filename]=verify(rec,filename)
    (out/'registrations.json').write_text(json.dumps(registrations,indent=2))
    print(filename,rec['artifact'])
print('All exact readbacks verified')
