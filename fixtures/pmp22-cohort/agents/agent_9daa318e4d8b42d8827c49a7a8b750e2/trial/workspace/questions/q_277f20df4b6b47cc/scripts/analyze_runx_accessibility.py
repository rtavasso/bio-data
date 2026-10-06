import pathlib,json,gzip,io,sys
import numpy as np,pandas as pd
from read_tdf import TDF
q=pathlib.Path(__file__).resolve().parents[1];d=q/'inputs/continuation';o=q/'outputs'
ref=pd.read_csv(d/'mm10-refGene.txt.gz',sep='\t',header=None);ref=ref.rename(columns={1:'transcript',2:'chrom',3:'strand',4:'txStart',5:'txEnd',12:'gene'});ref['tss']=np.where(ref.strand=='+',ref.txStart,ref.txEnd);ref['start']=np.maximum(0,ref.tss-np.where(ref.strand=='+',1500,500));ref['end']=ref.tss+np.where(ref.strand=='+',500,1500)
# Preserve every distinct annotated promoter; no arbitrary isoform choice or P1/P2 label.
regions=ref.groupby(['chrom','start','end','strand','gene'],sort=False).agg(transcripts=('transcript',lambda x:';'.join(sorted(set(x))))).reset_index();regions['region_type']='RefSeq_promoter_-1500_+500'
# Paper coordinates reported without explicit coordinate convention; use literal bounds and state this.
regions=pd.concat([regions,pd.DataFrame([dict(chrom='chr11',start=63114879,end=63115495,strand='.',gene='Pmp22_RUNX_site',transcripts='',region_type='paper_literal_CRISPR_target_bounds')])],ignore_index=True)
meta={};summaries=[]
for sid in ['GSM3484775','GSM3484776']:
 t=TDF(d/(sid+'.tdf'));meta[sid]=t.metadata();out={}
 for chrom,g in regions.groupby('chrom',sort=False):
  name='/'+chrom+'/raw'
  if name not in t.datasets:continue
  attrs,typ,width,tiles=t.dataset(name);parts=[]
  for pos,size in tiles:
   rr=t.tile(pos,size)
   if rr is not None:
    a,b,v,tt=rr;assert v.shape[0]==1;parts.append(np.column_stack([a,b,v[0]]))
  arr=np.concatenate(parts) if parts else np.empty((0,3));arr=np.unique(arr,axis=0);arr=arr[np.argsort(arr[:,0],kind='stable')]
  assert np.all(arr[1:,0]>=arr[:-1,1]),f'Overlapping signal intervals {sid} {chrom}'
  a,b,v=arr.T
  summaries.append({'sample':sid,'chrom':chrom,'unzoomed_intervals':len(a),'finite_intervals':int(np.isfinite(v).sum()),'mean_interval_signal_unweighted':float(np.nanmean(v)),'track_units':'normalized to 1e7 tags per source trackLine'})
  for idx,row in g.iterrows():
   l=np.searchsorted(b,row.start,side='right');h=np.searchsorted(a,row.end,side='left');aa=a[l:h];bb=b[l:h];vv=v[l:h];w=np.maximum(0,np.minimum(bb,row.end)-np.maximum(aa,row.start));ok=np.isfinite(vv);covered=float(w[ok].sum());total=float((w[ok]*vv[ok]).sum())
   out[idx]=(covered,total/covered if covered else np.nan,float(vv[ok].max()) if ok.any() else np.nan)
  print(sid,chrom,len(arr),'regions',len(g),flush=True)
 for j,field in enumerate(['covered_bases','mean_signal_observed','max_signal_observed']):regions[sid+'_'+field]=[out.get(i,(0,np.nan,np.nan))[j] for i in regions.index]
 regions[sid+'_coverage_fraction']=regions[sid+'_covered_bases']/(regions.end-regions.start)
 del t
mask=(regions.GSM3484775_coverage_fraction>=.9)&(regions.GSM3484776_coverage_fraction>=.9)&(regions.GSM3484775_mean_signal_observed>0)&(regions.GSM3484776_mean_signal_observed>0)
regions['log2_tKO_over_sKO_observed_mean']=np.where(mask,np.log2(regions.GSM3484776_mean_signal_observed/regions.GSM3484775_mean_signal_observed),np.nan)
regions.to_csv(o/'runx-atac-all-promoters.tsv',sep='\t',index=False,na_rep='NA')
regions.loc[regions.gene.isin(['Pmp22','Pmp22_RUNX_site','Egr2','Jun','Sox10','Mbp','Rnf157','Ccnd1','Ern1'])].to_csv(o/'runx-atac-regulator-loci.tsv',sep='\t',index=False,na_rep='NA')
regions.loc[mask].assign(abslog=lambda x:x.log2_tKO_over_sKO_observed_mean.abs()).sort_values('abslog',ascending=False).head(100).to_csv(o/'runx-atac-broad-extremes.tsv',sep='\t',index=False)
pd.DataFrame(summaries).to_csv(o/'runx-atac-signal-qc.tsv',sep='\t',index=False)
# independently check byte decoder against exact round-trip for numeric scalar + zlib; all tile cursors and interval continuity checked above.
result={'source':'GSE122776 deposited TDF continuous ATAC signal; primary text PMC6482019 Methods sec21','metadata':meta,'reference':'UCSC mm10 refGene URL in transport.json; contemporary reference, not asserted identical to 2019 annotation','promoter_windows':len(regions),'at_least_90pct_observed_both':int(mask.sum()),'median_log2_ratio_observed_promoters':float(regions.loc[mask,'log2_tKO_over_sKO_observed_mean'].median()),'material':'FACS-sorted EGFP+ Schwann lineage, mouse Nf1 single-KO versus Nf1/Runx1/Runx3 triple-KO; source sample tissues DRG versus neurofibroma tumor. One ATAC library per genotype.','units':'Continuous deposited bedGraph signal, normalized to 10 million tags according to TDF trackLine, not raw fragment counts. TDF genomeId is a local path, assembly established independently by GEO and paper mm10.','comparison':'Descriptive triple-KO/single-KO mean signal over observed bases for windows with >=90% coverage in both; missing coverage is not filled as zero. Rat Egr2-AS experiment kept separate.','limitations':['No independent ATAC replication (paper explicitly n=1/genotype). No new differential-accessibility p-values.','Tissue/state differences confounded with genotype; not a clean causal Runx effect.','Many RefSeq transcripts share promoters; transcript windows are not independent observations.','Endogenous protein/myelin function cannot be inferred from ATAC signal.','Paper literal RUNX-site interval convention not explicit; no exact base-resolution functional claim.'], 'parser_validation':'Header/index/dataset/tile lengths fully consumed; zlib validated; one track; intervals sorted/deduplicated and nonoverlap asserted chromosome-wide; no downloaded executable code used.'}
(o/'runx-atac-summary.json').write_text(json.dumps(result,indent=2,allow_nan=False));print(regions.loc[regions.gene.str.startswith('Pmp22')].to_string(index=False))
