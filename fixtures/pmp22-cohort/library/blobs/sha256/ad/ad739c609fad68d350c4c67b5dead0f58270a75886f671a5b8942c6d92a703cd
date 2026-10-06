"""Extract exact source-methods locators; no new target measurements or fraction fits."""
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from defusedxml import ElementTree as ET
ws=Path(os.environ['BIO_WORKSPACE'])
q=ws/'questions/q_ec00fef1019a4c6f'
xml_hash='97346c435e332d809322247b90f7c7aded6bb61d0b2c1fe9415ef55e2cbaf3d3'
audit_hash='c46936b00bd2abcc3b2cbc3971dfb190f6915aedbe9a7b15b88161198c819786'
def source(h):
    p=ws/'blobs/sha256'/h[:2]/h
    assert hashlib.sha256(p.read_bytes()).hexdigest()==h
    return p
root=ET.parse(source(xml_hash)).getroot()
assert root is not None
paths={}
parents={}
def visit(node,path):
    paths[node]=path
    counts=Counter()
    for child in node:
        counts[child.tag]+=1
        component=f"{child.tag}[@id='{child.attrib['id']}']" if 'id' in child.attrib else f'{child.tag}[{counts[child.tag]}]'
        parents[child]=node
        visit(child,path+'/'+component)
visit(root,'/article')
selectors={
'surgery_and_sham':'All surgical experiments were performed',
'pool_anatomy_selection_recovery':'10–20 sciatic nerves were used',
'culture_validation_not_rnaseq':'Cultured cells were fixed',
'acutely_extracted_rna':'RNA from purified Schwann cells was isolated',
'naive_purity':'To assess the purity of our O4-immunopanned Schwann cells',
'all_timepoint_contamination_checks':'Examination of FPKM values for known cell type-specific genes',
'author_discussion_recovery_age_handling':'We used published immunopanning methods',
'dual_processing_fpkm':'FASTQ files were first groomed',
'dual_processing_counts':'To assess the functional difference of genes post-nerve crush',
'dissociation_control_caption':'Additional file 4. All FPKM data for uncrushed',
}
excerpts=[]
for key,start in selectors.items():
    found=[]
    for node in root.iter('p'):
        text=' '.join(''.join(node.itertext()).split())
        if text.startswith(start):
            found.append((node,text))
    assert len(found)==1,(key,len(found))
    node,text=found[0]
    headings=[]
    cursor=node
    while cursor in parents:
        cursor=parents[cursor]
        title=cursor.find('title')
        if title is not None:
            headings.append(''.join(title.itertext()))
    excerpts.append({'key':key,'source':'PMC9063194','source_sha256':xml_hash,'xpath':paths[node],'section_hierarchy':headings[::-1],'text_verbatim_whitespace_normalized':text})
obj=json.loads(source(audit_hash).read_text())
rows=[]
for r in obj['sample_annotations']:
    if r['dataset']=='GSE177037' and r['compartment']=='O4-immunopanned Schwann cells':
        day=r['injury_day']
        rows.append({k:r[k] for k in ['gsm','source_title','source_characteristics','age_or_stage_source','injury_day','library_column','biological_unit','individual_donor_ids','pairing','metadata_export_sha256']})
        rows[-1]['postinjury_harvest_age_derived_from_P18_surgery']=18+day if day else None
        rows[-1]['naive_age_caveat']='GEO labels P18; no separate harvest-age-matched naive arm verified' if day==0 else 'GEO constant P18 label conflicts with elapsed post-surgery days; derived age not donor metadata'
rows.sort(key=lambda r:r['gsm'])
counts=Counter(r['injury_day'] for r in rows)
assert len(rows)==8 and counts=={0:2,3:2,5:2,7:2}
assert all(r['individual_donor_ids'] is None for r in rows)
result={'question':q.name,'responding_to':'post_5038564d23c34f33bab9ab0aaf0fe46c','status':'source extraction and audit reuse; not new biological replication','sources':[xml_hash,audit_hash],'excerpts':excerpts,'purified_libraries':rows,'validated':{'xml_and_audit_hashes':True,'selected_excerpts':len(excerpts),'purified_library_rows':len(rows),'library_counts_by_injury_day':dict(counts)},'interpretation_limits':['O4 recognition and purity do not establish equal subtype recovery','the naive-yield wording is retained exactly; no normalization of its ambiguous range','within-purified contrasts remain descriptive; age/surgery/selection not experimentally separated','same naive libraries serve multiple timepoints; timepoints are not independent replications','no Supplement4 target values acquired or inspected in this follow-up']}
output=q/'outputs/repair-eligibility-source-locators.json'
output.write_text(json.dumps(result,indent=2,allow_nan=False))
print(json.dumps({'validated':result['validated'],'locators':[{k:x[k] for k in ['key','xpath','section_hierarchy']} for x in excerpts],'samples':[{k:r[k] for k in ['gsm','source_title','library_column','postinjury_harvest_age_derived_from_P18_surgery']} for r in rows]},indent=2))
