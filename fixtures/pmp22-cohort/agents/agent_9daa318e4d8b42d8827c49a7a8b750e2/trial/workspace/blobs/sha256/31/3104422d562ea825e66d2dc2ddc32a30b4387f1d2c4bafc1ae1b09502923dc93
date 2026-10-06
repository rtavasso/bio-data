from pathlib import Path
import pandas as pd,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/specific';s=pd.read_csv(O/'discovery-samples.tsv',sep='\t');d=pd.read_csv(O/'discovery-selected.tsv',sep='\t');v=pd.read_csv(O/'validation-primary-results.tsv',sep='\t');a=pd.read_csv(O/'alternate-myelin-targets.tsv',sep='\t')
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False});fig,axs=plt.subplots(1,3,figsize=(14,4.5));ax=axs[0]
for day,g in s.groupby('day'):ax.scatter(g.myelin_score,g.Pmp22_log2CPM,label=f'day {day}',s=45)
b=np.polyfit(s.myelin_score,s.Pmp22_log2CPM,1);x=np.linspace(s.myelin_score.min(),s.myelin_score.max(),80);ax.plot(x,np.polyval(b,x),color='gray',lw=1);ax.set(xlabel='Seven-gene myelin score (log2 CPM)',ylabel='Pmp22 (log2 CPM)',title='Discovery: most variation is shared\nR² = 0.981; 8 pooled preparations');ax.legend(frameon=False,fontsize=8)
ax=axs[1];pos=np.arange(3);ax.bar(pos-.18,d.partial_r,.36,label='Discovery',color='#3c6997');ax.bar(pos+.18,v.validation_partial_r,.36,label='Zeb2 validation',color='#bb684b');ax.axhline(0,color='gray',lw=.8);ax.set(xticks=pos,xticklabels=v.candidate,ylabel='Correlation after myelin adjustment',ylim=(-1.1,1.1),title='Conditional signs reverse\nFrozen primary test: none passed');ax.legend(frameon=False,fontsize=8)
ax=axs[2];names=['Observed','Myelin only']+v.candidate.tolist();vals=[v.delta_Pmp22.iloc[0],v.baseline_prediction.iloc[0]]+v.augmented_prediction.tolist();ax.barh(names,vals,color=['#333333','#999999']+['#bb684b']*3);ax.axvline(0,color='gray',lw=.8);ax.set(xlabel='Pmp22 KO − control (log2)',title='Independent Zeb2 deletion\n3 mice per group; P25 nerve');ax.invert_yaxis()
fig.text(.02,.01,'Exploratory gene selection used 1,119 annotated regulatory candidates. Rat injury → mouse perturbation; no causal or promoter-specific inference.',fontsize=9);fig.tight_layout(rect=(0,.045,1,1));fig.savefig(O/'PMP22-specificity.png',dpi=180);fig.savefig(O/'PMP22-specificity.pdf');plt.close(fig)
