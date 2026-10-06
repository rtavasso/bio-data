import pathlib,json,numpy as np,pandas as pd
from read_tdf import TDF
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
q=pathlib.Path(__file__).resolve().parents[1];d=q/'inputs/continuation';o=q/'outputs'
chrom='chr11';start=63095000;end=63175000;tracks={};metadata={}
for sid in ['GSM3484775','GSM3484776']:
 t=TDF(d/(sid+'.tdf'));a,ty,width,tiles=t.dataset('/chr11/raw');parts=[]
 for i in range(max(0,int(start//width)),min(len(tiles),int(end//width)+1)):
  z=t.tile(*tiles[i])
  if z is not None:
   aa,bb,vv,typ=z;sel=(bb>start)&(aa<end)&(bb>aa);parts.append(np.column_stack([aa[sel],bb[sel],vv[0,sel]]))
 arr=np.unique(np.concatenate(parts),axis=0);tracks[sid]=arr
 pd.DataFrame(arr,columns=['start','end','signal']).assign(chrom=chrom).to_csv(o/(sid+'-Pmp22-signal.tsv'),sep='\t',index=False)
 metadata[sid]={'track_line':t.track_line,'raw_dataset_width':width,'selected_intervals':len(arr)}
# Segment on union breakpoints so all paired measurements refer to identical genomic bases.
bounds=np.unique(np.concatenate([np.array([start,end]),*[a[:,:2].ravel() for a in tracks.values()]]));bounds=bounds[(bounds>=start)&(bounds<=end)];aa=bounds[:-1];bb=bounds[1:];mid=(aa+bb)/2;vals={}
for sid,arr in tracks.items():
 idx=np.searchsorted(arr[:,0],mid,side='right')-1;valid=(idx>=0)&(mid<arr[np.maximum(idx,0),1]);vals[sid]=np.where(valid,arr[np.maximum(idx,0),2],np.nan)
common=np.isfinite(vals['GSM3484775'])&np.isfinite(vals['GSM3484776']);loci=pd.read_csv(o/'runx-atac-regulator-loci.tsv',sep='\t');loci=loci[loci.gene.str.startswith('Pmp22')];rows=[]
for row in loci.itertuples():
 w=np.maximum(0,np.minimum(bb,row.end)-np.maximum(aa,row.start));w=w*common;total=w.sum();means={sid:float((np.nan_to_num(v)*w).sum()/total) if total else None for sid,v in vals.items()};rows.append({'gene':row.gene,'start':row.start,'end':row.end,'transcripts':row.transcripts if isinstance(row.transcripts,str) else '', 'common_covered_bases':float(total),'common_coverage_fraction':float(total/(row.end-row.start)),**means,'log2_tKO_over_sKO_common_bases':float(np.log2(means['GSM3484776']/means['GSM3484775'])) if total else None})
pd.DataFrame(rows).to_csv(o/'runx-atac-Pmp22-common-bases.tsv',sep='\t',index=False)
fig,axs=plt.subplots(2,1,figsize=(11,6),sharex=True)
for ax,(sid,arr),color in zip(axs,tracks.items(),['#3977a8','#bc4c38']):
 bins=np.arange(start,end+1,250);yy=[]
 for lo,hi in zip(bins[:-1],bins[1:]):
  w=np.maximum(0,np.minimum(arr[:,1],hi)-np.maximum(arr[:,0],lo));yy.append(float((w*arr[:,2]).sum()/w.sum()) if w.sum()>=.9*(hi-lo) else np.nan)
 ax.plot((bins[:-1]+125)/1e6,yy,color=color,lw=1);ax.axvspan(63114879/1e6,63115495/1e6,color='gold',alpha=.35,label='reported RUNX-target region');ax.set_ylabel('Signal / 10M tags');ax.set_title(sid+(' Nf1 sKO' if sid.endswith('775') else ' Nf1/Runx1/Runx3 tKO'))
 for r in loci.itertuples():
  if r.gene=='Pmp22':ax.axvspan(r.start/1e6,r.end/1e6,color='gray',alpha=.1)
axs[0].legend(fontsize=8);axs[1].set_xlabel('mm10 chr11 (Mb); 250-bp bins with ≥90% observed coverage');fig.suptitle('Independent RUNX experiment: one library/genotype; no causal DA test',fontsize=11);fig.tight_layout();fig.savefig(o/'runx-Pmp22-accessibility.png',dpi=170);plt.close(fig)
result={'locus':f'{chrom}:{start}-{end}','metadata':metadata,'common_base_promoter_estimates':rows,'validation':'All paired locus means integrated on identical common-covered base segments. Unrepresented bases excluded, never treated as measured zero. Zero-width TDF bed intervals contribute no bases.','context':'One library/genotype, distinct DRG/tumor annotations; not independent evidence about Egr2-AS. Lower promoter signal does not contradict RNA induction causally because confounded contexts and endpoints.','broad_context':'All-promoter mean-signal log2 median from >=90% coverage windows is about -0.45; local reductions are not uniquely PMP22-specific.'}
(o/'runx-locus-summary.json').write_text(json.dumps(result,indent=2,allow_nan=False));print(json.dumps(result,indent=2))
