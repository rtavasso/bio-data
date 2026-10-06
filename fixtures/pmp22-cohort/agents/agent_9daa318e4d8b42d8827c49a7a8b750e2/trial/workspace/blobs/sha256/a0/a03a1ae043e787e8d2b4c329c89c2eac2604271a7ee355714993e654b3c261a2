from pathlib import Path
import json
import pandas as pd,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/iteration';plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axs=plt.subplots(2,2,figsize=(13,9),layout='constrained')
r=pd.read_csv(O/'isr-panel-effects.tsv',sep='\t');r=r[(r.gene=='Pmp22')&(r.method=='median_ratio')];ax=axs[0,0]
cs=['acute','chronic_vs_control','PERKi'];labels=['1h / untreated','16h / untreated','PERKi / 16h']
for i,(endpoint,color) in enumerate([('cytosolic','#2878b5'),('polysome','#bd4d2a')]):
 d=r[r.endpoint==endpoint].set_index('contrast').loc[cs];x=np.arange(3)+(i-.5)*.17;ax.errorbar(x,d.log2_effect,yerr=np.vstack([d.log2_effect-d.ci_low,d.ci_high-d.log2_effect]),fmt='o',color=color,label=endpoint,capsize=3)
ax.set(xticks=np.arange(3),xticklabels=labels,ylabel='Pmp22 log2 change',title='A  Matched fractions: chronic suppression and PERKi reversal');ax.axhline(0,color='gray',lw=.8);ax.legend();ax.text(.02,.02,'GSE90070 MEF; 400 nM Tg; 4 labelled replicates\nIntervals describe replicate variation, not donor populations',transform=ax.transAxes,fontsize=8)
r=pd.read_csv(O/'footprint-pmp22-effects.tsv',sep='\t');r=r[r.method=='TPM'];ax=axs[0,1];ax.plot(r.hour,r.WT_log2_effect,'o-',color='#7447a4',label='MEF WT: 1 µM Tg');ax.plot(r.hour,r.KO_log2_effect,'s--',color='#8b8b8b',label='MEF PERK KO: 1 µM Tg');s=json.loads((O/'followup-summary.json').read_text())['Gonen_NIH3T3_source_values'];ax.plot([2,7],np.log2(np.array([s['NIH3T3_Tg2hr'],s['NIH3T3_Tg7hr']])/s['NIH3T3_Cont']),'^-',color='#1c998e',label='NIH3T3: 200 nM Tg');ax.axhline(0,color='gray',lw=.8);ax.set(title='B  Footprints change in opposite directions across contexts',xlabel='Hours after Tg',ylabel='Pmp22 log2 TPM / own control');ax.legend(fontsize=8);ax.text(.02,.02,'GSE118660; one library per condition; no matched RNA\nNIH3T3 late point: GEO/methods 7h, Table S5B labels 8h',transform=ax.transAxes,fontsize=8)
r=pd.read_csv(O/'array-stratified-Pmp22-effects.tsv',sep='\t');r=r[r.method=='deposited_log2'];ax=axs[1,0];cs=['WT_ATF4_subset','WT_PERK_subset','PERKKO','eIF2alpha_AA']
for i,(probe,color) in enumerate([('A_55_P2040168','#2878b5'),('A_55_P2040170','#bd4d2a')]):
 d=r[r.probe==probe].set_index('contrast').loc[cs];ax.plot(np.arange(4)+(i-.5)*.15,d.log2_effect,'o',color=color,label=probe)
ax.axhline(0,color='gray',lw=.8);ax.set(xticks=np.arange(4),xticklabels=['ATF4WT files','PERKWT files','PERK KO','eIF2α-AA'],ylabel='Pmp22 deposited log2 response',title='C  Source control subsets change the genetic comparison');ax.legend(fontsize=8);ax.text(.02,.02,'GSE49598: post hoc strata, 2 labelled replicates/group\nMixed WT sources and one KO control time ambiguity',transform=ax.transAxes,fontsize=8)
r=pd.read_csv(O/'granule-panel-relative-effects.tsv',sep='\t');r=r[r.stress=='THAP'];ax=axs[1,1];genes=['Pmp22','Xiap','Ago3','Creb1'];colors=['#2878b5','#bd4d2a','#1c998e']
for rep in [1,2,3]:
 d=r[r.replicate==rep].set_index('gene').reindex(genes);ax.plot(np.arange(4)+(rep-2)*.13,d.median_centered_change,'o',color=colors[rep-1],label='Rep '+str(rep))
ax.axhline(0,color='gray',lw=.8);ax.set(xticks=np.arange(4),xticklabels=genes,ylabel='Relative RG / cytoplasm log2 change',title='D  Pmp22 relative granule response is inconsistent');ax.legend(fontsize=8);ax.text(.02,.02,'GSE90869 NIH3T3; centered on eligible median gene\nMissing spike calibration prevents absolute recruitment inference',transform=ax.transAxes,fontsize=8)
fig.suptitle('PMP22 regulation depends on endpoint, context and source design',fontsize=16)
fig.savefig(O/'PMP22-iteration.png',dpi=180);fig.savefig(O/'PMP22-iteration.pdf')
