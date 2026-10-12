"""图10：问题2与问题3紧急购电的月内小时三维分布。

只读取 results/ 中已核对的 emergency 轨迹与 summary.json 的报告期日期，按月份与
小时汇总为 MWh 后绘图；不重新求解，不改写任何主结果。运行方式（工程根目录）：

    python code/emergency_surface.py
"""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import colors, font_manager
from mpl_toolkits.mplot3d.art3d import Line3DCollection

import scientific_style as style

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / 'results'
F = ROOT / 'figures'
DT = 1 / 6                      # 每个时段 10 分钟，换算成小时
MONTHS = np.arange(2, 13)       # 报告期为 2—12 月
HOURS = np.arange(24)
CASES = (('q2', '问题2'), ('q3', '问题3'))

S = json.loads((R / 'summary.json').read_text(encoding='utf-8'))
months = np.array([int(d[5:7]) for d in S['dates']])
TITLE_FONT = 'SimHei'
MESH_COLOR = '#3165D6'      # 网格线固定蓝，与论文其他线图一致
MARKER_CMAP = 'turbo'     # 顶点按高度着色：低值暗蓝、峰值红，便于读出峰值位置


def register_cjk():
    """Windows 上用 SimSun/SimHei；其他平台退回本机可用的中文字体。"""
    global TITLE_FONT
    have = {f.name for f in font_manager.fontManager.ttflist}
    body = next((n for n in ('SimSun', 'AR PL SungtiL GB', 'Noto Serif CJK SC',
                             'WenQuanYi Zen Hei', 'Droid Sans Fallback') if n in have), None)
    # Droid Sans Fallback 的中文可显示，但无法被子集化嵌入 PDF，故不作为首选。
    title = next((n for n in ('SimHei', 'AR PL SungtiL GB', 'WenQuanYi Zen Hei',
                              'AR PL UMing CN') if n in have), None)
    if body:
        plt.rcParams['font.family'] = [body, 'DejaVu Sans']
    if title:
        TITLE_FONT = title
    print(f'中文字体：正文 {body}，标题 {TITLE_FONT}')


def monthly_hourly(key):
    """把 (365,144) 的 kW 轨迹按月、小时汇总为 (11,24) 的 MWh。"""
    em = np.load(R / f'{key}.npz')['emergency']
    out = np.zeros((len(MONTHS), len(HOURS)))
    for i, m in enumerate(MONTHS):
        sel = months == m
        if not sel.any():
            continue
        out[i] = em[sel].reshape(-1, len(HOURS), 6).sum(axis=(0, 2)) * DT / 1000
    return out


def add_mesh(ax, z, vmax):
    """网格线固定蓝色；顶点按高度着色，便于直接读出峰值位置。"""
    segments, values = [], []
    for i in range(z.shape[0]):
        for j in range(z.shape[1] - 1):
            segments.append([(HOURS[j], MONTHS[i], z[i, j]),
                             (HOURS[j + 1], MONTHS[i], z[i, j + 1])])
    for i in range(z.shape[0] - 1):
        for j in range(z.shape[1]):
            segments.append([(HOURS[j], MONTHS[i], z[i, j]),
                             (HOURS[j], MONTHS[i + 1], z[i + 1, j])])
    norm = colors.Normalize(0, vmax)
    ax.add_collection3d(Line3DCollection(segments, colors=MESH_COLOR,
                                         linewidths=.5, alpha=.95))
    # 逐格标记，白描边保证与网格线区分。
    xx, yy = np.meshgrid(HOURS, MONTHS)
    ax.scatter(xx.ravel(), yy.ravel(), z.ravel(), c=z.ravel(), cmap=MARKER_CMAP,
               norm=norm, s=9, edgecolors='white', linewidths=.25,
               depthshade=False, zorder=8)


def draw(ax, z, label, vmax, ztop):
    add_mesh(ax, z, vmax)
    ax.set(xlim=(0, 24), ylim=(2, 12), zlim=(0, ztop),
           xticks=[0, 6, 12, 18, 24], yticks=[2, 4, 6, 8, 10, 12],
           zticks=[0, 3, 6, 9])
    ax.set_xlabel('小时区间 / h', fontsize=9, labelpad=4)
    ax.set_ylabel('月份', fontsize=9, labelpad=6)
    ax.set_zlabel('月内该小时紧急电量 / MWh', fontsize=9, labelpad=5)
    ax.tick_params(labelsize=8, pad=1)
    ax.view_init(elev=22, azim=-57)
    ax.set_proj_type('ortho')
    ax.set_box_aspect((1.45, 1, .72))
    ax.set_title(label, fontproperties=font_manager.FontProperties(family=TITLE_FONT, size=10.5), pad=2)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((1, 1, 1, 1)); axis.pane.set_edgecolor('#E0E0E0')
        axis._axinfo['grid'].update(color='#E2E4E6', linewidth=.45)
        axis.line.set_color('#929292'); axis.line.set_linewidth(.6)


def main():
    style.configure()
    register_cjk()
    data = {k: monthly_hourly(k) for k, _ in CASES}
    for (k, _), z in zip(CASES, data.values()):
        want = S['cases'][k]['emergency_kwh'] / 1000
        assert abs(z.sum() - want) < 5e-3, (k, z.sum(), want)
        print(f'{k}: 总量 {z.sum():.2f} MWh  峰值 {z.max():.2f} MWh')
    vmax = max(z.max() for z in data.values())
    ztop = np.ceil(vmax)
    fig = plt.figure(figsize=(7.6, 3.4))
    for j, (k, name) in enumerate(CASES):
        ax = fig.add_subplot(1, 2, j + 1, projection='3d')
        z = data[k]
        draw(ax, z, f'({chr(97 + j)}) {name}  |  总量 {z.sum():.2f} MWh', vmax, ztop)
    fig.subplots_adjust(left=.01, right=.99, top=.99, bottom=.02, wspace=.06)
    style.export(fig, F, 'emergency_heatmap')
    print('已写出 figures/emergency_heatmap.pdf 及预览、SVG、600 dpi PNG')


if __name__ == '__main__':
    main()
