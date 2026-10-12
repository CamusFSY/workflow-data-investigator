#!/usr/bin/env python3
"""Regenerate paper figures from the bundled, verified descriptive observations."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch
import numpy as np
ROOT = Path(__file__).resolve().parent
D = json.loads((ROOT/'data/figure_data.json').read_text())
OUT = ROOT/'figures'; OUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':9,'axes.labelsize':8,'xtick.labelsize':7.5,'ytick.labelsize':7.5,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,'axes.edgecolor':'#7b8491','text.color':'#18212c','axes.labelcolor':'#18212c','xtick.color':'#334155','ytick.color':'#334155'})
BLUE='#255f85'; GOLD='#b86c27'; GREY='#6b7785'; LIGHT='#edf2f6'; INK='#18212c'
def save(fig,name):
 for ext in ['pdf','svg','png']:
  fig.savefig(OUT/f'{name}.{ext}',dpi=240,bbox_inches='tight',pad_inches=.03)
  if ext == 'svg':
   path = OUT/f'{name}.{ext}'
   path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()) + '\n')
 plt.close(fig)
def box(ax,x,y,w,h,head,body,ec=BLUE):
 ax.add_patch(Rectangle((x,y),w,h,facecolor='white',edgecolor=ec,linewidth=.9))
 ax.text(x+w/2,y+h*.70,head,ha='center',va='center',weight='bold',fontsize=8)
 ax.text(x+w/2,y+h*.30,body,ha='center',va='center',fontsize=7.5,linespacing=1.4)
def arrow(ax,a,b,color=GREY,rad=0):
 ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=9,lw=.9,color=color,connectionstyle=f'arc3,rad={rad}'))
# 1. Conceptual gate and verification layers. This is a schematic, not measured data.
f,ax=plt.subplots(figsize=(5.5,2.48)); ax.set(xlim=(0,10),ylim=(0,5)); ax.axis('off')
box(ax,.03,3.13,1.95,1.25,'Caller','question\nfixed contract')
box(ax,2.64,3.13,2.14,1.25,'Agent / tools','query\ninspect')
box(ax,5.44,3.13,2.03,1.25,'Finish gate','primary\nsupport')
box(ax,8.13,3.13,1.84,1.25,'Accepted','valid\nartifact')
for a,b in [((1.98,3.76),(2.64,3.76)),((4.78,3.76),(5.44,3.76)),((7.47,3.76),(8.13,3.76))]: arrow(ax,a,b)
ax.text(5.11,4.55,'submit',ha='center',fontsize=7)
arrow(ax,(6.47,3.1),(3.72,3.1),GOLD,rad=-.36)
ax.text(5.05,2.31,'rejection → repair within original budget',ha='center',fontsize=7.5,color=GOLD)
ax.plot([0,10],[1.89,1.89],color='#ccd3da',lw=.6)
ax.text(0,1.64,'Independent evaluation',weight='bold',fontsize=8)
for x,h,b in [(0,'Structure S','artifact contract'),(3.43,'Numerical result N','reference answer'),(6.86,'Grounding G','claim-level support')]:
 ax.text(x+.08,1.02,h,weight='bold',fontsize=8,color=BLUE)
 ax.text(x+.08,.55,b,fontsize=7.5)
ax.text(0,.07,'Acceptance alone does not certify numerical truth or narrative grounding.',fontsize=7.6,style='italic')
save(f,'interface-verification')
# 2. Prospective paired result matrix + measured total resource costs.
f=plt.figure(figsize=(5.5,2.65)); gs=f.add_gridspec(1,3,width_ratios=[1.35,1,1],wspace=.62)
a=f.add_subplot(gs[0]); a.set_title('(a) Strict endpoint',loc='left',fontweight='bold',pad=10)
units={u['unit_id']:u for u in D['units']}
for row,q in enumerate([744,745,800]):
 for col,arm in enumerate(['legacy','roles']):
  ok=units[f'q{q}-{arm}']['overall_success']
  a.add_patch(Rectangle((col-.42,row-.34),.84,.68,facecolor=BLUE if ok else '#fff4e9',edgecolor=BLUE if ok else GOLD,lw=.8))
  a.text(col,row,'pass' if ok else 'unv.',ha='center',va='center',color='white' if ok else GOLD,fontsize=8,weight='bold')
a.set_xlim(-.5,1.5);a.set_ylim(2.65,-.7);a.set_xticks([0,1],['Legacy','Explicit']);a.set_yticks([0,1,2],['744','745','800']);a.tick_params(length=0)
for s in a.spines.values():s.set_visible(False)
for col, total in enumerate(['2/3', '3/3']):
 a.text(col,3.2,total,ha='center',fontsize=8,fontweight='bold',transform=a.transData)
for ix,(key,title,ylabel,fmt,lim) in enumerate([('requests','(b) Model requests','Requests',lambda v:str(int(v)),17),('cost_cny','(c) Model cost','CNY',lambda v:f'{v:.6f}',.125)],1):
 ax=f.add_subplot(gs[ix]);vals=[D['results']['primary_three_families'][arm][key] for arm in ['legacy','roles']]
 bars=ax.bar([0,1],vals,width=.64,color=[GREY,BLUE],edgecolor=[GREY,BLUE],lw=.6)
 bars[0].set_hatch('///'); ax.set_title(title,loc='left',weight='bold',pad=10)
 ax.set_xticks([0,1],['Legacy','Explicit']);ax.tick_params(axis='x',length=0);ax.set_ylim(0,lim);ax.set_ylabel(ylabel,labelpad=3)
 if key=='requests':ax.set_yticks([0,5,10,15])
 else:ax.set_yticks([0,.05,.10]);ax.set_yticklabels(['0','.05','.10'])
 ax.yaxis.grid(True,lw=.4,color='#d6dde5');ax.set_axisbelow(True)
 for p,v in zip(bars,vals):ax.text(p.get_x()+p.get_width()/2,v+lim*.035,fmt(v),ha='center',fontsize=7.5,fontweight='bold')
f.subplots_adjust(left=.045,right=.99,top=.84,bottom=.24)
save(f,'prospective-results')
# 3. Observed ranking and its contradictory summary, no sampling inference.
rows=units['q728-roles']['observed_primary_rows']; names=[r[0] for r in rows]; values=[r[1] for r in rows]
f=plt.figure(figsize=(5.5,3.55));gs=f.add_gridspec(1,2,width_ratios=[2.22,1],wspace=.43);a=f.add_subplot(gs[0]);b=f.add_subplot(gs[1])
y=np.arange(len(rows));a.barh(y,values,height=.62,color=[GOLD if v==1 else BLUE for v in values]);a.set_yticks(y,names);a.invert_yaxis();a.set_xlim(0,140);a.set_xticks([0,50,100]);a.set_xlabel('Recorded count');a.set_title('(a) Replayed 19-row result',loc='left',weight='bold',pad=10)

for tick,v in zip(a.get_yticklabels(),values):
 if v==1: tick.set_color(GOLD)
a.tick_params(axis='y',length=0,labelsize=7.2);a.tick_params(axis='x',length=2);a.xaxis.grid(True,lw=.4,color='#d6dde5');a.set_axisbelow(True)
for yy,v in zip(y,values):a.text(v+2,yy,str(v),va='center',fontsize=7)
b.set_title('(b) Singleton colours',loc='left',weight='bold',pad=10)
b.bar([0,1],[6,7],width=.6,color=['white',GOLD],edgecolor=[GREY,GOLD],hatch=['///',''],lw=.8)
b.set_xticks([0,1],['Summary\nclaim','Verified\ntable']);b.set_ylim(0,8.5);b.set_yticks([0,2,4,6,8]);b.set_ylabel('Number of colours');b.yaxis.grid(True,lw=.4,color='#d6dde5');b.set_axisbelow(True)
for xx,v in enumerate([6,7]):b.text(xx,v+.16,str(v),ha='center',fontweight='bold',fontsize=10)
b.text(.5,-.30,'Correct table\nContradicted summary',ha='center',va='top',transform=b.transAxes,fontsize=8,color=GOLD,linespacing=1.5)
f.subplots_adjust(left=.18,right=.99,top=.9,bottom=.2)
save(f,'ranking-grounding-failure')
print('Generated 3 figures in PDF, SVG, and PNG.')
