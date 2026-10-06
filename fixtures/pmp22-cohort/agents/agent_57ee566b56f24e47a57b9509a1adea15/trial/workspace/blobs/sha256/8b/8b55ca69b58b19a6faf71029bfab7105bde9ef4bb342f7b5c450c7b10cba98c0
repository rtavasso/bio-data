"""Test the presealed transporter split on independently collected NRG1 libraries."""
import hashlib
from itertools import combinations
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs'
BLOBS = Q.parents[1] / 'blobs/sha256'
LOCK = Q / 'outputs/predictions/abca1-abcg1-state-transfer-r001.json'
assert hashlib.sha256(LOCK.read_bytes()).hexdigest() == 'a48d7a06535a11421c508d8f6c84f2a3b3af315e03a3eacd561dc1bf88e98d9a'


def blob(h):
    p = BLOBS / h[:2] / h
    assert hashlib.sha256(p.read_bytes()).hexdigest() == h
    return p


def estimate(v, mask):
    a, b = v[mask], v[~mask]
    d = float(a.mean()-b.mean())
    va, vb = a.var(ddof=1)/len(a), b.var(ddof=1)/len(b)
    se = np.sqrt(va+vb)
    df = (va+vb)**2/(va**2/(len(a)-1)+vb**2/(len(b)-1))
    margin = float(stats.t.ppf(.975, df)*se)
    perms = []
    for ix in combinations(range(len(v)), len(a)):
        m = np.zeros(len(v), dtype=bool)
        m[list(ix)] = True
        perms.append(float(v[m].mean()-v[~m].mean()))
    return {'delta_log2': d, 'ci95_low': d-margin, 'ci95_high': d+margin,
            'permutation_p': sum(abs(p) >= abs(d)-1e-12 for p in perms)/len(perms),
            'permutation_assignments': len(perms)}


inventory = json.loads((OUT / 'peer-input-inventory.json').read_text())
manifest = json.loads(blob('3ce4458f0aee44b54666e89f5c86e8bdeaf611289078d3009cabac36d2215637').read_text())
source_meta = json.loads(blob('2aa166f06f67fb37c49b65f5b659bd9213d8dc290984183f7cd0d074bff34813').read_text())
asset_names = {x['asset_revision']: x['name'] for x in manifest['items']}
matrices, sample_map = [], []
for entry in inventory:
    if entry['bytes'] != 287:
        continue
    receipt = json.loads(blob(entry['blob']).read_text())
    name = asset_names[receipt['previous_revision']]
    sample = name.split('_',1)[0]
    fields = source_meta[sample]
    title = fields['Sample_title'][0]
    assert 'Vehicle' in title or 'b10nM' in title
    treated = 'b10nM' in title
    frame = pd.read_csv(blob(receipt['blob']), sep='\t', compression='gzip', header=None, names=['gene',sample], index_col=0)
    assert frame.index.is_unique
    matrices.append(frame)
    sample_map.append({'sample': sample, 'source_file': name, 'source_blob': receipt['blob'], 'title': title,
                       'treatment': treated, 'unit': 'source-labelled independent experiment; donor/split unresolved'})
counts = pd.concat(matrices, axis=1)
assert len(sample_map) == 6 and counts.notna().all().all()
treat = np.array([x['treatment'] for x in sample_map])
assert treat.sum() == 3
counts.to_csv(OUT / 'validation-native-counts.tsv.gz', sep='\t', compression='gzip')
arr = counts.to_numpy(dtype=float)
assert np.isfinite(arr).all() and (arr>=0).all()
feature = ~counts.index.astype(str).str.startswith('__')
positive = (arr>0).all(axis=1) & feature
geometric = np.exp(np.log(arr[positive]).mean(axis=1))
factors = np.median(arr[positive]/geometric[:,None], axis=0)
norm = arr/factors
logs = np.log2(norm+.5)
keygenes = ['Abca1','Abcg1','Apoe','Pmp22']
rows, outcomes, eligible = [], {}, True
for gene in keygenes:
    if gene not in counts.index:
        eligible = False
        outcomes[gene] = {'status': 'missing'}
        continue
    i = counts.index.get_loc(gene)
    baseline = float(norm[i,~treat].mean())
    if gene in ['Abca1','Abcg1'] and baseline<10:
        eligible = False
    outcomes[gene] = {'control_mean_normalized': baseline, **estimate(logs[i], treat)}
    for j, s in enumerate(sample_map):
        rows.append({**s, 'gene': gene, 'raw_count': arr[i,j], 'normalized_count': norm[i,j], 'value_log2': logs[i,j]})
assert set(['Abca1','Abcg1']).issubset(counts.index)
ia, ig = counts.index.get_loc('Abca1'), counts.index.get_loc('Abcg1')
ratio = logs[ia]-logs[ig]
result = estimate(ratio, treat)
cpm = arr/arr.sum(axis=0)*1e6
cpmlog = np.log2(cpm+.01)
sensitivity = estimate(cpmlog[ia]-cpmlog[ig], treat)
point_pass = result['delta_log2']>=.5 and outcomes['Abca1']['delta_log2']>0 and outcomes['Abcg1']['delta_log2']<0
status = 'untestable' if not eligible else 'point_pass' if point_pass else 'failed_prediction'
validation = {'candidate_id': 'abca1-abcg1-state-transfer', 'prediction_sha256': hashlib.sha256(LOCK.read_bytes()).hexdigest(),
              'source': 'GSE104324', 'result_status': status, 'eligible': eligible, 'primary_logratio': result,
              'CPM_sensitivity': sensitivity, 'genes': outcomes, 'samples': sample_map,
              'full_native_feature_rows': len(counts), 'normalization_gene_rows': int(positive.sum()),
              'interpretation_limit': 'Independent contextual perturbation test; not disease replication, lipid flux, or promoter output. Donor pairing remains unknown.'}
pd.DataFrame(rows).to_csv(OUT / 'validation-per-sample.tsv', sep='\t', index=False)
pd.DataFrame(sample_map).to_csv(OUT / 'validation-sample-map.tsv', sep='\t', index=False)
(OUT / 'validation-transfer.json').write_text(json.dumps(validation, indent=2, allow_nan=False))
# New post-discovery ratio calculation on already-exposed discovery samples, no new hypothesis credit.
samples = pd.read_csv(OUT / 'rna-per-sample.tsv', sep='\t')
discovery = []
for context, frame in samples.groupby('contrast'):
    w = frame[frame.endpoint.isin(['gene:Abca1','gene:Abcg1'])].pivot(index='sample', columns='endpoint', values='value_log2')
    v = (w['gene:Abca1']-w['gene:Abcg1']).to_numpy()
    groups = frame[['sample','group']].drop_duplicates().set_index('sample').loc[w.index,'group']
    m = (groups == 'perturbed').to_numpy()
    discovery.append({'contrast': context, 'endpoint': 'Abca1_minus_Abcg1', 'stage': 'post-discovery exploration', **estimate(v,m)})
pd.DataFrame(discovery).to_csv(OUT / 'discovery-transporter-split.tsv', sep='\t', index=False)
print(json.dumps(validation, indent=2))
print(pd.DataFrame(discovery).to_string(index=False))
