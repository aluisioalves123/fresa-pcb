"""Geometria dos cortes: isolacao com fresa em V, ordem dos cortes e voos de teste.

A isolacao e a mesma de referencias/gerar_gcode_v5_gen5.py, que gerou a blink v5.
"""
import math

from shapely import affinity
from shapely.geometry import LineString, MultiPolygon
from shapely.ops import unary_union

TOOL = 0.35              # largura efetiva da fresa em V no gerador
R = TOOL / 2
STEP = TOOL * 0.85       # 0.2975
PASSES = 4
SEG_ISO = 32
SIMPLIFICA = 0.005
TRECHO_MIN = 0.05        # pedacos recortados menores que isso sao descartados
TOL_CONTORNO = 0.3       # voo 2: tira vertices que mudam o contorno menos que isso


def cobre(elementos, espelhar=False):
    cu = unary_union([e.geom for e in elementos])
    if espelhar:
        cu = affinity.scale(cu, -1, 1, origin=(0, 0))
    return cu


def _aneis(g):
    out = []
    for p in (g.geoms if isinstance(g, MultiPolygon) else [g]):
        if p.is_empty:
            continue
        out.append(list(p.exterior.coords))
        out += [list(i.coords) for i in p.interiors]
    return out


def isolacao(cu, area_livre):
    """Lista de caminhos (lista de pontos). 1a passada inteira, as outras so na area livre."""
    P = []
    for k in range(PASSES):
        aneis = _aneis(cu.buffer(R + k * STEP, SEG_ISO).simplify(SIMPLIFICA))
        if k == 0:
            P += aneis
            continue
        for anel in aneis:
            g = LineString(anel).intersection(area_livre)
            for sg in (g.geoms if hasattr(g, 'geoms') else [g]):
                if isinstance(sg, LineString) and sg.length > TRECHO_MIN:
                    P.append(list(sg.coords))
    return P


def ordenar(P, inicio=(0, 0)):
    """Vizinho mais proximo a partir do inicio (igual a referencia)."""
    res, cur, P = [], inicio, P[:]
    while P:
        i = min(range(len(P)), key=lambda k: math.hypot(P[k][0][0] - cur[0], P[k][0][1] - cur[1]))
        p = P.pop(i)
        res.append(p)
        cur = p[-1]
    return res


def ordenar_pontos(pts, inicio=(0, 0)):
    res, cur, pts = [], inicio, pts[:]
    while pts:
        i = min(range(len(pts)), key=lambda k: math.hypot(pts[k][0] - cur[0], pts[k][1] - cur[1]))
        p = pts.pop(i)
        res.append(p)
        cur = p
    return res


def extremos(P):
    xs = [x for p in P for x, y in p]
    ys = [y for p in P for x, y in p]
    return min(xs), max(xs), min(ys), max(ys)


def _casco(pontos):
    """Casco convexo (cadeia monotona), anti-horario, comecando no menor (x, y)."""
    pts = sorted(set((round(x, 3), round(y, 3)) for x, y in pontos))
    if len(pts) < 3:
        return pts
    c = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and c(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and c(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def _dist_reta(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L < 1e-12:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    return abs(dx * (a[1] - p[1]) - dy * (a[0] - p[0])) / L


def contorno_voo(P, tol=TOL_CONTORNO):
    """Casco convexo de todos os pontos de corte, sem os vertices que mudam o
    contorno menos que tol (tira sempre o que muda menos, um por vez)."""
    H = _casco([q for p in P for q in p])
    while len(H) > 3:
        n = len(H)
        d = [_dist_reta(H[i], H[i - 1], H[(i + 1) % n]) for i in range(n)]
        i = min(range(n), key=d.__getitem__)
        if d[i] >= tol:
            break
        H.pop(i)
    return H
