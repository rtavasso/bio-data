"""Descriptive audit of immutable processed GSE165206; no donor inference."""
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

Q = Path(__file__).resolve().parents[1]
WORK = Q.parents[1]
BLOB = '18d7514262d8f22f193bbf44a0b27966de83714cb93d1e5d4a9661721622a3db'
SOURCE = WORK / 'blobs' / 'sha256' / BLOB[:2] / BLOB
OUT = Q / 'outputs'
PANEL = ['Pmp22','Egr2','Jun','Sox10','Mpz','Mbp','Mag','Prx','Sox2','Ngfr','Pou3f1','Yap1','Wwtr1','Tead1','Erbb2','Erbb3']
SAMPLES = ['GSM5028218','GSM5028219','GSM5028220','GSM5028221','GSM5028222','GSM5028223']
CONTRASTS = [('stiff_minus_soft',SAMPLES[0],SAMPLES[1]),('large_minus_small',SAMPLES[2],SAMPLES[3]),('elongated_minus_nonelongated',SAMPLES[4],SAMPLES[5])]
with SOURCE.open('rb') as f:
    assert hashlib.file_digest(f,'sha256').hexdigest() == BLOB
platform = {}
samples = {}
section = None
sample = None
headers = None
expected = {}
with SOURCE.open() as stream:
    for line_no,line in enumerate(stream,1):
        line=line.rstrip('\r\n')
        if line.startswith('^SAMPLE = '):
            sample=line.split(' = ',1)[1]
            assert sample not in samples
            samples[sample]={}
        if line.startswith('!Sample_data_row_count = '):
            expected[sample]=int(line.split(' = ')[1])
        if line in ('!platform_table_begin','!sample_table_begin'):
            section='platform' if 'platform' in line else 'sample'
            headers=None
            continue
        if line in ('!platform_table_end','!sample_table_end'):
            section=None
            continue
        if section:
            values=line.split('\t')
            if headers is None:
                headers=values
                continue
            if section=='platform':
                assert len(values)==len(headers)
                probe=values[0]
                assert probe not in platform
                assignment=values[headers.index('mrna_assignment')]
                symbols=set()
                for block in assignment.split(' /// '):
                    fields=block.split(' // ')
                    if len(fields)>=3 and fields[1]=='RefSeq':
                        match=re.search(r'\(([A-Za-z][A-Za-z0-9_-]*)\), (?:transcript variant .*?, )?(?:mRNA|non-coding RNA)',fields[2])
                        if match:
                            symbols.add(match.group(1))
                platform[probe]={'symbols':sorted(symbols),'category':values[headers.index('category')], 'line':line_no,'annotation':assignment}
            else:
                assert headers==['ID_REF','VALUE','DETECTION P-VALUE']
                probe=values[0]
                assert probe not in samples[sample]
                samples[sample][probe]={'value_token':values[1],'detection_token':values[2],'line':line_no}
assert sorted(samples)==SAMPLES
for s in SAMPLES:
    assert len(samples[s])==expected[s]
    assert set(samples[s])==set(samples[SAMPLES[0]])

def number(token):
    if token in ('','NA','NaN','null','NULL'):
        return None
    value=float(token)
    assert math.isfinite(value), token
    return value

all_rows=[]
panel_rows=[]
for probe in samples[SAMPLES[0]]:
    a=platform.get(probe)
    assert a is not None,probe
    row={'probe':probe,'symbols':'|'.join(a['symbols']), 'platform_line':a['line'],'category':a['category'],'mapping_status':'single_refseq_symbol' if len(a['symbols'])==1 else 'multiple_refseq_symbols' if a['symbols'] else 'no_refseq_symbol_extracted'}
    for s in SAMPLES:
        m=samples[s][probe]
        value=number(m['value_token'])
        p=number(m['detection_token'])
        assert p is None or 0<=p<=1
        row.update({s+'_value':value,s+'_value_token':m['value_token'],s+'_detection_p':p,s+'_detection_token':m['detection_token'],s+'_line':m['line']})
    for name,case,control in CONTRASTS:
        x,y=row[case+'_value'],row[control+'_value']
        row[name]=None if x is None or y is None else x-y
        p1,p0=row[case+'_detection_p'],row[control+'_detection_p']
        row[name+'_both_detection_lt_005']=None if p1 is None or p0 is None else p1<0.05 and p0<0.05
    all_rows.append(row)
    if set(a['symbols']) & set(PANEL):
        panel_rows.append(row)

def tsv(path,rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)

tsv(OUT/'array-all-probes.tsv',all_rows)
tsv(OUT/'array-panel.tsv',panel_rows)
annotation_rows=[{'probe':p,**a,'symbols':'|'.join(a['symbols'])} for p,a in platform.items() if set(a['symbols']) & set(PANEL)]
tsv(OUT/'array-panel-annotations.tsv',annotation_rows)
summary={'source_blob':BLOB,'assay':'processed total-RNA rat Clariom S array','cell_context':'RT4-D6P2T; passage5; two days per GEO','units':'Native VALUE Quantification; paper reports RMA and log2 transformation; differences are deposited source-scale, not independently normalized log2FC','replication':'one deposited array per condition; no independent-donor variance','sample_ids':SAMPLES,'n_platform_probes':len(platform),'n_measured_probes_each':len(all_rows),'n_panel_probes':len(panel_rows),'missing_panel_symbols':[g for g in PANEL if not any(g in platform[r['probe']]['symbols'] for r in panel_rows)],'detection_rule':'Analyst screen p<0.05, not authors established DE or expression rule; all values retained','statistics':{},'contrasts':{},'panel':panel_rows,'inferential_pvalues':None,'mediation_fraction':None,'promoter_initiation_identified':False}
for s in SAMPLES:
    vv=[r[s+'_value'] for r in all_rows if r[s+'_value'] is not None]
    pp=[r[s+'_detection_p'] for r in all_rows if r[s+'_detection_p'] is not None]
    summary['statistics'][s]={'numeric_values':len(vv),'missing_values':len(all_rows)-len(vv),'min':min(vv),'median':statistics.median(vv),'max':max(vv),'zero_values':sum(x==0 for x in vv),'detection_lt_005':sum(x<0.05 for x in pp)}
for name,case,control in CONTRASTS:
    vv=[r[name] for r in all_rows if r[name] is not None and r['category']=='main']
    summary['contrasts'][name]={'case':case,'control':control,'main_probes':len(vv),'median':statistics.median(vv),'min':min(vv),'max':max(vv),'n_abs_source_difference_gt1':sum(abs(x)>1 for x in vv)}
(OUT/'array-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ('panel','statistics')},indent=2))
for r in panel_rows:
    print(r['symbols'],r['probe'], 'stiff',r[SAMPLES[0]+'_value'],'soft',r[SAMPLES[1]+'_value'],'difference',r['stiff_minus_soft'],'detect',r[SAMPLES[0]+'_detection_p'],r[SAMPLES[1]+'_detection_p'])
