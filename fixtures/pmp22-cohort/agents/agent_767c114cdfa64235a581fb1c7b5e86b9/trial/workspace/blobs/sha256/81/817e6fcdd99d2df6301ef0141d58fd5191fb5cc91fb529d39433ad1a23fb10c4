"""PMP22 screen on immutable processed eCLIP and GC-corrected RNA-seq; no raw analysis."""
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import zipfile
import openpyxl
q=Path(__file__).resolve().parents[1]
w=Path(os.environ['BIO_WORKSPACE'])
out=q/'outputs/screen-r001'
out.mkdir(parents=True,exist_ok=True)
manifest=json.loads((q/'inputs/screen-manifest-r001.json').read_text())
inputs={r['name']:r for r in manifest['files']}


def data(name):
    r=inputs[name]
    p=w/'blobs/sha256'/r['sha256'][:2]/r['sha256']
    b=p.read_bytes()
    assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],name
    return b


def dump(name,obj):
    (out/name).write_text(json.dumps(obj,indent=2,allow_nan=False))


def table(name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (out/name).open('w') as f:
        writer=csv.DictWriter(f,fieldnames=fields,delimiter='\t')
        writer.writeheader()
        for r in rows:
            writer.writerow({k:json.dumps(v,sort_keys=True) if isinstance(v,(list,dict)) else v for k,v in r.items()})


def bh(pvals,by=False):
    n=len(pvals)
    order=sorted(range(n),key=lambda i:pvals[i])
    adjusted=[1.0]*n
    scale=sum(1/k for k in range(1,n+1)) if by else 1.0
    last=1.0
    for rank in range(n,0,-1):
        i=order[rank-1]
        last=min(last,pvals[i]*n/rank*scale)
        adjusted[i]=last
    return adjusted


def finite(s):
    if s in ['NA','NaN','nan','']:
        return None
    x=float(s)
    assert math.isfinite(x),s
    return x


def overlaps(a,b):
    return a['chrom']==b['chrom'] and a['strand']==b['strand'] and a['start']<b['end'] and b['start']<a['end']


# GTF uses one-based closed intervals; every derived interval is zero-based half-open.
genes={}
features=[]
for line in gzip.decompress(data('gencode19-encode-gtf-r001')).decode().splitlines():
    if line.startswith('#'):
        continue
    a=line.split('\t')
    attrs=dict(re.findall(r'(\w+) "([^"]*)"',a[8]))
    g={'chrom':a[0],'start':int(a[3])-1,'end':int(a[4]),'strand':a[6],'name':attrs['gene_name']}
    if a[2]=='gene':
        genes[attrs['gene_id']]=g
    if attrs['gene_name']=='PMP22':
        features.append(dict(g,feature=a[2],attrs=attrs))
targets=[key for key,val in genes.items() if val['name']=='PMP22']
assert len(targets)==1
target=targets[0]
gene=genes[target]
transcripts=defaultdict(list)
for f in features:
    if 'transcript_id' in f['attrs']:
        transcripts[f['attrs']['transcript_id']].append(f)


def annotation(peak):
    annotations={}
    for tx,fs in transcripts.items():
        span=next(f for f in fs if f['feature']=='transcript')
        if not overlaps(peak,span):
            continue
        categories=set()
        cds=[f for f in fs if f['feature']=='CDS']
        for f in fs:
            if not overlaps(peak,f):
                continue
            if f['feature']=='CDS':
                categories.add('CDS')
            elif f['feature']=='UTR' and cds:
                # Minus-strand PMP22: genomic left of coding sequence is 3-prime UTR.
                if f['end']<=min(c['start'] for c in cds):
                    categories.add('3UTR')
                elif f['start']>=max(c['end'] for c in cds):
                    categories.add('5UTR')
                else:
                    categories.add('UTR_other')
            elif f['feature']=='exon' and not cds:
                categories.add('noncoding_exon')
        if not categories:
            categories.add('intronic')
        annotations[tx]=sorted(categories)
    return annotations


selection=json.loads(data('selection-r001.json'))
supp={}
with zipfile.ZipFile(io.BytesIO(data('encore-supplement-zip-r001'))) as z:
    for num in [4,6,7,11,12]:
        name=f'41586_2020_2077_MOESM{num}_ESM.xlsx'
        wb=openpyxl.load_workbook(io.BytesIO(z.read(name)),read_only=True,data_only=True)
        supp[num]={sheet.title:list(sheet.values) for sheet in wb}
        wb.close()
questionable={(r[1],r[3]) for r in supp[11]['Sheet1'][2:] if r[1]}
qc={}
for cell in ['HepG2','K562']:
    for r in supp[7][cell][2:]:
        qc[r[3]]={'kd_reads':[r[5],r[6]],'control_reads':[r[7],r[8]],'source_reported_de_genes':r[9]}
rows=[]
peaks=[]
backgrounds=[]
gene_universes={}
for item in [x for x in selection if x['role']=='idr_peaks']:
    key=(item['rbp'],item['cell'])
    row={k:item[k] for k in ['rbp','cell']}
    row.update(eclip_experiment=item['experiment'],eclip_control=item['control'],peak_file=item['file']['File accession'],assembly='hg19',target_gene_id=target,questionable_eclip_qc=key in questionable)
    lines=gzip.decompress(data('file-'+row['peak_file']+'-r001')).decode().splitlines()
    hits=[]
    for line in lines:
        a=line.split('\t')
        assert len(a)==10
        peak={'chrom':a[0],'start':int(a[1]),'end':int(a[2]),'strand':a[5]}
        if not overlaps(peak,gene):
            continue
        peak.update(rbp=item['rbp'],cell=item['cell'],source_file=row['peak_file'],signal_column7=float(a[6]),negative_log10p_column8=float(a[7]))
        peak['transcript_features']=annotation(peak)
        peak['same_strand_overlapping_genes']=[gid for gid,g in genes.items() if overlaps(peak,g)]
        hits.append(peak)
        peaks.append(peak)
    row.update(selected_idr_peak_rows_genome=len(lines),pmp22_idr_peak_rows=len(hits),binding_status='selected_reproducible_peak' if hits else 'no_selected_reproducible_peak_not_a_binding_zero',site_classes=sorted({c for p in hits for v in p['transcript_features'].values() for c in v}),max_signal_column7=max((p['signal_column7'] for p in hits),default=None))
    matches=[x for x in selection if x['role']=='de_paired' and (x['rbp'],x['cell'])==key]
    if not matches:
        row['rna_status']='no_matched_perturbation_in_source_map'
        rows.append(row)
        continue
    kd=matches[0]
    row.update(rna_experiment=kd['experiment'],rna_control=kd['control'],control_matches=kd['control_matches'],de_file=kd['file']['File accession'],superseded_de_file=kd['supplement_file_id'])
    native=list(csv.reader(io.StringIO(data('file-'+row['de_file']+'-r001').decode()),delimiter='\t'))
    assert native[0]==['baseMean','log2FoldChange','lfcSE','stat','pvalue','padj']
    measurements={}
    for a in native[1:]:
        assert len(a)==7 and a[0] not in measurements
        measurements[a[0]]=dict(zip(native[0],[finite(v) for v in a[1:]]))
    uni=sorted(measurements)
    usha=hashlib.sha256('\n'.join(uni).encode()).hexdigest()
    gene_universes[usha]=uni
    backgrounds.append({'file':row['de_file'],'rbp':row['rbp'],'cell':row['cell'],'gene_universe_sha256':usha,'rows':len(uni),'finite_pvalue':sum(v['pvalue'] is not None for v in measurements.values()),'finite_padj':sum(v['padj'] is not None for v in measurements.values()),'zero_baseMean':sum(v['baseMean']==0 for v in measurements.values()),'all_gene_fdr05':sum(v['padj'] is not None and v['padj']<=.05 for v in measurements.values())})
    if target not in measurements:
        row['rna_status']='target_not_in_supplied_feature_universe'
        rows.append(row)
        continue
    value=measurements[target]
    row.update({'pmp22_'+k:v for k,v in value.items()})
    row['rna_status']='measured' if value['pvalue'] is not None else ('measured_zero' if value['baseMean']==0 else 'pvalue_unavailable_filtered_or_outlier')
    if value['log2FoldChange'] is not None and value['lfcSE'] is not None:
        row['ci95_lower']=value['log2FoldChange']-1.959963984540054*value['lfcSE']
        row['ci95_upper']=value['log2FoldChange']+1.959963984540054*value['lfcSE']
        row['absolute_effect_lower95']=max(0,abs(value['log2FoldChange'])-1.959963984540054*value['lfcSE'])
    ids=[gid for gid,g in genes.items() if g['name']==item['rbp'] and gid in measurements]
    row['kd_target_gene_ids']=ids
    row['target_rna_depletion']=measurements[ids[0]] if len(ids)==1 else None
    tv=row['target_rna_depletion']
    row['adequate_target_rna_depletion']=bool(tv and tv['log2FoldChange'] is not None and tv['log2FoldChange']<=-1 and tv['padj'] is not None and tv['padj']<=.05)
    row['source_sequencing_qc']=qc.get(kd['experiment'])
    rows.append(row)
paired=[r for r in rows if 'de_file' in r]
assert len(rows)==223 and len(paired)==203
# Failed/untestable comparisons retain their family slot with p=1 solely for multiplicity.
# This is not imputing a measured RNA abundance or biological effect.
pvals=[r['pmp22_pvalue'] if r.get('pmp22_pvalue') is not None and r['control_matches'] else 1 for r in paired]
for r,b,y in zip(paired,bh(pvals),bh(pvals,True),strict=True):
    r['pmp22_screen_bh203']=b
    r['pmp22_screen_by203']=y
    r['primary_joint_candidate']=bool(r['control_matches'] and r['pmp22_idr_peak_rows'] and not r['questionable_eclip_qc'] and r.get('pmp22_padj') is not None and r['pmp22_padj']<=.05 and b<=.05 and r['adequate_target_rna_depletion'])
    r['low_coverage_flag']=r.get('pmp22_baseMean',0)<20
candidates=sorted([r for r in paired if r['primary_joint_candidate']],key=lambda r:(-r['absolute_effect_lower95'],-r['max_signal_column7']))
for rank,r in enumerate(candidates,1):
    r['candidate_rank']=rank
summary={'question':q.name,'target':dict(gene,gene_id=target),'contexts':len(rows),'paired_contexts':len(paired),'unique_rbps':len({r['rbp'] for r in rows}),'binding_positive_contexts':sum(bool(r['pmp22_idr_peak_rows']) for r in rows),'candidate_count':len(candidates),'rna_status_counts':dict(Counter(r['rna_status'] for r in rows)),'qc_questionable_contexts':sum(r['questionable_eclip_qc'] for r in rows),'gene_universe_count':len(gene_universes),'candidates':candidates,'scope':'Exploratory binding-plus-steady-state-RNA association; no decay or cell-context transfer estimated'}
dump('summary.json',summary)
dump('binding-by-perturbation.json',rows)
table('binding-by-perturbation.tsv',rows)
dump('pmp22-peak-sites.json',peaks)
table('pmp22-peak-sites.tsv',peaks)
dump('eligible-backgrounds.json',{'files':backgrounds,'gene_universes':gene_universes,'pmp22_fdr_family':{'size':203,'null_slots_for_untestable':sum(p==1 for p in pvals)},'thresholds':{'gene_fdr':.05,'screen_bh':.05,'knockdown_max_log2':-1,'knockdown_fdr':.05,'low_baseMean_sensitivity':20}})
dump('pmp22-transcript-annotation.json',features)
print(json.dumps({k:v for k,v in summary.items() if k!='candidates'},indent=2))
print('CANDIDATES',json.dumps([{k:r.get(k) for k in ['rbp','cell','candidate_rank','pmp22_idr_peak_rows','site_classes','pmp22_baseMean','pmp22_log2FoldChange','ci95_lower','ci95_upper','pmp22_padj','pmp22_screen_bh203','pmp22_screen_by203','adequate_target_rna_depletion','de_file','peak_file']} for r in candidates],indent=2))
print('ALL BOUND CONTEXTS',json.dumps([{k:r.get(k) for k in ['rbp','cell','pmp22_idr_peak_rows','site_classes','pmp22_log2FoldChange','pmp22_padj','pmp22_screen_bh203','adequate_target_rna_depletion']} for r in rows if r['pmp22_idr_peak_rows']],indent=2))
