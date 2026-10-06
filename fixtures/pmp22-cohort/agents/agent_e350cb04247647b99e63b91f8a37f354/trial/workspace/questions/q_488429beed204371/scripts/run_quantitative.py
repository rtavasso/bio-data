"""Run the current local producer with a fresh, explicit execution receipt."""
import argparse
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--receipt', required=True)
a = p.parse_args()
names = ['sample-design.tsv','pmp22-native-rows.tsv','cluster-membership.tsv','per-library-start-signals.tsv',
         'condition-variation.tsv','contrasts-and-sensitivity.tsv','leave-one-library.tsv','cross-library-contrasts.tsv',
         'clone-family-contrasts.tsv','all-pmp22-cluster-contrasts.tsv','comparator-coverage.tsv','comparator-per-library.tsv',
         'comparator-contrasts.tsv','selected-universe-quality.tsv','summary.json','focal-library-responses.png',
         'focal-library-responses.svg','robustness-grid.png','comparator-responses.png','analysis-output-manifest.json']
command = ['./bin/python','.agents/skills/bio-research/scripts/run_analysis.py','--receipt',str(q/'outputs'/a.receipt)]
for name in names:
    command.extend(['--output',str(q/'outputs'/name)])
command.extend(['--','./bin/python',str(q/'scripts/analyze_responses.py')])
raise SystemExit(subprocess.run(command, check=False).returncode)
