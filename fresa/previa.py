"""Imagem de previa de cada lado, tema escuro: a placa como ela sai da maquina.

A placa virgem e toda de cobre. A fresa em V so abre os sulcos, e o que nao foi cortado
continua sendo cobre: ligado a uma rede (laranja forte, inclusive a faixa da beira que
fica grudada num plano) ou solto, sobra sem ligacao (laranja apagado). A broca fura.
"""
import math
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point
from shapely.ops import unary_union

from . import caminhos as cam
from . import gcode

FUNDO = '#16181d'
COBRE = '#e8a050'          # cobre ligado a uma rede
SOBRA = '#7a5634'          # cobre solto, sem ligacao
FIBRA = '#2f3a2c'          # sulco da fresa: aparece a fibra de vidro
FURO = '#0b0c0f'
ANEL_FURO = '#e6e6e6'
VERMELHO, VERDE, AMARELO = '#ff5a5a', '#7dff6a', '#ffd84a'

LARGURA_SULCO = cam.LARGURA_SULCO   # ~0,41 mm


def _caminho(g):
    """Poligono(s) shapely, com buracos, para um Path do matplotlib."""
    partes = []
    for p in (g.geoms if hasattr(g, 'geoms') else [g]):
        if p.is_empty or p.geom_type != 'Polygon':
            continue
        for anel in [p.exterior] + list(p.interiors):
            partes.append(Path(list(anel.coords), closed=True))
    return Path.make_compound_path(*partes) if partes else None


def _pinta(ax, g, **kw):
    c = _caminho(g)
    if c is not None:
        ax.add_patch(PathPatch(c, **kw))


def _lado(placa, res, fid, espelhar, titulo, caminho):
    P = res.caminhos_baixo if espelhar else res.caminhos_cima
    H = res.contorno_baixo if espelhar else res.contorno_cima
    cu = cam.cobre(placa.B if espelhar else placa.F, espelhar)
    sx = -1 if espelhar else 1
    contorno = affinity.scale(placa.contorno, -1, 1, origin=(0, 0)) if espelhar else placa.contorno

    # o que a maquina tira: sulcos da fresa em V e furos da broca
    sulcos = unary_union([LineString(p).buffer(LARGURA_SULCO / 2, 8) for p in P if len(p) > 1])
    furos = unary_union([Point(sx * f.x, f.y).buffer(gcode.BROCA / 2, 24) for f in placa.furos])
    resto = contorno.difference(sulcos).difference(furos)
    ligado, solto = [], []
    for ilha in (resto.geoms if isinstance(resto, MultiPolygon) else [resto]):
        (ligado if ilha.intersection(cu).area > 1e-4 else solto).append(ilha)

    x0, y0, x1, y1 = contorno.bounds
    m = 2
    fig, ax = plt.subplots(figsize=(7, 8.2), facecolor=FUNDO)
    ax.set_facecolor(FUNDO)
    ax.set_aspect('equal')
    ax.set_xlim(x0 - m, x1 + m)
    ax.set_ylim(y0 - m, y1 + m)

    _pinta(ax, contorno, fc=FIBRA, ec='none')
    _pinta(ax, unary_union(solto), fc=SOBRA, ec='none')
    _pinta(ax, unary_union(ligado), fc=COBRE, ec='none')
    for a in placa.areas_proibidas():
        a = affinity.scale(a, -1, 1, origin=(0, 0)) if espelhar else a
        _pinta(ax, a, fc='none', ec=VERMELHO, hatch='//', lw=.8, alpha=.7)
    for f in placa.furos:
        ax.add_patch(plt.Circle((sx * f.x, f.y), gcode.BROCA / 2, fc=FURO, ec=ANEL_FURO, lw=.9))
    for x, y in fid:
        ax.add_patch(plt.Circle((sx * x, y), .75, fc='none', ec=VERMELHO, lw=1.5))
    xa, xb, ya, yb = res.cruz_baixo if espelhar else res.cruz_cima
    ax.plot([xa, xb], [0, 0], color=VERDE, lw=1, ls='--')
    ax.plot([0, 0], [ya, yb], color=VERDE, lw=1, ls='--')
    ax.plot([q[0] for q in H + [H[0]]], [q[1] for q in H + [H[0]]], color=AMARELO, lw=1.2, ls=':')

    ax.set_title(titulo, color='w')
    ax.tick_params(colors='#aaa')
    for s in ax.spines.values():
        s.set_color('#444')
    legenda = [
        Patch(fc=COBRE, label='cobre ligado a uma rede'),
        Patch(fc=SOBRA, label='cobre que sobra solto'),
        Patch(fc=FIBRA, ec='#555', label=f'sulco da fresa em V ({LARGURA_SULCO:.2f} mm)'),
        Line2D([], [], marker='o', ls='', mfc=FURO, mec=ANEL_FURO, ms=7, label=f'furo da broca {gcode.BROCA} (fase 2)'),
        Patch(fc='none', ec=VERMELHO, hatch='//', label='área proibida'),
        Line2D([], [], marker='o', ls='', mfc='none', mec=VERMELHO, ms=9, mew=1.5, label='fiducial'),
        Line2D([], [], color=VERDE, ls='--', label='voo 1, em cruz, Z2'),
        Line2D([], [], color=AMARELO, ls=':', lw=1.2, label='voo 2, contorno, Z0.5'),
    ]
    leg = fig.legend(handles=legenda, loc='lower center', ncol=2, fontsize=8, frameon=False,
                     labelcolor='#ddd', handlelength=2.2, columnspacing=1.5)
    for t in leg.get_texts():
        t.set_color('#ddd')
    plt.tight_layout(rect=(0, .12, 1, 1))
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
