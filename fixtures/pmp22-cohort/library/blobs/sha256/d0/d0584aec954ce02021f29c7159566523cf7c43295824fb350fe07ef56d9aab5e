"""Execute frozen independent injury prediction and prespecified exploratory Raptor contrasts.
Stable gene IDs only: current annotation coordinates are never transferred to source GRCm38.
"""
import csv,gzip,hashlib,itertools,json,os
from pathlib import Path
import numpy as np
from scipy.stats import t
Q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1';WS=Q.parents[1];O=Q/'outputs'
spec=json.loads((Q/'inputs/panel-spec.json').read_text());selection=json.loads((Q/'inputs/validation-selection.json').read_text());panels=spec['panels']
receipt=json.loads((O/'fetch-GSE108231.json').read_text());assert receipt['outcome']=='available_full';h=receipt['blob'];p=WS/'blobs/sha256'/h[:2]/h
assert hashlib.sha256(p.read_bytes()).hexdigest()==h
with gzip.open(p,'rt') as f:
    rd=csv.reader(f,delimiter='\t');header=next(rd);rows=list(rd)
assert header[0]=='Feature ID';samples=header[1:];ids=[r[0] for r in rows];counts=np.asarray([[float(v) for v in r[1:]] for r in rows]);assert len(ids)==len(set(ids))
assert counts.shape==(len(ids),13) and (counts>=0).all() and np.isfinite(counts).all()
fields=json.loads((O/'fields-GSE108231.json').read_text());metadata={}
for acc,d in fields.items():
    if not acc.startswith('GSM'):continue
    title=d['Sample_title'][0]
    col=title[:-len('_contralateral')]+'_ctrlat' if title.endswith('_contralateral') else title
    assert col in samples and col not in metadata
    metadata[col]={'accession':acc,'source_title':title,'native_column':col,'characteristics':d['Sample_characteristics_ch1'],'source_relations':d['Sample_relation'],'mouse_pair_label':title.split('_')[0]}
assert set(samples)==set(metadata)
a=[f'Control{i}_ctrlat' for i in [1,2,3]];b=[f'Control{i}_crush' for i in [1,2,3]]
assert [metadata[s]['accession'] for s in a]==selection['control_samples'] and [metadata[s]['accession'] for s in b]==selection['injured_samples']
mapping={};annotation_receipts={};unmapped={}
for gene in list(dict.fromkeys(['Pmp22',*sum(panels.values(),[])])):
    path=Q/f'inputs/public/ensembl-mouse-{gene}.json';r=json.loads(path.with_name(path.name+'.receipt.json').read_text());assert r['status']==200 and hashlib.sha256(path.read_bytes()).hexdigest()==r['sha256']
    g=json.loads(path.read_text());assert g['display_name']==gene and g['species']=='mus_musculus' and g['object_type']=='Gene'
    annotation_receipts[gene]={'sha256':r['sha256'],'stable_id':g['id'],'lookup_assembly':g['assembly_name'],'usage':'stable-ID label only; source matrix GRCm38 coordinates not altered'}
    if g['id'] in ids:mapping[gene]=ids.index(g['id'])
    else:unmapped[gene]=g['id']
lib=counts.sum(axis=0);cpm=counts/lib*1e6;positive=(counts>0).all(axis=1);geo=np.exp(np.log(counts[positive]).mean(axis=1));sf=np.median(counts[positive]/geo[:,None],axis=0);mr=(counts/sf)/np.median(lib/sf)*1e6
z=np.log2(cpm+.1)
def one_sample(d):
    d=np.asarray(d);m=float(d.mean());se=float(d.std(ddof=1)/np.sqrt(len(d)));w=float(t.ppf(.975,len(d)-1)*se)
    signs=np.array(list(itertools.product([-1,1],repeat=len(d))));null=np.abs((signs*d).mean(axis=1));p=float((null>=abs(m)-1e-12).mean())
    return {'effect':m,'ci_low':m-w,'ci_high':m+w,'df':len(d)-1,'paired_unit_effects':d.tolist(),'exact_signflip_p':p}
def welch(a,b):
    a=np.asarray(a);b=np.asarray(b);m=float(b.mean()-a.mean());va=a.var(ddof=1)/len(a);vb=b.var(ddof=1)/len(b);s=float(np.sqrt(va+vb));df=float((va+vb)**2/(va*va/(len(a)-1)+vb*vb/(len(b)-1))) if s else None
    w=float(t.ppf(.975,df)*s) if s else 0
    return {'effect':m,'ci_low':m-w,'ci_high':m+w,'df':df}
contrasts=[('control_injury_d5',a,b,True,'frozen primary independent bulk-context transfer'),('raptorKO_injury_d5',[f'KO{i}_ctrlat' for i in [1,2,3]],[f'KO{i}_crush' for i in [1,2,3]],True,'exploratory; KO4 has no injured partner'),('raptorKO_vs_control_injured',b,[f'KO{i}_crush' for i in [1,2,3]],False,'exploratory genotype contrast'),('raptorKO_vs_control_contralateral',a,[f'KO{i}_ctrlat' for i in [1,2,3,4]],False,'exploratory genotype contrast')]
results=[];gene_rows=[];sample_rows=[];sens=[]
for name,control,treated,paired,role in contrasts:
    ia=[samples.index(s) for s in control];ib=[samples.index(s) for s in treated]
    base={g:float(cpm[j,ia].mean()) for g,j in mapping.items()};missing=[g for g in ['Pmp22',*panels['myelin7']] if g not in mapping];floor=[g for g in ['Pmp22',*panels['myelin7']] if g in base and base[g]<1]
    r={'dataset':'GSE108231','contrast':name,'role':role,'control':control,'treated':treated,'paired':paired,'n_control':len(ia),'n_treated':len(ib),'primary_eligible':not missing and not floor,'missing':missing,'baseline_floor_failures':floor,'control_mean_cpm':base}
    def estimate(v):return one_sample(v[ib]-v[ia]) if paired else welch(v[ia],v[ib])
    r['Pmp22']=estimate(z[mapping['Pmp22']])
    for panel,genes in panels.items():
        keep=[mapping[g] for g in genes if g in mapping]
        if keep:r[panel]=estimate(z[keep].mean(axis=0))|{'coverage':len(keep),'missing':[g for g in genes if g not in mapping]}
    if r['primary_eligible']:
        ii=[mapping[g] for g in panels['myelin7']];v=z[mapping['Pmp22']]-z[ii].mean(axis=0)
        r['primary_selectivity']=estimate(v);r['unpaired_sensitivity']=welch(v[ia],v[ib]);r['target_vs_each_myelin']={g:float((z[mapping['Pmp22']]-z[mapping[g]])[ib].mean()-(z[mapping['Pmp22']]-z[mapping[g]])[ia].mean()) for g in panels['myelin7']}
        for norm,mat in [('CPM',cpm),('median_ratio',mr)]:
            for pc in [0,.1,1]:
                vals=mat[[mapping['Pmp22'],*ii]][:,ia+ib]
                if pc==0 and (vals<=0).any():continue
                zz=np.log2(vals+pc);dd=zz[0]-zz[1:].mean(axis=0)
                sens.append({'contrast':name,'kind':'normalization_pseudocount','normalization':norm,'pseudocount':pc,'omitted':None,'effect':float(dd[len(ia):].mean()-dd[:len(ia)].mean())})
        for drop in panels['myelin7']:
            w=z[mapping['Pmp22']]-z[[mapping[g] for g in panels['myelin7'] if g!=drop]].mean(axis=0)
            sens.append({'contrast':name,'kind':'leave_one_marker','normalization':'CPM','pseudocount':.1,'omitted':drop,'effect':float(w[ib].mean()-w[ia].mean())})
        if paired:
            d=v[ib]-v[ia]
            for i in range(len(d)):sens.append({'contrast':name,'kind':'leave_one_mouse_pair','normalization':'CPM','pseudocount':.1,'omitted':metadata[control[i]]['mouse_pair_label'],'effect':float(np.delete(d,i).mean())})
        else:
            for omit in ia+ib:
                aa=[i for i in ia if i!=omit];bb=[i for i in ib if i!=omit]
                sens.append({'contrast':name,'kind':'leave_one_mouse','normalization':'CPM','pseudocount':.1,'omitted':samples[omit],'effect':float(v[bb].mean()-v[aa].mean())})
    else:r['primary_selectivity']=None
    for g,j in mapping.items():
        e=estimate(z[j]);gene_rows.append({'contrast':name,'gene':g,'stable_id':ids[j],'control_mean_cpm':base[g],'treated_mean_cpm':float(cpm[j,ib].mean()),'effect':e['effect'],'ci_low':e['ci_low'],'ci_high':e['ci_high']})
    results.append(r)
# Difference of within-mouse injury effects between genotypes, excludes unmatched KO4.
ii=[mapping[g] for g in panels['myelin7']];v=z[mapping['Pmp22']]-z[ii].mean(axis=0)
ca=np.array([samples.index(f'Control{i}_ctrlat') for i in [1,2,3]]);cb=np.array([samples.index(f'Control{i}_crush') for i in [1,2,3]]);ka=np.array([samples.index(f'KO{i}_ctrlat') for i in [1,2,3]]);kb=np.array([samples.index(f'KO{i}_crush') for i in [1,2,3]])
interaction={'contrast':'genotype_by_injury','unit':'difference of paired changes, 3 independent source-numbered mice/genotype; KO4 excluded','selectivity':welch(v[cb]-v[ca],v[kb]-v[ka]),'Pmp22':welch(z[mapping['Pmp22'],cb]-z[mapping['Pmp22'],ca],z[mapping['Pmp22'],kb]-z[mapping['Pmp22'],ka]),'myelin7':welch(z[ii][:,cb].mean(axis=0)-z[ii][:,ca].mean(axis=0),z[ii][:,kb].mean(axis=0)-z[ii][:,ka].mean(axis=0))}
for i,s in enumerate(samples):
    for g,j in mapping.items():sample_rows.append({'sample':s,'accession':metadata[s]['accession'],'mouse_pair_label':metadata[s]['mouse_pair_label'],'gene':g,'stable_id':ids[j],'native_count':float(counts[j,i]),'cpm':float(cpm[j,i]),'log2cpm_plus01':float(z[j,i])})
primary=results[0];eff=primary['primary_selectivity'];decision='untestable' if eff is None else ('magnitude_pass' if eff['effect']<=-.5 else ('direction_contradiction' if eff['effect']>=0 else 'magnitude_fail'))
summary={'dataset':'GSE108231','question':'q_6a3a0a07fa5d4da1','native_input':h,'features':len(ids),'samples':len(samples),'source_genome':'GRCm38','annotation':annotation_receipts,'unmapped_current_symbols':unmapped,'sample_metadata':metadata,'library_sums':dict(zip(samples,map(float,lib))),'median_ratio_positive_features':int(positive.sum()),'noninteger_count_values':int((counts!=np.floor(counts)).sum()),'panel_spec_sha256':hashlib.sha256((Q/'inputs/panel-spec.json').read_bytes()).hexdigest(),'frozen_prediction_sha256':hashlib.sha256((Q/'inputs/frozen-prediction.json').read_bytes()).hexdigest(),'selection_sha256':hashlib.sha256((Q/'inputs/validation-selection.json').read_bytes()).hexdigest(),'primary_decision':decision,'primary_direction_interval_supported':bool(eff and eff['ci_high']<0),'contrasts':results,'genotype_by_injury':interaction,'pairing_basis':'GEO numbered Control1-3/KO1-3 injured and contralateral titles; primary PMC5956991 unilateral injury/corresponding contralateral design and Fig6 n=3 mice; unpaired sensitivity retained. Not a direct tissue-composition-adjusted effect.'}
for filename,rr in [('validation-gene-effects.tsv',gene_rows),('validation-sample-values.tsv',sample_rows),('validation-sensitivities.tsv',sens)]:
    with (O/filename).open('w') as f:w=csv.DictWriter(f,fieldnames=list(rr[0]),delimiter='\t');w.writeheader();w.writerows(rr)
(O/'validation-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
print('PRIMARY_DECISION',decision,'direction_interval_supported',summary['primary_direction_interval_supported'],'features',len(ids),'unmapped',unmapped)
for r in results:print(r['contrast'],'Pmp22',r['Pmp22'],'myelin7',r['myelin7'],'relative',r['primary_selectivity'],'unpaired',r.get('unpaired_sensitivity'))
print('INTERACTION',interaction)
