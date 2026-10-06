"""Execute upstream RNA/program contrasts from immutable native measurements.
No downloaded code; no count rounding; no cross-study pooling or paired inference.
"""
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
from scipy import stats

Q = Path(__file__).resolve().parents[1]
WS = Q.parents[1]
PLAN = json.loads((Q / 'inputs/analysis-plan.r001.json').read_text())
PANEL = PLAN['primary_program']['genes']
TARGETS = PLAN['targets']
CONTROLS = PLAN['controls']
GENES = list(dict.fromkeys(TARGETS + PANEL + sum(CONTROLS.values(), [])))
INPUTS = {}


def blob(h):
    p = WS / 'blobs/sha256' / h[:2] / h
    assert hashlib.sha256(p.read_bytes()).hexdigest() == h
    INPUTS[h] = str(p)
    return p


def norm(x):
    pos = (x > 0).all(axis=1)
    assert pos.sum() > 1000
    g = np.exp(np.log(x.loc[pos]).mean(axis=1))
    factors = x.loc[pos].div(g, axis=0).median(axis=0)
    return x.div(factors, axis=1), factors, int(pos.sum())


def effect(y, c, t):
    a, b = y.loc[c].to_numpy(dtype=float), y.loc[t].to_numpy(dtype=float)
    delta = float(b.mean() - a.mean())
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    se = float(np.sqrt(va + vb))
    df = float((va + vb)**2 / (va**2/(len(a)-1) + vb**2/(len(b)-1))) if se else None
    half = float(stats.t.ppf(.975, df) * se) if se else 0.0
    half_family = float(stats.t.ppf(1-.05/(2*15), df)*se) if se else 0.0
    ci = [delta-half, delta+half]
    loo = []
    for group, other, sign in [(a,b,1),(b,a,-1)]:
        for k in range(len(group)):
            loo.append(float(sign*(other.mean()-np.delete(group,k).mean())))
    return {'effect':delta, 'se':se, 'df':df, 'ci95':ci,
            'family15_ci95':[delta-half_family,delta+half_family],
            'loo_sample_effect_range':[min(loo),max(loo)],
            'preserved_0.25':bool(ci[0]>=-.25 and ci[1]<=.25),
            'preserved_0.5':bool(ci[0]>=-.5 and ci[1]<=.5),
            'nondepleted_0.5':bool(ci[0]>-.5),
            'minimum_symmetric_bound':max(abs(v) for v in ci),
            'max_compatible_log2_decrease':max(0.0,-ci[0])}


# NAE1: independently rebuild every source row; validate earlier preparation.
receipts = json.loads(blob('5d4a8d97cecd2eebec81a71a0d3df46913cd3350776604f4d83b3ee7c15a6f3b').read_text())
count_cols, tpm_cols = {}, {}
for r in receipts:
    name = r['name'].split('_',1)[1].removesuffix('.genes.results.gz')
    p = blob(r['receipt']['blob'])
    with gzip.open(p, 'rt') as f:
        d = pd.read_csv(f,sep='\t',index_col='gene_id')
    assert d.index.is_unique
    count_cols[name] = d['expected_count']
    tpm_cols[name] = d['TPM']
counts = pd.DataFrame(count_cols).sort_index(axis=1)
assert not counts.isna().any().any()
prior = pd.read_csv(blob('2d6f0b558d32cd63d89f9799882ed9cb084400aca6cd3b000b5cfdd2cf91673a'),sep='\t',index_col='gene_id')
assert np.array_equal(counts.to_numpy(),prior.loc[counts.index,counts.columns].to_numpy())
symbols = pd.Series([s.rsplit('_',1)[1] for s in counts.index],index=counts.index)
normalized,sf,npos = norm(counts)
sets = [{'id':'Nae1_cKO_P7','study':'GSE241269','units':'RSEM fractional expected counts; native TPM sensitivity',
         'counts':counts,'symbols':symbols,'control':[c for c in counts if c.startswith('WT')],
         'treatment':[c for c in counts if c.startswith('KO')],
         'variants':{'median_ratio':(normalized,.5),'CPM':(counts.div(counts.sum(),axis=1)*1e6,.1),'TPM':(pd.DataFrame(tpm_cols)[counts.columns],.1)},
         'primary':'median_ratio','coverage_floor':'all_control_count_ge10','factors':sf.to_dict(),
         'positive_features':npos,'native_rows':len(counts),'source_matches_prior_all_rows':True,
         'unit_limit':'4 labeled nerve libraries per arm; litter dependence not resolved; no donor pairing assumed'}]

# Figlia: preserved native normalized-count sheets and exact source fold direction.
fp = blob('3c1be01fc49ea6b7eb7b527352c032e8e9987e4db78ed2a0bcc79b53b902b5b6')
map_df = pd.read_csv(blob('db9cc3ad3df363e4a84f6841ac3c388c754328e85e7c9082dd49d88f09ff4b2c'),sep='\t')
assert map_df['sample_alias'].is_unique
mapping = dict(zip(map_df['sample_alias'],map_df['sample_title'],strict=True))
with fp.open('rb') as f:
    wb = openpyxl.load_workbook(f,read_only=True,data_only=False)
    for target in ['TSC1KO','PTENKO','RaptorKO']:
        sheet = wb['Control vs '+target]
        rows = sheet.iter_rows(values_only=True)
        header = next(rows)
        d = pd.DataFrame(rows,columns=header).set_index('gene_id')
        assert d.index.is_unique
        c = [f'Dev{i}' for i in sorted(mapping) if mapping[i]=='Control']
        t = [f'Dev{i}' for i in sorted(mapping) if mapping[i]==target]
        x = d[[s+' [normalized count]' for s in c+t]].astype(float)
        x.columns = c+t
        fpkm = d[[s+' [FPKM]' for s in c+t]].astype(float)
        fpkm.columns = c+t
        assert not x.isna().any().any() and (x>=0).all().all()
        # Validate mapping on other genes; never select map to optimize target result.
        other = ~d['gene_name'].isin(GENES)
        ratio = np.log2((x[t].mean(axis=1)+.5)/(x[c].mean(axis=1)+.5))
        use = other & (x.min(axis=1)>=10) & d['log2 Ratio'].notna()
        corr = float(np.corrcoef(ratio.loc[use],d.loc[use,'log2 Ratio'].astype(float))[0,1])
        assert corr > .99
        sets.append({'id':target+'_P5','study':'PRJEB20661','units':'source normalized counts; FPKM sensitivity',
                     'counts':x,'symbols':d['gene_name'],'control':c,'treatment':t,
                     'variants':{'native_normalized':(x,.5),'FPKM':(fpkm,.1)},'primary':'native_normalized',
                     'flags':d['isPresent'],'source_effects':d['log2 Ratio'],
                     'coverage_floor':'all_control_count_ge10','native_rows':len(x),
                     'mapping_check':{'nonpanel_genes':int(use.sum()),'effect_correlation':corr},
                     'unit_limit':'3 labeled libraries per arm; shared Dev1-3 controls; ENA numeric aliases map to Dev labels, prefix not independently explicit; intervals conditional on this map and independence'})

# NRG1: exact receipt identity, deposited counts, no filename-inferred pairing.
inputs = json.loads((Q/'outputs/selectivity-manifest.json').read_text())['manifest']['derivation']['inputs']
meta = json.loads(blob('2aa166f06f67fb37c49b65f5b659bd9213d8dc290984183f7cd0d074bff34813').read_text())
assets = json.loads(blob('3ce4458f0aee44b54666e89f5c86e8bdeaf611289078d3009cabac36d2215637').read_text())['items']
asset_names = {a['asset_revision']:a['name'] for a in assets}
cols, nrg_maps = {}, []
for inp in inputs:
    data = blob(inp['blob']).read_bytes()
    if not data.startswith(b'{'):
        continue
    r = json.loads(data)
    if r.get('previous_revision') not in asset_names:
        continue
    file_name = asset_names[r['previous_revision']]
    gsm = file_name.split('_')[0]
    with gzip.open(blob(r['blob']),'rt') as f:
        d = pd.read_csv(f,sep='\t',header=None,names=['symbol','count'],index_col='symbol')
    assert d.index.is_unique
    cols[gsm] = d['count']
    nrg_maps.append({'sample':gsm,'title':meta[gsm]['Sample_title'][0],'native_file':file_name,'blob':r['blob']})
x = pd.DataFrame(cols).sort_index(axis=1)
assert x.shape[1] == 6 and not x.isna().any().any() and (x>=0).all().all()
nonfeatures = [i for i in x.index if i.startswith('__')]
x = x.drop(nonfeatures)
assert np.equal(x,np.floor(x)).all().all()
c = [s for s in x if meta[s]['Sample_title'][0].startswith('mock')]
t = [s for s in x if meta[s]['Sample_title'][0].startswith('treated')]
normalized,sf,npos = norm(x)
sets.append({'id':'NRG1_6h','study':'GSE104324','units':'deposited HTSeq gene counts',
             'counts':x,'symbols':pd.Series(x.index,index=x.index),'control':c,'treatment':t,
             'variants':{'median_ratio':(normalized,.5),'CPM':(x.div(x.sum(),axis=1)*1e6,.1)},
             'primary':'median_ratio','coverage_floor':'control_mean_CPM_ge1',
             'factors':sf.to_dict(),'positive_features':npos,'native_rows':len(x),
             'removed_nonmeasurement_counters':nonfeatures,'sample_map':nrg_maps,
             'unit_limit':'source states three independent experiments per condition, explicit donor pairing not established; unpaired library intervals'} )

summary, sample_rows, gene_effects, outputs = [], [], [], []
for ds in sets:
    x, symbols, c, t = ds['counts'],ds['symbols'],ds['control'],ds['treatment']
    coverage = {}
    ids = {}
    for g in GENES:
        hits = symbols.index[symbols==g].tolist()
        row = {'native_matches':len(hits),'feature_ids':hits}
        if len(hits)==1:
            i = hits[0]
            ids[g] = i
            vals = x.loc[i,c+t]
            flags = str(ds['flags'].loc[i]) if 'flags' in ds else 'not_exported'
            floor = bool(x.loc[i,c].min()>=10)
            if ds['coverage_floor']=='control_mean_CPM_ge1':
                floor = bool((x.loc[i,c]/x[c].sum()*1e6).mean()>=1)
            row.update({'control_min_native':float(x.loc[i,c].min()),'control_mean_native':float(x.loc[i,c].mean()),
                        'native_flag':flags,'finite_nonnegative':bool(np.isfinite(vals).all() and (vals>=0).all()),
                        'baseline_pass':floor,'flags_pass':flags.lower() in ['true','not_exported']})
            row['eligible'] = row['finite_nonnegative'] and floor and row['flags_pass']
        else:
            row['eligible']=False
        coverage[g]=row
    primary_eligible = all(coverage[g]['eligible'] for g in PANEL+TARGETS)
    result = {k:v for k,v in ds.items() if k not in ['counts','symbols','variants','flags','source_effects']}
    result.update({'coverage':coverage,'primary_eligible':primary_eligible,'variants':{}})
    for variant,(m,pc) in ds['variants'].items():
        logs = np.log2(m+pc)
        # Complete source effects, not significant-gene selection.
        if variant==ds['primary']:
            changes=logs[t].mean(axis=1)-logs[c].mean(axis=1)
            for i,v in changes.items():
                gene_effects.append({'contrast':ds['id'],'feature':i,'symbol':symbols.loc[i],'log2_change':v})
        observed = pd.DataFrame({g:logs.loc[i,c+t] for g,i in ids.items()})
        for s in c+t:
            for g,i in ids.items():
                sample_rows.append({'contrast':ds['id'],'variant':variant,'sample':s,'group':'control' if s in c else 'perturbed','gene':g,'feature':i,'expression':float(m.loc[i,s]),'log2_expression':float(logs.loc[i,s]),'pseudocount':pc})
        measures = {g:observed[g] for g in TARGETS if g in observed}
        if set(PANEL)<=set(observed):
            measures['myelin7']=observed[PANEL].mean(axis=1)
            for regulator in ['Egr2','Sox10']:
                if regulator in observed:
                    measures['myelin7-minus-'+regulator]=measures['myelin7']-observed[regulator]
                    measures['Pmp22-minus-'+regulator]=observed['Pmp22']-observed[regulator]
        for name,genes in CONTROLS.items():
            if set(genes)<=set(observed):
                measures[name]=observed[genes].mean(axis=1)
        results = {name:effect(y,c,t) for name,y in measures.items()}
        if 'myelin7' in results:
            omit = [float(effect(observed[[g for g in PANEL if g!=omit]].mean(axis=1),c,t)['effect']) for omit in PANEL]
            results['myelin7']['loo_gene_effect_range']=[min(omit),max(omit)]
            for regulator in ['Egr2','Sox10']:
                omit = [float(effect(observed[[g for g in PANEL if g!=omit]].mean(axis=1)-observed[regulator],c,t)['effect']) for omit in PANEL]
                results['myelin7-minus-'+regulator]['loo_gene_effect_range']=[min(omit),max(omit)]
        result['variants'][variant]=results
        for name,r in results.items():
            summary.append({'contrast':ds['id'],'variant':variant,'primary_variant':variant==ds['primary'],'primary_eligible':primary_eligible,'metric':name,**{k:v for k,v in r.items() if not isinstance(v,list)},'ci_low':r['ci95'][0],'ci_high':r['ci95'][1]})
    outputs.append(result)
    selected = result['variants'][ds['primary']]
    print(ds['id'],'eligible',primary_eligible)
    for metric in ['Egr2','Sox10','Pmp22','myelin7','myelin7-minus-Egr2','myelin7-minus-Sox10']:
        print(metric,selected.get(metric))

out = Q/'outputs'
pd.DataFrame(summary).to_csv(out/'contrast-summary.tsv',sep='\t',index=False)
pd.DataFrame(sample_rows).to_csv(out/'sample-expression.tsv',sep='\t',index=False)
pd.DataFrame(gene_effects).to_csv(out/'all-gene-effects.tsv',sep='\t',index=False)
(out/'executed-contrasts.json').write_text(json.dumps({'plan_sha256':hashlib.sha256((Q/'inputs/analysis-plan.r001.json').read_bytes()).hexdigest(),'input_blobs':INPUTS,'contrasts':outputs},indent=2,allow_nan=False)+'\n')
