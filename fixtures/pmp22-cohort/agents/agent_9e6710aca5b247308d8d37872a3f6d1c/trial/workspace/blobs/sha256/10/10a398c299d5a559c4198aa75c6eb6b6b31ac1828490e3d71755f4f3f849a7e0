"""Independently validate source matrices, effects and frozen predictions."""
import hashlib
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

Q = Path(__file__).resolve().parents[1]
W = Q.parents[1]
OUT = Q/'outputs'

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def finite_records(frame):
    return json.loads(frame.to_json(orient='records'))

r = json.loads((OUT/'analysis-execution-r003.json').read_text())
assert r['complete'] and r['exit_code']==0 and r['code_unchanged']
assert sha(Q/'scripts/analyze_mechanics.py') == r['code_sha256']
for x in r['outputs']:
    assert x['written'] and sha(OUT/Path(x['path']).name)==x['sha256']
assert sha(OUT/'predictions/mechanical-transfer-r001.json') == '5239371537f3699d2e6a2b0bdd52e7605ddf2c9e11a822b8ada8ed436701f216'
manifest=json.loads((Q/'inputs/acquisition/manifest.json').read_text())
samples=pd.read_csv(OUT/'sample-design.tsv',sep='\t').set_index('sample')
panel=pd.read_csv(OUT/'panel-measurements.tsv',sep='\t')
coverage=pd.read_csv(OUT/'panel-coverage.tsv',sep='\t')
effects=pd.read_csv(OUT/'executed-contrasts.tsv',sep='\t')
primary=effects.loc[effects.variant.eq('primary')&effects.pseudocount.eq(.5)]
qc=json.loads((OUT/'measurement-qc.json').read_text())
all_effects=pd.read_csv(OUT/'full-feature-contrasts.tsv.gz',sep='\t',compression='gzip')
matrices={s:pd.read_csv(OUT/f'{s}-native-matrix.tsv.gz',sep='\t',index_col=0) for s in qc}
statuses={s:pd.read_csv(OUT/f'{s}-status-matrix.tsv.gz',sep='\t',index_col=0) for s in qc}
checks={'source_files':0,'source_numeric_values':0,'panel_values':0,'effect_rows':0,'full_feature_contrast_rows':0,'conditional_Welch_checks':0}
anomalies=[]
for item in manifest:
    f=W/item['path']
    assert sha(f)==item['blob']
    s=item['series']
    mat=matrices[s]
    if s=='GSE79115':
        df=pd.read_csv(f,compression='gzip',sep='\t',header=None,names=['id','x'],index_col=0)
        gsm=item['name'].split('_')[0]
        arr=df.loc[mat.index,'x']
        assert np.array_equal(arr.to_numpy(),mat[gsm].to_numpy())
        checks['source_numeric_values']+=len(arr)
    elif s=='GSE292211':
        df=pd.read_csv(f,compression='gzip',sep='\t',index_col=0)
        for gsm in mat:
            arr=df.loc[mat.index,samples.at[gsm,'native_column']]
            assert np.array_equal(arr.to_numpy(),mat[gsm].to_numpy())
            checks['source_numeric_values']+=len(arr)
    else:
        df=pd.read_csv(f,compression='gzip',sep='\t',keep_default_na=False)
        df.index=df.tracking_id+'|'+df.locus
        gsm=item['name'].split('_')[0]
        assert df.index.is_unique
        assert np.array_equal(df.loc[mat.index,'FPKM'].to_numpy(),mat[gsm].to_numpy())
        assert df.loc[mat.index,'FPKM_status'].equals(statuses[s][gsm].rename('FPKM_status'))
        checks['source_numeric_values']+=len(df)
        outside=(df.FPKM<df.FPKM_conf_lo)|(df.FPKM>df.FPKM_conf_hi)
        anomalies.append({'sample':gsm,'series':s,'point_outside_source_interval':int(outside.sum()),'PMP22_outside':bool(outside.loc[df.gene_short_name.str.upper().eq('PMP22')].any()),'interpretation':'native FPKM interval columns not treated as biological confidence intervals; point values preserved'})
    checks['source_files']+=1
for row in panel.itertuples(index=False):
    assert row.native==matrices[row.series].at[row.feature_id,row.sample]
    assert row.status==statuses[row.series].at[row.feature_id,row.sample]
    if row.status in ['OK','measured_count']:
        assert np.isclose(row.normalized,row.native/samples.at[row.sample,'size_factor'],rtol=1e-12)
    else:
        assert pd.isna(row.normalized)
    checks['panel_values']+=1
assert coverage.n_matches.eq(1).all()

for s, mat in matrices.items():
    if qc[s]['counts']:
        good=mat.loc[(mat>0).all(axis=1)]
        logs=np.log(good.to_numpy())
        geo=np.exp(np.mean(logs,axis=1))
        sf=np.median(good.to_numpy()/geo[:,None],axis=0)
        sf/=np.exp(np.mean(np.log(sf)))
        assert np.allclose(sf,samples.loc[mat.columns,'size_factor'],rtol=1e-12)
        variants={'primary':mat/sf,'CPM':mat/mat.sum()*1e6}
    else:
        variants={'primary':mat.where(statuses[s].eq('OK'))}
    for name, sub in all_effects.loc[all_effects.series.eq(s)].groupby('contrast'):
        example=primary.loc[primary.series.eq(s)&primary.contrast.eq(name)].iloc[0]
        a=example.treatment_samples.split(';')
        b=example.control_samples.split(';')
        logs=np.log2(variants['primary']+.5)
        val=(logs[a].mean(axis=1,skipna=False)-logs[b].mean(axis=1,skipna=False)).reindex(sub.feature_id)
        assert np.allclose(val,sub.effect_log2,equal_nan=True,atol=1e-12,rtol=1e-12)
        checks['full_feature_contrast_rows']+=len(sub)
    for row in effects.loc[effects.series.eq(s)].itertuples(index=False):
        a=row.treatment_samples.split(';')
        b=row.control_samples.split(';')
        ids=row.source_features.split(';')
        log=np.log2(variants[row.variant].loc[ids]+row.pseudocount)
        if row.endpoint.startswith('PMP22_minus_'):
            score=log.iloc[0]-log.iloc[1:].mean(axis=0,skipna=False)
        else:
            score=log.mean(axis=0,skipna=False)
        val=score[a].mean(skipna=False)-score[b].mean(skipna=False)
        assert np.isclose(val,row.effect_log2,equal_nan=True,atol=1e-11)
        if np.isfinite(val):
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                result=stats.ttest_ind(score[a],score[b],equal_var=False)
            if np.isfinite(row.welch_p):
                assert np.isclose(result.pvalue,row.welch_p,atol=1e-12)
                ci=result.confidence_interval()
                assert np.allclose([ci.low,ci.high],[row.ci95_low,row.ci95_high],rtol=1e-10,atol=1e-12)
                checks['conditional_Welch_checks']+=1
        checks['effect_rows']+=1

# Exact family named in the lock: three target environmental tests.
env_names=['WT_40_minus_1kPa','compression4h_vs_uncompressed','pulse_recovery_vs_uncompressed']
env=primary.loc[primary.contrast.isin(env_names)&primary.endpoint.eq('PMP22')].copy()
assert len(env)==3
order=np.argsort(env.welch_p.to_numpy())
padj=np.empty(3)
padj[order]=np.minimum(1,np.maximum.accumulate((3-np.arange(3))*env.welch_p.to_numpy()[order]))
env['Holm_p_environmental_family3']=padj
lock=[]
for name,claim,threshold in [(env_names[0],'stiffness-negative-transfer',-.15),(env_names[1],'compression-negative-transfer',-.25)]:
    row=env.loc[env.contrast.eq(name)].iloc[0]
    tests=effects.loc[effects.contrast.eq(name)&effects.endpoint.eq('PMP22')]
    eligible=bool(row.baseline_eligible and row.statuses_valid)
    if not eligible:
        outcome='untestable'
    elif row.effect_log2>threshold:
        outcome='failed_magnitude_or_direction'
    elif row.ci95_high<0 and row.loo_max<0 and tests.effect_log2.lt(0).all():
        outcome='supported_in_declared_context_under_conditional_interval_model'
    else:
        outcome='inconclusive_reproducibility'
    lock.append({'candidate_id':claim,'outcome':outcome,'prediction_threshold':threshold,'primary':finite_records(pd.DataFrame([row]))[0],'effect_range_all_normalizations_pseudocounts':[float(tests.effect_log2.min()),float(tests.effect_log2.max())],'interpretation':'cross-context transfer, not independent-donor Schwann stiffness replication'})
genetic=primary.loc[primary.contrast.isin(['P3_partial_loss_vs_control','P5_partial_loss_vs_control'])&primary.endpoint.isin(['PMP22','PMP22_minus_EGR2','PMP22_minus_SOX10'])]
assert len(genetic)==6
elig=genetic.baseline_eligible.all() and genetic.statuses_valid.all()
sens=effects.loc[effects.contrast.isin(genetic.contrast)&effects.endpoint.isin(genetic.endpoint)]
outcome='untestable' if not elig else ('supported_quantitative_RNA_discordance_not_activity' if genetic.effect_log2.le(-.5).all() and sens.loo_max.lt(0).all() else 'failed')
lock.append({'candidate_id':'yaptaz-rna-discordance','outcome':outcome,'prior_exposure':'directional genetic results known before lock; quantitative comparison new','primary':finite_records(genetic),'scope':'two independent studies, different ages/drivers/pools; P5 n2 descriptive'})

# Published scaled-count workbook: independent processing comparison, same biological libraries.
wb=json.loads((OUT/'author-workbook-inspection.json').read_text())
assert len(wb['sheets'])==1 and wb['sheets'][0]['formula_cells_not_evaluated']==0
sheet=wb['sheets'][0]
header={x['cell'].rstrip('0123456789'):x['value'] for x in sheet['header_rows'][0]}
authrows=[]
for row in sheet['selected_rows']:
    d={header[x['cell'].rstrip('0123456789')]:x['value'] for x in row}
    gene=d['GeneSymbol']
    d.pop('ID')
    d.pop('GeneSymbol')
    a=[float(v) for k,v in d.items() if '__Comp_4h' in k]
    b=[float(v) for k,v in d.items() if '__Uncomp' in k]
    pulse=[float(v) for k,v in d.items() if '__Comp_5min' in k]
    assert len(a)==len(b)==len(pulse)==3
    authrows.append({'gene':gene,'compression4h_log2':float(np.log2(np.array(a)+.5).mean()-np.log2(np.array(b)+.5).mean()),'pulse_recovery_log2':float(np.log2(np.array(pulse)+.5).mean()-np.log2(np.array(b)+.5).mean()),'source_feature_universe_rows_excluding_header':sheet['rows']-1,'independent_biology':False})

summary={'question':'q_4f573ee10eee421b','prediction_lock_sha256':sha(OUT/'predictions/mechanical-transfer-r001.json'),'source_counts':qc,'executed_contrasts':primary[['series','contrast']].drop_duplicates().to_dict('records'),'locked_outcomes':lock,'environmental_PMP22':finite_records(env),'author_scaled_counts_crosscheck':authrows,'conditional_inference_warning':'Welch distributional and independence assumptions; exact permutation3+3 minimum0.1,2+2 minimum1/3; no donor or activity equivalence claims','myelin7_P5_failure':finite_records(panel.loc[panel.series.eq('GSE94990')&~panel.status.isin(['OK','measured_count'])]),'native_FPKM_anomalies':anomalies,'key_endpoint_effects':finite_records(primary.loc[primary.endpoint.isin(['PMP22','EGR2','SOX10','JUN','MKI67','CTGF','CYR61','ITGA6','DAG1','myelin7','PMP22_minus_EGR2','PMP22_minus_SOX10','PMP22_minus_myelin7'])]),'raw_feature_measurements_verified':checks['source_numeric_values']}
(OUT/'result-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
validation={'passed':True,'checks':checks,'source_receipt':sha(OUT/'analysis-execution-r003.json'),'producer_hash':r['code_sha256'],'finite_JSON':True,'all_panel_gene_mappings_unique':True,'source_values_retained':True,'failed_status_not_zero':True,'author_workbook_no_formulas_or_macros':True}
(OUT/'validation.json').write_text(json.dumps(validation,indent=2,allow_nan=False)+'\n')
env.to_csv(OUT/'environmental-PMP22-summary.tsv',sep='\t',index=False)
pd.DataFrame(authrows).to_csv(OUT/'author-normalization-crosscheck.tsv',sep='\t',index=False)
print(json.dumps(validation,indent=2))
print('PREDICTIONS',[(x['candidate_id'],x['outcome']) for x in lock])
print(env[['contrast','effect_log2','Holm_p_environmental_family3']].to_string(index=False))
print('AUTHOR',authrows)
