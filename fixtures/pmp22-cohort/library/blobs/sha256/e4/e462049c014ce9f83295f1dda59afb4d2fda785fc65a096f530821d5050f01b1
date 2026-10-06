"""Prepare source-preserving reference and inherited matrices, with explicit selectors."""
from pathlib import Path
import hashlib
import json
import gzip
import re
import numpy as np
import pandas as pd
from xls_values import read_xls

Q=Path(__file__).resolve().parents[1]
W=Q.parents[1]
P=Q.parent/'q_277f20df4b6b47cc'
O=Q/'outputs'
D=O/'matrices'
D.mkdir(exist_ok=True)
inputs=[]
checks=[]

def blob(h,role):
    p=W/'blobs/sha256'/h[:2]/h
    assert hashlib.sha256(p.read_bytes()).hexdigest()==h
    inputs.append(dict(blob=h,role=role))
    return p

def dump(p,x):
    p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')

def emit(name,d):
    d.to_csv(D/(name+'.tsv.gz'),sep='\t',compression='gzip',index=True,na_rep='NA')

# Native XLS parsing preserves cell values and source row identity, no formulas.
r=json.loads((Q/'inputs/managed/elife-58591-supp1.xls.fetch.json').read_text())
x=read_xls(blob(r['blob'],'SNAT supplement1 native RPKM'))
references={}
for dataset,sheet in [('development','RPKM related to Figure 1'),('sorted','RPKM related to Figure 2')]:
    s=x[sheet]
    assert not s['formulas'] and not s['errors']
    d=pd.DataFrame(s['rows'][1:],columns=s['rows'][0])
    d['source_excel_row']=np.arange(2,len(d)+2)
    assert d.gene_id.is_unique
    dupe=d.gene_name.duplicated(False)|d.gene_name.isna()
    mapping=d[['gene_id','gene_name','source_excel_row']].copy()
    mapping['eligible_unique_symbol']=~dupe
    emit(dataset+'-feature-map',mapping)
    emit(dataset+'-native',d)
    values=d.loc[~dupe].set_index('gene_name').drop(columns=['gene_id','source_excel_row']).astype(float)
    assert np.isfinite(values.values).all() and (values.values>=0).all()
    emit(dataset+'-rpkm',values)
    references[dataset]=values
    checks.append(dict(dataset=dataset,source_rows=len(d),unique_rows=len(values),duplicate_or_missing_symbols=int(dupe.sum()),columns=list(values),formula_cells=len(s['formulas']),error_cells=len(s['errors'])))

# Rebuild Nae1 native source cells and audit the exact inherited prepared matrix.
rr=json.loads((P/'inputs/upstream/rna-fetch-receipts.json').read_text())
raw={}
tpm={}
for r in rr:
    h=r['receipt']['blob']
    s=r['name'].split('_',1)[1].split('.genes')[0]
    d=pd.read_csv(blob(h,'Nae1 native '+s),sep='\t',compression='gzip',index_col=0)
    assert d.index.is_unique and not any('status' in c.lower() for c in d)
    raw[s]=d.expected_count
    tpm[s]=d.TPM
c=pd.DataFrame(raw).sort_index(axis=1)
t=pd.DataFrame(tpm).reindex(c.index).reindex(columns=c.columns)
old=pd.read_csv(blob('2d6f0b558d32cd63d89f9799882ed9cb084400aca6cd3b000b5cfdd2cf91673a','inherited complete expected-count matrix'),sep='\t',index_col=0)
sy=old.pop('symbol')
assert np.allclose(c,old.reindex(index=c.index,columns=c.columns),rtol=0,atol=0)
positive=(c>0).all(axis=1)
sf=c.loc[positive].div(np.exp(np.log(c.loc[positive]).mean(axis=1)),axis=0).median()
n=c.div(sf)
y=np.log2(n+.5)
oldy=pd.read_csv(blob('6474b5abdfc1cddbc1c893b16115ec092382f9eb18555afc9bfe0245b1286525','inherited log2 normalized matrix'),sep='\t',index_col=0)
oldy.pop('symbol')
assert np.allclose(y,oldy.reindex(index=c.index,columns=c.columns),rtol=0,atol=1e-12)
sy=sy.reindex(c.index)
unique=~sy.duplicated(False)&sy.notna()
for name,m in [('counts',c),('log2',y),('tpm',t),('cpm',c.div(c.sum())*1e6)]:
    z=m.loc[unique].copy()
    z.index=sy[unique]
    z.index.name='gene'
    emit('nae1-'+name,z)
checks.append(dict(dataset='Nae1',source_rows=len(c),unique_rows=int(unique.sum()),source_cell_check='all eight expected-count columns exactly equal inherited matrix',normalized_check='all values agree within 1e-12',size_factors=sf.to_dict(),columns=list(c)))

# Figlia: keep native source status, normalized counts, FPKM and supplied contrast.
p=blob('3c1be01fc49ea6b7eb7b527352c032e8e9987e4db78ed2a0bcc79b53b902b5b6','Figlia2017 Figure3 native XLSX')
allcounts={}
allfpkm={}
effects={}
for group in ['TSC1KO','PTENKO','RaptorKO']:
    d=pd.read_excel(p,sheet_name='Control vs '+group,engine='openpyxl')
    assert d.Identifier.is_unique
    invalid=~d.gene_name.map(lambda x:isinstance(x,str))
    emit('figlia-'+group+'-nontext-symbols',d.loc[invalid])
    d=d.loc[~invalid].copy()
    d=d.loc[d.gene_name.notna()&~d.gene_name.duplicated(False)].set_index('gene_name')
    emit('figlia-'+group+'-native',d)
    present=d.isPresent.astype(str).str.upper().eq('TRUE')
    effects[group]=pd.to_numeric(d['log2 Ratio']).where(present)
    for col in d:
        if col.endswith(' [normalized count]'):
            sample=col.split(' ')[0]
            v=pd.to_numeric(d[col])
            if sample in allcounts:
                shared=v.index.intersection(allcounts[sample].index)
                assert np.allclose(v.loc[shared],allcounts[sample].loc[shared],rtol=1e-5,atol=.01), sample
            allcounts[sample]=v
        elif col.endswith(' [FPKM]'):
            allfpkm[col.split(' ')[0]]=pd.to_numeric(d[col])
    checks.append(dict(dataset='Figlia '+group,unique_rows=len(d),source_present_true=int(present.sum()),source_statuses=d.isPresent.astype(str).value_counts().to_dict()))
# Intersection across sheets avoids silently reconstructing missing values.
f=pd.DataFrame(allcounts).sort_index(axis=1).dropna()
fp=pd.DataFrame(allfpkm).reindex(index=f.index,columns=f.columns)
assert np.isfinite(f.values).all() and (f.values>=0).all()
emit('figlia-counts',f)
emit('figlia-log2',np.log2(f+.5))
emit('figlia-fpkm',fp)
emit('figlia-source-effects',pd.DataFrame(effects))

# Full inherited purified-cell/whole-nerve injury matrix, not just prior gene panel.
r=json.loads((P/'inputs/specific/fetch-discovery.json').read_text())
raw=pd.read_csv(blob(r['blob'],'GSE177037 full source count matrix'),compression='gzip',sep='\t',index_col=0)
parts=[s.split('_') for s in raw.index]
keep=np.array([len(s)==2 and s[0]==s[1] for s in parts])
z=raw.loc[keep].copy()
z.index=[s[0] for s,k in zip(parts,keep) if k]
assert z.index.is_unique
emit('repair-counts',z)
emit('repair-log2cpm',np.log2(z.div(raw.sum())*1e6+.5))
checks.append(dict(dataset='GSE177037',source_rows=len(raw),unique_rows=len(z),columns=list(z),unit='two pooled preparations per compartment/time, not individual nerves'))

# Metadata in human-readable complete sample records, not inferred donor matches.
meta=[]
for fn in ['GSE137868-gsm.soft','GSE137947-gsm.soft','GSE138577-family.soft']:
    p=Q/'inputs/public'/fn
    inputs.append(dict(blob=hashlib.sha256(p.read_bytes()).hexdigest(),role=fn))
    current={}
    for line in p.read_text().splitlines():
        if line.startswith('^SAMPLE'):
            if current:
                meta.append(current)
            current={'accession':line.split(' = ')[1], 'metadata_source':fn}
        elif current and line.startswith('!Sample_') and ' = ' in line:
            key,value=line.split(' = ',1)
            if any(t in key for t in ['title','characteristics','source_name','description','data_processing','supplementary_file']):
                current.setdefault(key,[]).append(value)
    if current:
        meta.append(current)
dump(O/'reference-sample-metadata.json',meta)
dump(O/'preparation-summary.json',dict(checks=checks,inputs=inputs,limits='Source values preserve relative units; missing/ambiguous genes excluded explicitly, never zero-filled. Fractions/states are not biological replicates.'))
print(json.dumps(checks,indent=2))
