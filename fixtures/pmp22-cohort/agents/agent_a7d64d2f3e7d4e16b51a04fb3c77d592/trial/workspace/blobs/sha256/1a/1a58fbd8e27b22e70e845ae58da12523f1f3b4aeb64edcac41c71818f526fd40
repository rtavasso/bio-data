"""Report full-background RNA results and sensitivity ranges; no reranking filtering."""
import json
from pathlib import Path
import pandas as pd

Q = Path(__file__).resolve().parents[1]
plan = json.loads((Q / 'inputs/analysis-plan.json').read_text())
g = pd.read_csv(Q / 'outputs/rna-all-gene-contrasts.tsv.gz', sep='\t')
s = pd.read_csv(Q / 'outputs/rna-sensitivities.tsv', sep='\t')
chosen = g[g.symbol.isin(plan['gene_endpoints'])]
chosen.to_csv(Q / 'outputs/rna-named-gene-contrasts.tsv', sep='\t', index=False, na_rep='NA')
print(chosen[['contrast','symbol','delta_log2','ci95_low','ci95_high']].to_string(index=False))
for name in ['sterol_synthesis_minus_myelin7','efflux_export_minus_sterol_synthesis','Pmp22_minus_myelin7']:
    print(name)
    print(s[s.endpoint == name].groupby(['contrast']).delta_log2.agg(['min','max']).to_string())
    print(s[(s.endpoint == name) & (s.variant == 'CPM_plus_0.01')].to_string(index=False))
# The author's table defines AK as KO and AW as WT; check exact raw columns against full input.
a = json.loads((Q / 'outputs/Acly-deg-acquired.json').read_text())
deg = pd.read_csv(a['path'], sep='\t', compression='gzip')
raw = pd.read_csv(json.loads((Q / 'outputs/Acly-acquired.json').read_text())['path'], compression='gzip').set_index('gene_id')
assert deg.gene_id.is_unique
common = deg.set_index('gene_id')
for sample in ['AK1','AK2','AK3','AW1','AW2']:
    assert (common[sample+'_count'] == raw.loc[common.index, sample]).all()
assert ((common[['AK1','AK2','AK3']].mean(axis=1)-common.Aclyko).abs() < .000001).all()
assert ((common[['AW1','AW2']].mean(axis=1)-common.Aclywt).abs() < .000001).all()
result = {'native_DE_rows': len(deg), 'matched_raw_columns': True, 'AK_group': 'Aclyko', 'AW_group': 'Aclywt',
          'label_mapping_evidence': 'native DE mean columns agree with AK/AW group means and raw count columns agree with complete CSV',
          'note': 'Individual GSM ordinal mapping is not needed; native group membership is directly checked.'}
(Q / 'outputs/Acly-group-mapping-validation.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
print(deg[deg.gene_name.isin(['Pmp22','Abca1','Abcg1','Apoe','Hmgcr','Egr2','Fasn'])][['gene_name','log2FoldChange','padj']].to_string(index=False))
