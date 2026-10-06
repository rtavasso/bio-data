"""Harmonize verified PMP22 QTL summaries; no genotype inference or raw-data modeling."""
import csv
import gzip
import hashlib
import io
import json
import platform
from pathlib import Path
import re
import tarfile
from collections import Counter, defaultdict
import pyarrow
import pyarrow.compute as pc
import pyarrow.parquet as pq

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs/final-r002'
OUT.mkdir(exist_ok=False)
inputs = {}

def use(rel):
    p = Q / rel
    h = hashlib.sha256()
    with p.open('rb') as f:
        while b := f.read(2**22):
            h.update(b)
    inputs[rel] = {'path': rel, 'bytes': p.stat().st_size, 'sha256': h.hexdigest()}
    return p

def readj(rel):
    return json.loads(use(rel).read_text())

def save(name, obj):
    with (OUT / name).open('x') as f:
        json.dump(obj, f, indent=2, allow_nan=False)
        f.write('\n')

def table(name, rows):
    fields = sorted({k for r in rows for k in r})
    with (OUT / name).open('x', newline='') as f:
        w = csv.DictWriter(f, fields, delimiter='\t', lineterminator='\n')
        w.writeheader()
        for r in rows:
            w.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, (list, dict)) else v
                        for k, v in r.items()})

def ci(b, se):
    b, se = float(b), float(se)
    assert se > 0
    return b - 1.96 * se, b + 1.96 * se

def variant(v, gtex=False):
    pat = r'chr(\d+|X|Y)_(\d+)_([ACGT]+)_([ACGT]+)' + ('_b38' if gtex else '')
    m = re.fullmatch(pat, v)
    assert m, v
    ch, pos, ref, alt = m.groups()
    assert int(pos) > 0 and ref != alt
    return 'chr' + ch, int(pos), ref, alt

inspection = readj('outputs/inspection-v11.json')
receipt = readj('outputs/inspection-execution-r001.json')
assert receipt['exit_code'] == 0 and receipt['complete']
assert inputs['outputs/inspection-v11.json']['sha256'] == receipt['outputs'][0]['sha256']
indrec = readj('outputs/independent-execution-r002.json')
assert indrec['exit_code'] == 0 and indrec['complete']
indval = readj('outputs/independent-r002/extraction-validation.json')
for x in indrec['outputs']:
    rel = str(Path(x['path']).relative_to(Q))
    use(rel)
    assert inputs[rel]['sha256'] == x['sha256']

# Direct counts of source covariate matrices and gene-specific splice groups.
cov = {}
for assay in ['eqtl', 'sqtl']:
    p = use(f'inputs/public/v11-{assay}-covariates.tar')
    with tarfile.open(p, 'r:') as t:
        for m in t:
            if not m.isfile():
                continue
            rows = t.extractfile(m).read().decode().splitlines()
            samples = rows[0].split('\t')[1:]
            assert len(samples) == len(set(samples))
            names = [r.split('\t')[0] for r in rows[1:]]
            tissue = Path(m.name).name.split('.v11')[0]
            cov[assay, tissue] = {'sample_n': len(samples), 'covariates': names,
                                  'covariate_n': len(names), 'source_member': m.name}
features = {}
with tarfile.open(use('inputs/public/v11-sqtl-groups.tar'), 'r:') as t:
    for m in t:
        if not m.isfile():
            continue
        data = t.extractfile(m).read()
        if m.name.endswith('.gz'):
            data = gzip.decompress(data)
        rows = [s for s in data.decode().splitlines() if 'ENSG00000109099.' in s]
        tissue = Path(m.name).name.split('.v11')[0]
        features[tissue] = [r.split('\t')[0] for r in rows]

harmonized = []
for r in inspection['genes']:
    b, se = float(r['slope']), float(r['slope_se'])
    ch, pos, ref, alt = variant(r['variant_id'], True)
    assert (ch, pos, ref, alt) == (r['chr'], int(r['variant_pos']), r['ref'], r['alt'])
    lo, hi = ci(b, se)
    row = dict(r, beta=b, se=se, ci95_normal_low=lo, ci95_normal_high=hi,
               source_gene_fdr_pass=float(r['qval']) < .05, dataset='GTEx_v11',
               assembly='GRCh38', effect_allele=alt, other_allele=ref,
               ci_note='Approximate normal interval; not selection-adjusted; source-normalized scale, not RNA percentage',
               **cov[r['assay'], r['tissue']])
    if r['assay'] == 'sqtl':
        row['tested_features'] = features[r['tissue']]
        assert len(row['tested_features']) == int(r['group_size'])
    else:
        row['tested_features'] = [r['gene_id']]
    row['variant_universe_status'] = 'Source-reported num_var; all-tested variant IDs not obtained for GTEx v11'
    harmonized.append(row)
assert len(harmonized) == 98
save('tested-feature-summary.json', harmonized)
table('tested-feature-summary.tsv', harmonized)

# Source-produced fine mapping. Filter in Arrow before conversion, retaining every matching record.
cs = []
for assay in ['eqtl', 'sqtl']:
    with tarfile.open(use(f'inputs/public/v11-{assay}-susie.tar'), 'r:') as t:
        for m in t:
            if not m.isfile() or not m.name.endswith('.parquet'):
                continue
            tab = pq.read_table(io.BytesIO(t.extractfile(m).read()))
            gene_key = 'phenotype_id' if assay == 'eqtl' else 'gene_id'
            assert gene_key in tab.column_names
            selected = tab.filter(pc.equal(tab[gene_key], 'ENSG00000109099.16'))
            for r in selected.to_pylist():
                cs.append(dict(r, assay=assay, source_member=m.name,
                               tissue=Path(m.name).name.split('.v11')[0]))
assert len(cs) == 8 and all(x['assay'] == 'sqtl' for x in cs)
for group in {(x['tissue'], x['phenotype_id'], x['cs_id']) for x in cs}:
    rs = [x for x in cs if (x['tissue'], x['phenotype_id'], x['cs_id']) == group]
    assert len(rs) == rs[0]['cs_size']
table('source-credible-sets.tsv', cs)

# Direct eligible significant-pair rows, no guessed all-variant negatives.
pairs = list(inspection['significant_pairs'])
for tissue in ['Adipose_Subcutaneous', 'Ovary']:
    rel = f'inputs/native/v11-sqtl/{tissue}.v11.sQTLs.signif_pairs.parquet'
    tab = pq.read_table(use(rel), filters=[('group_id', '=', 'ENSG00000109099.16')])
    for r in tab.to_pylist():
        pairs.append(dict(r, assay='sqtl', tissue=tissue, source=rel))
for r in pairs:
    variant(r['variant_id'], True)
    r['ci95_normal_low'], r['ci95_normal_high'] = ci(r['slope'], r['slope_se'])
table('selected-associations.tsv', pairs)

# GENCORD exact all-tested universe: rsID alias rows can repeat but numerical fields must match.
with use('outputs/independent-r002/GENCORD-PMP22-native.tsv').open() as f:
    raw = list(csv.DictReader(f, delimiter='\t'))
byvar = defaultdict(list)
for r in raw:
    assert r['gene_id'] == r['molecular_trait_id'] == 'ENSG00000109099'
    ch, pos, ref, alt = variant(r['variant'])
    assert (ch, pos, ref, alt) == ('chr'+r['chromosome'], int(r['position']), r['ref'], r['alt'])
    byvar[r['variant']].append(r)
gen = []
for v, rows in byvar.items():
    for r in rows[1:]:
        assert {k:x for k,x in r.items() if k != 'rsid'} == {k:x for k,x in rows[0].items() if k != 'rsid'}
    r = dict(rows[0], rsid_aliases=sorted({x['rsid'] for x in rows}), alias_rows=len(rows))
    r['ci95_normal_low'], r['ci95_normal_high'] = ci(r['beta'], r['se'])
    gen.append(r)
with gzip.open(use('inputs/public/QTD000100.permuted.tsv.gz'), 'rt') as f:
    perm = [r for r in csv.DictReader(f, delimiter='\t') if r['molecular_trait_id'] == 'ENSG00000109099']
assert len(perm) == 1 and len(gen) == int(perm[0]['n_variants']) == 8593
assert len(raw) == indval[0]['target_rows']
table('GENCORD-tested-variants.tsv', gen)
primary = next(r for r in gen if r['variant'] == 'chr17_15314994_A_G')
assert float(primary['an']) == 372 and primary['rsid'] == 'rs2531950'
independent = {'GENCORD': {'raw_rows':len(raw), 'unique_variants':len(gen), 'duplicates_identical_except_rsid':True,
 'permutation':perm[0], 'primary_prediction':primary, 'replication_success':float(primary['beta'])>0 and float(primary['pvalue'])<.05,
 'verdict':'Failed significance rule; same direction, not replicated, not effect-size equivalence or demonstrated heterogeneity',
 'cohort':'Independent newborn cord-derived fibroblasts, source sample_size186; GTEx adult fibroblast transfer limit',
 'catalogue_model':'Source uniform pipeline; normalized RNA, 6 genotype PCs + 6 expression PCs in official methods; no refitting'},
 'TwinsUK':{'exact_junction_verdict':'Untestable in available public export; absent target at queried variant is not a tested negative',
 'export_target_rows':indval[1]['target_rows'], 'permutation_other_junction':readj('inputs/text/twins-perm-target.json'),
 'exact_variant_range':readj('inputs/ranges/QTD000538-15263668-cc/result.json'),
 'selection_and_relatedness':'Primary Catalogue paper explicitly uses unrelated subset of TwinsUK; do not count all original twins or tissues as independent samples',
 'cohort_sample_size_from_r7_metadata':381,'not_substituted':'15260757 acceptor differs by4 bases from15260761; cluster labels do not certify matching features'}}
assert independent['GENCORD']['replication_success'] is False
save('independent-evidence.json', independent)

# Join all overlapping discovery pairs to independent tested variants; exploratory, not rescue testing.
lookup = {r['variant']:r for r in gen}
joined = []
for r in pairs:
    if r['assay'] != 'eqtl' or r['tissue'] != 'Cells_Cultured_fibroblasts':
        continue
    key = r['variant_id'].removesuffix('_b38')
    g = lookup.get(key)
    joined.append({'variant_id':r['variant_id'],'GTEx_beta':r['slope'],'GTEx_p':r['pval_nominal'],
                   'GENCORD_tested':g is not None,'GENCORD_beta':None if g is None else g['beta'],
                   'GENCORD_p':None if g is None else g['pvalue'],
                   'descriptive_only':True})
table('cross-cohort-variant-overlap.tsv', joined)

# Direct source-compatible chain mapping; both source endpoint conventions retained.
ann = readj('inputs/human-interval-annotations.json')
blocks = []
with gzip.open(use('inputs/public/hg18ToHg38.over.chain.gz'), 'rt') as f:
    for line_no, line in enumerate(f,1):
        s = line.split()
        if not s:
            continue
        if s[0] == 'chain':
            header=s; tx=int(s[5]); qx=int(s[10]); continue
        size=int(s[0])
        if header[2]=='chr17':
            blocks.append((tx,tx+size,qx,header[7],header[9],int(header[8]),header[12],line_no))
        if len(s)==3:
            tx+=size+int(s[1]); qx+=size+int(s[2])

def lift(a,b):
    hits=[]
    for x,y,z,ch,strand,sz,cid,line in blocks:
        if x<=a and b<=y:
            l,h=z+a-x,z+b-x
            if strand=='-': l,h=sz-h,sz-l
            hits.append({'chr':ch,'start0':l,'end0':h,'orientation':strand,'chain':cid,'chain_line':line})
    assert len(hits)==1
    return hits[0]
reg=[]
for r in ann['intervals']:
    z=lift(r['start'],r['end']);o=lift(r['start']-1,r['end'])
    assert z['chr']==o['chr']=='chr17' and z['chain']==o['chain']
    reg.append(dict(r,assembly='GRCh38',chromosome='chr17',source_assembly='hg18',
                    core_start0=max(z['start0'],o['start0']),core_end0=min(z['end0'],o['end0']),
                    outer_start0=min(z['start0'],o['start0']),outer_end0=max(z['end0'],o['end0']),
                    zero_based_hypothesis=z,one_based_hypothesis=o,source_convention=ann['source_convention']))
# Preserve GTF exon coordinates and all tags, not just the last repeated tag.
gtf=[]
with gzip.open(use('inputs/public/gencode47.gtf.gz'),'rt') as f:
    for line_no,line in enumerate(f,1):
        if line.startswith('#') or 'gene_id "ENSG00000109099.' not in line:
            continue
        c=line.rstrip('\n').split('\t'); attrs=defaultdict(list)
        for k,v in re.findall(r'(\w+) "([^"]*)"',c[8]): attrs[k].append(v)
        gtf.append({'source_line':line_no,'chromosome':c[0],'feature':c[2],'start1':int(c[3]),'end1':int(c[4]),
                    'start0':int(c[3])-1,'end0':int(c[4]),'strand':c[6],'attributes':dict(attrs),'raw':line.rstrip('\n')})
assert len(gtf)==373
exons=defaultdict(list)
for r in gtf:
    if r['feature']=='exon':exons[r['attributes']['transcript_id'][0]].append(r)
junction=[]
for tx,ex in exons.items():
    ex.sort(key=lambda r:r['end1'],reverse=True)
    for i,(up,down) in enumerate(zip(ex,ex[1:])):
        if (down['end1'],up['start1'])==(15260761,15265154):
            junction.append({'transcript_id':tx,'upstream_exon_ordinal':i+1,'downstream_exon_ordinal':i+2,
                             'strand':'-','upstream_exon_source_line':up['source_line'],'downstream_exon_source_line':down['source_line']})
assert len(junction)==4 and all(r['upstream_exon_ordinal']==1 for r in junction)
overlap=[]
for r in pairs:
    ch,pos,ref,alt=variant(r['variant_id'],True)
    start,end=pos-1,pos-1+len(ref)
    for g in reg:
        core=start<g['core_end0'] and end>g['core_start0']
        envelope=start<g['outer_end0'] and end>g['outer_start0']
        if envelope:overlap.append({'variant_id':r['variant_id'],'tissue':r['tissue'],'assay':r['assay'],'region':g['name'],
                                    'overlap_core':core,'overlap_envelope':envelope,'interpretation':'Coordinate overlap only; LD/causality/cell-context unproven'})
save('coordinate-annotation-provenance.json', {'human_reporter_intervals':reg,'gencode47':gtf,
 'first_exon_junction_matches':junction,'overlaps':overlap,
 'limitations':['No rat lift','No boundary convention silently assigned','No P1/P2 initiation inference from steady-state junctions',
 'Variants correlated; no independently computed LD or colocalization. GTEx provided SuSiE sets retain their source model.']})
table('human-regulatory-intervals.tsv',reg)
table('association-region-overlaps.tsv',overlap)

summary={'tested_eQTL_tissues':50,'tested_sQTL_tissues':48,'absent_sQTL_tissues':['Whole_Blood','Cells_EBV-transformed_lymphocytes'],
 'source_q_pass_tissues':{a:[r['tissue'] for r in harmonized if r['assay']==a and r['source_gene_fdr_pass']] for a in ['eqtl','sqtl']},
 'selected_pair_counts':{f'{a}:{t}':n for (a,t),n in Counter((r['assay'],r['tissue']) for r in pairs).items()},
 'selected_CI_rows':[r for r in harmonized if (r['assay'],r['tissue']) in [('eqtl','Nerve_Tibial'),('eqtl','Cells_Cultured_fibroblasts'),('sqtl','Adipose_Subcutaneous')]],
 'credible_set_counts':dict(Counter(r['tissue'] for r in cs)),
 'adipose_pip_sum':sum(r['pip'] for r in cs if r['tissue']=='Adipose_Subcutaneous'),
 'adipose_cs_span1':[min(variant(r['variant_id'],True)[1] for r in cs if r['tissue']=='Adipose_Subcutaneous'),max(variant(r['variant_id'],True)[1] for r in cs if r['tissue']=='Adipose_Subcutaneous')],
 'GENCORD_primary_CI':{k:primary[k] for k in ['beta','se','pvalue','ci95_normal_low','ci95_normal_high']},
 'cross_cohort_shared_discovery_variants':sum(r['GENCORD_tested'] for r in joined),
 'coordinate_overlaps':overlap,
 'stopping_conclusion':'Human cis-expression and splice associations support regulatory hypotheses beyond copy-number studies; no independent replication secured for the leading tested hypotheses and no initiation/cell-type/protein causal resolution.'}
save('results-summary.json',summary)
save('input-manifest.json',{'inputs':list(inputs.values()),'inherited_inspection_artifact':'artifact_378dd1dde1005fd0e0d90e022df9e66367227636b3f092afd63a1abd31f6624a'})
validation={'all_assertions_passed':True,'gencord_exact_variant_universe_matches_permutation':True,
 'gencord_alias_dedup_numeric_equality':True,'native_gencode_row_count':len(gtf),'human_mapped_intervals':len(reg),
 'junction_matching_transcripts':len(junction),'source_cs_rows':len(cs),'selected_pairs':len(pairs),
 'python':platform.python_version(),'platform':platform.platform(),'pyarrow':pyarrow.__version__,
 'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}}
save('analysis-validation.json',validation)
print(json.dumps({k:v for k,v in summary.items() if k not in ['selected_CI_rows']},indent=2))
print('VALIDATION',json.dumps(validation))
