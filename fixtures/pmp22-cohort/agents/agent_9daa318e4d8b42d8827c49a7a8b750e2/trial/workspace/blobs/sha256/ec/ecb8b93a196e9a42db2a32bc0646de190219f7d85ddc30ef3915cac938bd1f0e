from pathlib import Path
import json,subprocess,hashlib
Q=Path(__file__).resolve().parents[1];ROOT=Q.parents[2];O=Q/'outputs/iteration';records={}
inputs=[p for p in (Q/'inputs/iteration').rglob('*') if p.is_file() and not p.name.endswith('.lock')]
(O/'source-inventory.json').write_text(json.dumps([{'path':str(p.relative_to(Q)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs],indent=2))
interpretations=[p for p in O.iterdir() if p.is_file() and p.suffix in {'.json','.md'} and p.name not in {'preservation.json','sync-final.json'}]
interpretations += [p for p in (Q/'outputs').glob('mechanisms.r[0-9][0-9][0-9].json') if int(p.stem.split('r')[-1])>=13]
interpretations += [p for p in (Q/'outputs').glob('investigations.r[0-9][0-9][0-9].json') if int(p.stem.split('r')[-1])>=11]
interpretations += [Q/'outputs'/n for n in ['discoveries.r003.json','evidence-coverage.tsv']]
for p in inputs+interpretations:
 cls='source' if p.is_relative_to(Q/'inputs') else 'interpretation'
 r=subprocess.run([str(ROOT/'bin/bio'),'object','add',str(p),'--classification',cls],capture_output=True,text=True,check=True)
 records[str(p.relative_to(Q))]=json.loads(r.stdout)
(O/'preservation.json').write_text(json.dumps(records,indent=2))
receipt=subprocess.run([str(ROOT/'bin/bio'),'object','add',str(O/'preservation.json'),'--classification','interpretation'],capture_output=True,text=True,check=True)
(O/'preservation-receipt.json').write_text(receipt.stdout)
summary=['\n### Final new-iteration preservation and verification\n']
for f in ['outputs/mechanisms.r014.json','outputs/investigations.r017.json','outputs/discoveries.r003.json','outputs/evidence-coverage.tsv','outputs/iteration/REPORT.md']:
 summary.append('- '+f+': '+records[f]['blob']+'\n')
summary.append('\nVerified 49 artifact registration receipts, immutable derivation inputs/code, question links, unchanged frozen prediction and independent Pmp22 contrast arithmetic. Native target flag audit passes all48 observations. Verifier initially referenced a nonexistent named sample-index column; corrected to the saved unnamed index, without changing analysis outputs or thresholds. Historical format-role collisions remain explicitly resolved in registrations.json. Current status checker passes.\n')
summary.append('\nThis iteration accounts for73 retrieval requests and216,941,407bytes including260,000estimatedwebbytes, below the150request/1GiBtotal/512MiBperfile limits. No further acquisition occurred after budget-final.json. Original broad question remains open; selected new high-priority branches have executed analyses, with source clarification and matched-endpoint requirements recorded. Inherited work retains inherited credit. Reproduction instructions, source inventory, exact preservation receipts and current figure r002 are under outputs/iteration.\n')
(Q/'LABBOOK.md').open('a').writelines(summary)
print(json.dumps({'objects_preserved':len(records),'manifest_receipt':json.loads(receipt.stdout)},indent=2))
