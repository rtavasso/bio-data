from pathlib import Path
import json
q=Path(__file__).resolve().parents[1]/'outputs/upstream'
n=json.loads((q/'nae1-RNA-summary.json').read_text());print('RNA',{k:n[k] for k in ['pmp22_log2FC','marker_mean_log2FC','deltaR','deltaR_uncertainty','passes_locked_rule']})
d=json.loads((q/'antioxidant-posthoc-summary.json').read_text());print('PANELS')
for r in d['panels']:
 if r['panel'] in ['eligible4','discovery_gene_excluded','Pmp22']:print({k:r[k] for k in ['study','panel','effect','ci95','sample_omission_range','gene_omission_range']})
print('BROAD',d['broad']['shared']);m=json.loads((q/'antioxidant-source-mapping.json').read_text());print('MAPPING',[(r['group'],r['correlation']) for r in m]);r=json.loads((q/'transport-final.json').read_text());print('TRANSPORT',{k:r[k] for k in ['direct_attempts','direct_requests_including_recorded_redirects','direct_payload_bytes','managed_RNA_payload_bytes','known_new_payload_bytes']})
x=json.loads((q.parent/'investigations.json').read_text());print('PENDING',[(r['id'],r['priority'],r['status']) for r in x['items'] if r['status'] not in ['analyzed','rejected','blocked']]);print('HORMONE',[(r['id'],r['status']) for r in x['items'] if 'hormon' in r['id']])
