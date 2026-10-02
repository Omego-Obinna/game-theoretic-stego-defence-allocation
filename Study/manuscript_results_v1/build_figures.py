"""Publication figures from saved estimates only; no simulation or fitting.

Run with the existing scientific Python environment. Source files are read-only.
"""
from pathlib import Path
import os
import json
import hashlib
import itertools
import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
os.environ.setdefault('MPLCONFIGDIR', str(HERE / 'tmp' / 'matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D

OUT = HERE / 'output' / 'pdf'
PNG = HERE / 'output' / 'png'
OUT.mkdir(parents=True, exist_ok=True)
PNG.mkdir(parents=True, exist_ok=True)
SOURCES = {
    'fit': BASE / 'game_analysis_v1/game_results.json',
    'validation': BASE / 'fresh_seed_validation_v1/evaluated_strategies.json',
    'sensitivity': BASE / 'transport_sensitivity_v1/evaluated_strategies.json',
}
DATA = {k: json.loads(p.read_text()) for k, p in SOURCES.items()}
CAPS = [0, .2, .5, .7, .85, 1]
PRIMARY = 'transport_completion'
SECONDARY = 'recorded_extraction_weighted'
M = 'restricted_minimax'
B = 'balanced_equal_repetition_probability'
F = 'best_fixed_maximin'
G = 'greedy_marginal_per_byte'
S = 'shapley_knapsack'
E = 'equal_expected_channel_bytes'
U = 'uniform_feasible'
N = 'no_extra'
ORDER = [M, B, F, G, S, E, U, N]
NAMES = {M:'Restricted minimax', B:'Balanced repetition', F:'Best fixed maximin',
         G:'Greedy gain per byte', S:'Shapley-guided', E:'Equal channel bytes',
         U:'Uniform feasible', N:'No extra protection'}
SHORT = {M:'M', B:'B', F:'F', G:'G', S:'S', E:'E', U:'U', N:'N'}
# Okabe-Ito-derived palette, supplemented by shapes and direct labels.
COLORS = {M:'#0072B2', B:'#D55E00', F:'#009E73', G:'#8F6500', S:'#CC79A7',
          E:'#4C9BB0', U:'#555555', N:'#111111'}
MARKERS = {M:'o', B:'s', F:'^', G:'D', S:'v', E:'P', U:'X', N:'+'}
plt.rcParams.update({
    'font.family':'serif', 'font.serif':['Times New Roman', 'DejaVu Serif'],
    'font.size':9, 'axes.titlesize':10, 'axes.labelsize':9,
    'xtick.labelsize':8, 'ytick.labelsize':8, 'legend.fontsize':8,
    'pdf.fonttype':42, 'ps.fonttype':42, 'mathtext.fontset':'stix',
    'axes.spines.top':False, 'axes.spines.right':False,
    'axes.linewidth':.6, 'xtick.major.width':.6, 'ytick.major.width':.6,
    'savefig.facecolor':'white', 'figure.facecolor':'white',
})

def cell(stage, cap, pricing=None, payload=.2, env='E2', beta=.05, endpoint=PRIMARY):
    rows = [r for r in DATA[stage] if r['payload_bpp']==payload and
            r['environment']==env and r['beta']==beta and
            r['extra_byte_cap']==cap and r['endpoint']==endpoint and
            (pricing is None or r.get('pricing')==pricing)]
    assert len(rows)==1, (stage,cap,pricing,payload,env,beta,endpoint,len(rows))
    return rows[0]

def save(fig, stem):
    vectorise(fig)
    fig.savefig(OUT / (stem+'.pdf'), metadata={'Creator':'Matplotlib; saved-result reanalysis',
                'Title':stem, 'Author':'Manuscript figure preparation'})
    fig.savefig(PNG / (stem+'.png'), dpi=400)
    plt.close(fig)

def vectorise(fig):
    for ax in fig.axes:
        for collection in ax.collections:
            collection.set_rasterized(False)

def clean(ax, axis='x'):
    ax.set_axisbelow(True)
    ax.grid(axis=axis, color='#dddddd', lw=.45)

def pct(v): return 100*np.asarray(v)

def heat(ax, values, **kwargs):
    """Vector rectangles, not an embedded raster heatmap."""
    nr,nc=values.shape
    artist=ax.pcolormesh(np.arange(nc+1)-.5,np.arange(nr+1)-.5,values,
                        shading='flat',rasterized=False,**kwargs)
    ax.set_xlim(-.5,nc-.5);ax.set_ylim(nr-.5,-.5)
    return artist

def forest():
    fig, axs = plt.subplots(1,2,figsize=(7.15,3.05),sharey=True)
    fig.subplots_adjust(left=.225,right=.915,bottom=.18,top=.88,wspace=.40)
    for j,(ax,cap) in enumerate(zip(axs,[.7,.85])):
        c=cell('validation',cap)
        for y,n in enumerate(ORDER):
            s=c['strategies'][n]; mean=100*s['worst_of_attack_means']
            lo,hi=pct(s['descriptive_bootstrap_interval'])
            ax.errorbar(mean,y,xerr=[[mean-lo],[hi-mean]],fmt=MARKERS[n],
                        ms=4.4,color=COLORS[n],lw=1.1,capsize=2.3)
            ax.text(1.025,y,f'{mean:.3f}',transform=ax.get_yaxis_transform(),va='center',ha='left',fontsize=8)
        ax.set_title(f'({chr(97+j)})  {cap:.0%} extra-byte cap',loc='left')
        ax.set_xlim(79.5,88.8); ax.set_xticks([80,82,84,86,88])
        ax.set_ylim(7.6,-.8); ax.set_yticks(range(8),[NAMES[n] for n in ORDER])
        ax.tick_params(axis='y',length=0); clean(ax)
        ax.set_xlabel('Transport completion (%)')
    fig.text(.225,.02,'0.2 bpp  |  E2  |  attack fraction 5%  |  original five object-priced rules',fontsize=8)
    save(fig,'results_policy_comparison')

def cost():
    fig,axs=plt.subplots(1,2,figsize=(7.15,3.25),sharey=True)
    fig.subplots_adjust(left=.085,right=.985,bottom=.27,top=.88,wspace=.13)
    for j,(ax,cap) in enumerate(zip(axs,[.7,.85])):
        c=cell('validation',cap)
        for n in reversed(ORDER):
            s=c['strategies'][n]
            ax.plot(100*s['expected_extra_fraction_mean'],100*s['worst_of_attack_means'],
                    MARKERS[n],color=COLORS[n],ms=5,markerfacecolor='none' if n==B else COLORS[n],
                    markeredgewidth=1.0,zorder=3)
        groups = [(N,'N',(5,9)),(U,'U',(-2,-15)),(E,'E',(5,7)),
                  (M,'M / B',(0,15))]
        groups += [(F,'F / G / S',(0,-15))] if cap==.7 else [(G,'G',(0,10)),(F,'F / S',(-2,-15))]
        for n,lab,offset in groups:
            s=c['strategies'][n]; xy=(100*s['expected_extra_fraction_mean'],100*s['worst_of_attack_means'])
            ax.annotate(lab,xy,xytext=offset,textcoords='offset points',fontsize=8,
                        ha='center' if n!=N else 'left',va='center',
                        arrowprops={'arrowstyle':'-','color':'#888888','lw':.6} if n==M else None)
        ax.axvline(cap*100,ls='--',lw=.8,color='#777777')
        ax.text(cap*100-1,88.9,'Hard cap',ha='right',va='top',fontsize=7.5)
        ax.set(xlim=(-2,91),ylim=(79.7,89.1),xticks=[0,20,40,60,80],yticks=[80,82,84,86,88])
        ax.set_title(f'({chr(97+j)})  {cap:.0%} extra-byte cap',loc='left')
        ax.set_xlabel('Actual expected additional bytes (%)'); clean(ax,'both')
    axs[0].set_ylabel('Worst-of-attack-means completion (%)')
    fig.text(.085,.09,'M: minimax   B: balanced   F: best fixed   G: greedy   S: Shapley-guided',fontsize=8)
    fig.text(.085,.035,'E: equal channel bytes   U: uniform feasible   N: no extra protection',fontsize=8)
    save(fig,'results_cost_reliability')

def cooperative():
    fig,(a,b)=plt.subplots(1,2,figsize=(7.15,2.85),gridspec_kw={'width_ratios':[1.1,1]})
    fig.subplots_adjust(left=.085,right=.9,bottom=.22,top=.85,wspace=.55)
    for j,cap in enumerate([.7,.85]):
        v=pct(cell('fit',cap)['cooperative']['shapley'])
        bars=a.bar(np.arange(3)+(j-.5)*.32,v,width=.32,color=['#0072B2','#D55E00'][j],
                   label=f'{cap:.0%} cap',hatch=['','//'][j],edgecolor='white',linewidth=.4)
        for x,y in zip(np.arange(3)+(j-.5)*.32,v): a.text(x,y+.07,f'{y:.3f}',ha='center',fontsize=7.5)
    a.set_xticks(range(3),[r'$C_1$',r'$C_2$',r'$C_3$'])
    a.set_ylabel('Shapley contribution (pp)');a.set_ylim(0,3.55)
    a.set_title('(a)  Capability attribution',loc='left');a.legend(frameon=False,ncol=2,loc='upper left',fontsize=7.5)
    clean(a,'y')
    vals=np.array([[cell('fit',cap)['cooperative']['interaction_dividends'][str(mask)]*100
                    for cap in [.7,.85]] for mask in [3,5,6,7]])
    im=heat(b,vals,cmap='RdBu',norm=TwoSlopeNorm(vmin=-4,vcenter=0,vmax=4))
    b.set_xticks([0,1],['70% cap','85% cap'])
    b.set_yticks(range(4),[r'$d(\{1,2\})$',r'$d(\{1,3\})$',r'$d(\{2,3\})$',r'$d(\{1,2,3\})$'])
    b.tick_params(length=0); b.set_title('(b)  Interaction dividends',loc='left')
    for (y,x),v in np.ndenumerate(vals):
        b.text(x,y,('0.000' if abs(v)<.0005 else f'{v:+.3f}'),ha='center',va='center',
               fontsize=9,color='white' if abs(v)>2.5 else '#111111')
    cb=fig.colorbar(im,ax=b,fraction=.08,pad=.08);cb.set_label('Dividend (pp)');cb.set_ticks([-4,-2,0,2,4])
    fig.text(.085,.04,'Development-fitted worths; 0.2 bpp, E2, attack fraction 5%. No refitting or validation attribution.',fontsize=8)
    save(fig,'results_cooperative_attribution')

def sensitivity():
    chosen=[M,B,E,G]
    fig,axs=plt.subplots(2,2,figsize=(7.15,4.0),sharex=True,sharey=True)
    fig.subplots_adjust(left=.205,right=.98,bottom=.30,top=.92,wspace=.10,hspace=.37)
    for r,pricing in enumerate(['objects','bytes']):
        for j,cap in enumerate([.7,.85]):
            ax=axs[r,j]; c=cell('sensitivity',cap,pricing)
            for y,n in enumerate(chosen):
                s=c['strategies'][n]; color=COLORS[n]
                old,aug,matched,adapt=pct([s['legacy_catalogue_worst'],s['augmented_catalogue_worst'],
                                        s['matched_fixed_reservation_worst'],s['adaptive_only']])
                ax.plot([old,aug],[y-.11]*2,color=color,lw=1.5)
                ax.plot(old,y-.11,'o',mfc='white',mec=color,ms=4.5,zorder=4)
                ax.plot(aug,y-.11,'D',mfc=color,mec=color,ms=3.5,zorder=5)
                ax.plot([matched,adapt],[y+.13]*2,color='#666666',ls='--',lw=.9)
                ax.plot(matched,y+.13,'s',mfc='white',mec='#666666',ms=3.8,zorder=4)
                ax.plot(adapt,y+.13,'x',color='#333333',ms=4,zorder=5)
            ax.set_title(f'({chr(97+r*2+j)})  {pricing.capitalize()} / {cap:.0%} cap',loc='left')
            ax.set_xlim(73,90);ax.set_xticks([74,78,82,86,90]);ax.set_ylim(3.5,-.55)
            ax.set_yticks(range(4),[NAMES[n] for n in chosen]);ax.tick_params(axis='y',length=0)
            clean(ax)
    for ax in axs[1]:ax.set_xlabel('Worst-of-attack-means completion (%)')
    handles=[Line2D([],[],marker='o',color='#333333',mfc='white',ls='-',label='Original five'),
             Line2D([],[],marker='D',color='#333333',ls='-',label='Augmented nine'),
             Line2D([],[],marker='s',color='#666666',mfc='white',ls='--',label='Matched fixed three'),
             Line2D([],[],marker='x',color='#333333',ls='--',label='Learned target only')]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.57,.070),ncol=2,frameon=False,
               columnspacing=1.9,handlelength=2.2,fontsize=8)
    fig.text(.205,.025,'Within-row offsets separate two comparisons; they do not denote different policies.',fontsize=8)
    save(fig,'results_observation_pricing')

def coalition():
    fig,axs=plt.subplots(1,2,figsize=(7.15,3.2))
    fig.subplots_adjust(left=.12,right=.9,bottom=.255,top=.88,wspace=.30)
    masks=[0,1,2,4,3,5,6,7]
    labels=[r'$\varnothing$',r'$\{1\}$',r'$\{2\}$',r'$\{3\}$',r'$\{1,2\}$',
            r'$\{1,3\}$',r'$\{2,3\}$',r'$\{1,2,3\}$']
    for j,(ax,cap) in enumerate(zip(axs,[.7,.85])):
        v=cell('validation',cap)['frozen_coalition_evaluation']
        o=cell('sensitivity',cap,'objects')['frozen_coalition_values']
        b=cell('sensitivity',cap,'bytes')['frozen_coalition_values']
        vals=np.array([[100*v[str(m)]['frozen_policy_worst_case'],100*o[str(m)]['augmented_value'],
                        100*b[str(m)]['augmented_value']] for m in masks])
        im=heat(ax,vals,cmap='cividis',vmin=65,vmax=90)
        ax.set_yticks(range(8),labels);ax.set_xticks(range(3),['Original five\nobjects','Augmented nine\nobjects','Augmented nine\nbytes'])
        ax.tick_params(length=0);ax.set_title(f'({chr(97+j)})  {cap:.0%} extra-byte cap',loc='left')
        for (y,x),value in np.ndenumerate(vals):
            ax.text(x,y,f'{value+1e-10:.2f}',ha='center',va='center',fontsize=8.5,
                    color='white' if value<76.5 else '#111111')
    axs[0].set_ylabel('Available repetition capabilities at fitting')
    cax=fig.add_axes([.925,.255,.018,.625]);cb=fig.colorbar(im,cax=cax)
    cb.set_label('Frozen-policy completion (%)');cb.set_ticks([65,70,75,80,85,90])
    fig.text(.12,.045,'Same frozen policies and paired evaluation seeds. Scores are not reoptimised coalition worths.',fontsize=8)
    save(fig,'results_coalition_transfer')

def annotate_heat(ax,values,rows,title,bound,decimals=2,sequential=False):
    if sequential:
        im=heat(ax,values,cmap='Blues',vmin=0,vmax=bound)
    else:
        im=heat(ax,values,cmap='RdBu',norm=TwoSlopeNorm(vmin=-bound,vcenter=0,vmax=bound))
    ax.set_xticks(range(6),[f'{c:.0%}' for c in CAPS]);ax.set_yticks(range(len(rows)),rows)
    ax.tick_params(length=0,labelsize=8);ax.set_title(title,loc='left',fontsize=11)
    ax.set_xlabel('Hard additional-byte cap');ax.set_ylabel('bpp / environment / attack fraction')
    for (y,x),v in np.ndenumerate(values):
        label=f'{v:.{decimals}f}' if sequential else (f'{v:+.{decimals}f}' if abs(v)>=.5*10**(-decimals) else f'{0:.{decimals}f}')
        ax.text(x,y,label,ha='center',va='center',fontsize=7.5,
                color='white' if (v/bound>.65 if sequential else abs(v)/bound>.65) else '#111111')
    for y in range(1,len(rows)):
        if rows[y].split('/')[0]!=rows[y-1].split('/')[0]:ax.axhline(y-.5,color='white',lw=1.4)
    return im

def supplement():
    with PdfPages(OUT/'results_supplement.pdf') as pdf:
        for page,comp in enumerate([F,B],1):
            configs=list(itertools.product([.1,.2,.4],['E0','E1','E2'],[.01,.05]))
            rows=[f'{p:.1f} / {e} / {be:.0%}' for p,e,be in configs]
            arrays=[]
            for endpoint in [PRIMARY,SECONDARY]:
                arrays.append(np.array([[100*cell('validation',cap,payload=p,env=e,beta=be,endpoint=endpoint)
                                        ['strategies'][comp]['minimax_minus_this'] for cap in CAPS] for p,e,be in configs]))
            bound=max(.01,max(abs(v).max() for v in arrays))
            fig,axs=plt.subplots(1,2,figsize=(11.69,8.27))
            fig.subplots_adjust(left=.135,right=.88,bottom=.15,top=.86,wspace=.48)
            for ax,v,title in zip(axs,arrays,['(a) Transport completion','(b) Recorded-extraction-weighted completion']):
                im=annotate_heat(ax,v,rows,title,bound,3 if comp==B else 2)
            cax=fig.add_axes([.92,.25,.015,.50]);cb=fig.colorbar(im,cax=cax);cb.set_label('Minimax minus comparator (pp)')
            fig.suptitle(f'S{page}. Fresh-seed differences: minimax minus {NAMES[comp].lower()}',x=.05,ha='left',fontsize=14,y=.95)
            fig.text(.05,.068,'Every saved validation configuration is shown. Entries are point-estimate differences of strategy-specific attack minima.',fontsize=10)
            fig.text(.05,.037,'Shared seeds, source identifiers and outcomes make these cells dependent; they are not independent repetitions or significance tests.',fontsize=10)
            vectorise(fig);pdf.savefig(fig);plt.close(fig)
        for page,measure in [(3,'minimax_minus_this_augmented'),(4,'legacy_to_augmented_drop')]:
            configs=list(itertools.product([.1,.2,.4],['E1','E2'],[.01,.05]))
            rows=[f'{p:.1f} / {e} / {be:.0%}' for p,e,be in configs]
            arrays={}
            for ri,ep in enumerate([PRIMARY,SECONDARY]):
                for ci,pricing in enumerate(['objects','bytes']):
                    arrays[ri,ci]=np.array([[100*cell('sensitivity',cap,pricing,p,env,be,ep)['strategies']
                         [G if page==3 else M][measure] for cap in CAPS] for p,env,be in configs])
            bound=max(.01,max(abs(v).max() for v in arrays.values()))
            fig,axs=plt.subplots(2,2,figsize=(11.69,8.27))
            fig.subplots_adjust(left=.135,right=.88,bottom=.135,top=.865,wspace=.48,hspace=.35)
            for (ri,ci),vals in arrays.items():
                title=f'({chr(97+ri*2+ci)}) '+['Transport','Extraction-weighted'][ri]+' / '+['objects','bytes'][ci]
                im=annotate_heat(axs[ri,ci],vals,rows,title,bound,2,page==4)
            cax=fig.add_axes([.92,.25,.015,.50]);cb=fig.colorbar(im,cax=cax)
            cb.set_label('Minimax minus greedy (pp)' if page==3 else 'Original minus augmented (pp)')
            title='Augmented-catalogue differences: frozen minimax minus frozen greedy' if page==3 else 'Catalogue-expansion loss of frozen minimax policies'
            fig.suptitle(f'S{page}. '+title,x=.05,ha='left',fontsize=14,y=.95)
            fig.text(.05,.06,'All saved sensitivity configurations; same validation seeds reused, no strategy refitting. Values are descriptive point estimates.',fontsize=10)
            fig.text(.05,.03,'Object and byte budgets are different attacker-resource models; equal numerical fractions do not equate their physical strength.',fontsize=10)
            vectorise(fig);pdf.savefig(fig);plt.close(fig)

def audit():
    assert [len(DATA[k]) for k in ['fit','validation','sensitivity']]==[216,216,288]
    for c in DATA['validation']:
        for n,s in c['strategies'].items():
            scores=np.array(s['per_seed_per_attack_expected_performance']).mean(axis=0)
            assert abs(scores.min()-s['worst_of_attack_means'])<1e-12
    for c in DATA['sensitivity']:
        for n,s in c['strategies'].items():
            scores=np.array(s['per_seed_per_attack_expected_performance']).mean(axis=0)
            for ix,key in [(slice(0,5),'legacy_catalogue_worst'),(slice(5,8),'matched_fixed_reservation_worst'),
                           (slice(8,9),'adaptive_only'),(slice(0,9),'augmented_catalogue_worst')]:
                assert abs(scores[ix].min()-s[key])<1e-12
    # Export the full numerical summaries without bulky per-seed arrays.
    export=json.loads(json.dumps(DATA))
    for stage in ['validation','sensitivity']:
        for c in export[stage]:
            for s in c['strategies'].values(): s.pop('per_seed_per_attack_expected_performance',None)
    (HERE/'results_data.json').write_text(json.dumps(export,indent=2)+'\n')
    counts=[]
    for cap in CAPS:
        f=[c for c in DATA['fit'] if c['extra_byte_cap']==cap]
        v=[c for c in DATA['validation'] if c['extra_byte_cap']==cap]
        s=[c for c in DATA['sensitivity'] if c['extra_byte_cap']==cap]
        def nonmono(values):
            return any(values[a]>values[b]+1e-8 for a in range(8) for b in range(8) if a&b==a)
        counts.append({'cap':cap,'fit_cells':len(f),'empty_core':sum(not c['cooperative']['core_nonempty'] for c in f),
                       'shapley_outside_core':sum(not c['cooperative']['shapley_in_core'] for c in f),
                       'not_superadditive':sum(not c['cooperative']['superadditive'] for c in f),
                       'validation_cells':len(v),'validation_nonmonotone':sum(nonmono([c['frozen_coalition_evaluation'][str(m)]['frozen_policy_worst_case'] for m in range(8)]) for c in v),
                       'sensitivity_cells':len(s),'sensitivity_nonmonotone':sum(nonmono([c['frozen_coalition_values'][str(m)]['augmented_value'] for m in range(8)]) for c in s)})
    manifest={'source_sha256':{k:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for k,p in SOURCES.items()},
              'representative_condition':{'payload_bpp':.2,'environment':'E2','beta':.05,'caps':[.7,.85],'endpoint':PRIMARY},
              'all_point_estimates_recomputed':True,'new_simulations':False,'new_fits':False,
              'figure_intervals':'Existing paired seed-block descriptive 95% bootstrap percentiles; no new intervals fitted.',
              'cooperative_counts':counts,'matplotlib':matplotlib.__version__,'numpy':np.__version__}
    (HERE/'figure_audit.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(counts,indent=2))

if __name__=='__main__':
    audit()
    forest();cost();cooperative();sensitivity();coalition();supplement()
    print('Created five vector figures and a four-page full-grid supplement from saved results.')
