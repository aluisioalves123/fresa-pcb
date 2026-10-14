"""Imagem de previa de cada lado, tema escuro."""
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import MultiPolygon

from . import caminhos as cam

FUNDO = '#16181d'


def _preenche(ax, g, **kw):
    for p in (g.geoms if isinstance(g, MultiPolygon) else [g]):
        if p.is_empty:
            continue
        xs, ys = p.exterior.xy
        ax.fill(xs, ys, **kw)
        for i in p.interiors:
            xs, ys = i.xy
            ax.fill(xs, ys, fc=FUNDO, ec='none')


def _lado(placa, res, fid, espelhar, titulo, caminho):
    P = res.caminhos_baixo if espelhar else res.caminhos_cima
    H = res.contorno_baixo if espelhar else res.contorno_cima
    cu = cam.cobre(placa.B if espelhar else placa.F, espelhar)
    sx = -1 if espelhar else 1
    x0, y0, x1, y1 = placa.limites
    m = 2
    fig, ax = plt.subplots(figsize=(7, 7.4), facecolor=FUNDO)
    ax.set_facecolor(FUNDO)
    ax.set_aspect('equal')
    ax.set_xlim(x0 - m, x1 + m)
    ax.set_ylim(y0 - m, y1 + m)
    _preenche(ax, placa.contorno, fc='#b87333', alpha=.35, ec='none')
    for t in placa.triangulos_garras():
        _preenche(ax, t, fc='#ff5a5a', alpha=.25, ec='#ff5a5a', hatch='//')
    _preenche(ax, cu, fc='#e8a050', ec='none')
    for p in P:
        ax.plot([q[0] for q in p], [q[1] for q in p], color='#5ad1ff', lw=.5)
    for f in placa.furos:
        ax.add_patch(plt.Circle((sx * f.x, f.y), .4, fc=FUNDO))
    for x, y in fid:
        ax.add_patch(plt.Circle((sx * x, y), .55, fc='none', ec='#ff5a5a', lw=1.5))
    xa, xb, ya, yb = cam.extremos(P)
    ax.plot([xa, xb], [0, 0], color='#7dff6a', lw=1, ls='--')
    ax.plot([0, 0], [ya, yb], color='#7dff6a', lw=1, ls='--')
    ax.plot([q[0] for q in H + [H[0]]], [q[1] for q in H + [H[0]]], color='#ffd84a', lw=1, ls=':')
    ax.set_title(titulo, color='w')
    ax.tick_params(colors='#aaa')
    for s in ax.spines.values():
        s.set_color('#444')
    fig.text(.5, .015, 'azul: corte   verde: voo 1 em cruz   amarelo: voo 2 no contorno   '
             'vermelho: garras e fiduciais', color='#aaa', ha='center', fontsize=8)
    plt.tight_layout(rect=(0, .03, 1, 1))
    plt.savefig(caminho, dpi=110, facecolor=FUNDO)
    plt.close(fig)
    return caminho


def desenhar(placa, res, fid, saida):
    return [
        _lado(placa, res, fid, False, f'{placa.nome}: fase 1, cobre de cima',
              os.path.join(saida, 'previa-cima.png')),
        _lado(placa, res, fid, True, f'{placa.nome}: fase 3, cobre de baixo, placa virada',
              os.path.join(saida, 'previa-baixo.png')),
    ]
