"""Origin/MATLAB presentation style. Geometry comes only from stored data.

White canvas, light grid, restrained categorical colours, vector text and marks.
The 3-D seasonal panels connect observed net loads; no fitted plane is invented.
"""
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import font_manager, colors
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.mplot3d.art3d import Line3DCollection

PALETTE=['#1464A0','#CE4938','#25926B','#7554A3','#C99A26','#2A9EAD','#8C405D']
SURFACE=LinearSegmentedColormap.from_list('scientific_mesh',
 ['#5034A4','#3165D6','#269DD9','#24BBAF','#70CB80','#CCD44D','#F0C63C'])

def configure():
    for name in ('arial.ttf','arialbd.ttf','simsun.ttc','simhei.ttf','times.ttf'):
        p=Path('C:/Windows/Fonts')/name
        if p.exists():font_manager.fontManager.addfont(str(p))
    plt.rcParams.update({
        'font.family':['Arial','SimSun','DejaVu Sans'],'font.size':10,
        'axes.labelsize':10.5,'axes.titlesize':10.5,'axes.titleweight':'normal',
        'axes.linewidth':.85,'axes.edgecolor':'#505050',
        'xtick.direction':'in','ytick.direction':'in','xtick.major.width':.8,
        'ytick.major.width':.8,'xtick.major.size':3.8,'ytick.major.size':3.8,
        'xtick.labelsize':9,'ytick.labelsize':9,'axes.unicode_minus':False,
        'lines.linewidth':1.5,'lines.markersize':4.5,
        'figure.facecolor':'white','axes.facecolor':'white','savefig.facecolor':'white',
        'legend.fontsize':8.5,'legend.fancybox':False,'legend.framealpha':.97,
        'legend.edgecolor':'#C9C9C9','legend.borderpad':.35,
        'grid.color':'#E4E6E8','grid.linewidth':.5,'grid.alpha':1.,
        'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none',
        'savefig.bbox':'tight','savefig.pad_inches':.08})

def finish_axes(fig):
    for ax in fig.axes:
        if ax.name=='3d' or not ax.axison:continue
        ax.title.set_fontproperties(font_manager.FontProperties(family='SimHei',size=10.5))
        for line in ax.get_xgridlines()+ax.get_ygridlines():
            line.set_color('#E4E6E8');line.set_linewidth(.5);line.set_alpha(1.)
        for spine in ax.spines.values():
            spine.set_linewidth(.85);spine.set_color('#505050')
        for ln in ax.lines:
            if ln.get_marker() not in ('None','none','',None,'|','_'):
                ln.set_markeredgewidth(.8)
                if ln.get_marker() in ('o','s','D','^','v'):ln.set_markerfacecolor('white')
        leg=ax.get_legend()
        if leg:
            leg.get_frame().set_linewidth(.55);leg.get_frame().set_edgecolor('#C9C9C9')

def export(fig,folder,name):
    folder=Path(folder)
    for sub in ('previews','png600','svg'):(folder/sub).mkdir(exist_ok=True)
    # Leave dedicated headroom for legends instead of covering measured peaks.
    if name=='q1_dispatch':
        fig.axes[0].set_ylim(-.4,10.6);fig.axes[1].set_ylim(-5.6,8.4)
        fig.axes[2].set_ylim(.6,12.8);fig.axes[3].set_ylim(.25,1.65)
    elif name=='q4_price':
        lo,hi=fig.axes[0].get_ylim();fig.axes[0].set_ylim(lo,hi+(hi-lo)*.20)
        fig.axes[1].set_ylim(.6,12.8)
    elif name=='q3_typical':
        lo,hi=fig.axes[0].get_ylim();fig.axes[0].set_ylim(lo,hi+(hi-lo)*.16)
    finish_axes(fig)
    fig.savefig(folder/(name+'.pdf'))
    fig.savefig(folder/'svg'/(name+'.svg'))
    fig.savefig(folder/'png600'/(name+'.png'),dpi=600)
    fig.savefig(folder/'previews'/(name+'.png'),dpi=180)
    plt.close(fig)

def seasonal_surface(inputs,months):
    """Four representative months; hourly mesh of actual 10-minute data.

    x = time of day, y = day in month, z = (load-PV)/1000 MW.
    Mark each day's maximum among all 144 actual periods. Same z and colour scale.
    """
    months=np.asarray(months);selected=(3,6,9,12)
    norm=colors.Normalize(-8,8)
    dots=['#54349A','#18834B','#C64132','#9A930D']
    fig=plt.figure(figsize=(7.6,4.95))
    for j,m in enumerate(selected):
        ax=fig.add_subplot(2,2,j+1,projection='3d')
        a=(inputs['load'][months==m]-inputs['pv'][months==m])/1000
        assert a.min()>=-8 and a.max()<=8,(m,a.min(),a.max())
        slots=np.r_[np.arange(0,144,6),143]
        xx,yy=np.meshgrid(slots/6,np.arange(1,len(a)+1));zz=a[:,slots]
        segs=[];values=[]
        for d in range(len(a)):
            for t in range(len(slots)-1):
                segs.append([(xx[d,t],yy[d,t],zz[d,t]),(xx[d,t+1],yy[d,t+1],zz[d,t+1])])
                values.append((zz[d,t]+zz[d,t+1])/2)
        for d in range(len(a)-1):
            for t in range(len(slots)):
                segs.append([(xx[d,t],yy[d,t],zz[d,t]),(xx[d+1,t],yy[d+1,t],zz[d+1,t])])
                values.append((zz[d,t]+zz[d+1,t])/2)
        collection=Line3DCollection(segs,cmap=SURFACE,norm=norm,linewidths=.43,alpha=.85)
        collection.set_array(np.asarray(values));ax.add_collection3d(collection)
        peak=a.argmax(axis=1);days=np.arange(1,len(a)+1)
        ax.scatter(peak/6,days,a[np.arange(len(a)),peak],c=dots[j],s=8,
                   edgecolors='white',linewidths=.15,depthshade=False,zorder=8)
        ax.set(xlim=(0,24),ylim=(1,31),zlim=(-8,8),xticks=[0,6,12,18,24],
               yticks=[1,15,31],zticks=[-8,-4,0,4,8])
        ax.set_title(f'({chr(97+j)}) {m}月',fontproperties=font_manager.FontProperties(family='SimHei',size=11),pad=0)
        ax.set_xlabel('时刻 / h',fontsize=9,labelpad=3)
        ax.set_ylabel('月内日序',fontsize=9,labelpad=7)
        ax.set_zlabel('净负荷 / MW',fontsize=9,labelpad=2)
        ax.tick_params(labelsize=8,pad=0)
        ax.view_init(elev=23,azim=-57);ax.set_proj_type('ortho')
        ax.set_box_aspect((1.4,1,.67))
        for axis in (ax.xaxis,ax.yaxis,ax.zaxis):
            axis.pane.set_facecolor((1,1,1,1));axis.pane.set_edgecolor('#E0E0E0')
            axis._axinfo['grid'].update(color='#E2E4E6',linewidth=.45)
            axis.line.set_color('#929292');axis.line.set_linewidth(.6)
    fig.subplots_adjust(left=0,right=.97,top=.99,bottom=.03,wspace=.07,hspace=.09)
    return fig
