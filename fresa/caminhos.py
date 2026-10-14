"""Geometria dos cortes: isolacao com fresa em V, ordem dos cortes e voos de teste.

A isolacao e a mesma de referencias/gerar_gcode_v5_gen5.py, que gerou a blink v5.
"""
import math

from shapely import affinity
from shapely.geometry import LineString, MultiPolygon
from shapely.ops import linemerge, unary_union

TOOL = 0.35              # largura efetiva da fresa em V no gerador
DEPTH = 0.2              # profundidade do corte
# largura real do sulco da fresa em V 30 graus, ponta 0,3: ~0,41 mm a 0,2 de profundidade
LARGURA_SULCO = 0.3 + 2 * DEPTH * math.tan(math.radians(15))
MEIO_SULCO = LARGURA_SULCO / 2
R = TOOL / 2
STEP = TOOL * 0.85       # 0.2975
PASSES = 4
SEG_ISO = 32
SIMPLIFICA = 0.005
TRECHO_MIN = 0.05        # pedacos recortados menores que isso sao descartados
TOL_CONTORNO = 0.3       # voo 2: tira vertices que mudam o contorno menos que isso
BANDA_BORDA = 3.0        # faixa junto da beira onde se procura o plano que vai ate a borda
AREA_MIN_BORDA = 5.0     # mm2 de plano nessa faixa para ele ser o "dono da borda"
# Caminho do lado do plano so fica se outra rede estiver a menos disso (alem da distancia
# da passada). Tirar esse corte nunca cria curto: a outra rede mantem o anel dela inteiro.
# Ele so garante isolacao dupla na folga plano/rede (ate ~0,85 mm na 1a passada).
SEPARA = 0.5


def cobre(elementos, espelhar=False):
    cu = unary_union([e.geom for e in elementos])
    if espelhar:
        cu = affinity.scale(cu, -1, 1, origin=(0, 0))
    return cu


def dono_da_borda(elementos, contorno, espelhar=False, proibidas=None):
    """Plano (zona preenchida) que chega perto da beira da placa, ou None.

    A isolacao entre esse plano e a beira nao separa nada: a faixa de cobre que sobra
    na beira passa a ser dele. Por isso so a rede dona pode perder esses cortes; todas
    as outras continuam com a isolacao completa, e nenhuma outra rede encosta na faixa.
    Dentro das areas proibidas (lista de poligonos) o lado do plano nunca e cortado.
    Devolve dict(rede, dono, outros, proibidas) com a geometria ja espelhada se pedido.
    """
    banda = contorno.difference(contorno.buffer(-BANDA_BORDA, 32))
    por_rede = {}
    for e in elementos:
        if e.regiao and e.rede:
            por_rede[e.rede] = por_rede.get(e.rede, 0.0) + e.geom.intersection(banda).area
    if not por_rede:
        return None
    rede = max(por_rede, key=por_rede.get)
    if por_rede[rede] < AREA_MIN_BORDA:
        return None
    dono = unary_union([e.geom for e in elementos if e.rede == rede])
    outros = unary_union([e.geom for e in elementos if e.rede != rede])
    # a beira do sulco, nao o centro, e que nao pode entrar: meio sulco de folga
    proibido = unary_union(proibidas).buffer(MEIO_SULCO, SEG_ISO) if proibidas else None
    if espelhar:
        dono = affinity.scale(dono, -1, 1, origin=(0, 0))
        outros = affinity.scale(outros, -1, 1, origin=(0, 0))
        proibido = proibido and affinity.scale(proibido, -1, 1, origin=(0, 0))
    return dict(rede=rede, dono=dono, outros=outros, proibidas=proibido)


def descarte(borda, d):
    """Regiao onde um caminho a distancia d do cobre e inutil: do lado do plano dono
    da borda e a mais de SEPARA de qualquer cobre de outra rede."""
    if not borda:
        return None
    lado_dono = borda['dono'].buffer(d + 0.01, SEG_ISO)
    fora = lado_dono.difference(borda['outros'].buffer(d + SEPARA, SEG_ISO))
    if borda.get('proibidas') is not None:
        # na area proibida so fica a isolacao obrigatoria, a das outras redes
        fora = fora.union(lado_dono.difference(borda['outros'].buffer(d + 0.01, SEG_ISO))
                          .intersection(borda['proibidas']))
    return fora


def _pedacos(g):
    out = []
    for sg in (g.geoms if hasattr(g, 'geoms') else [g]):
        if isinstance(sg, LineString) and sg.length > TRECHO_MIN:
            out.append(list(sg.coords))
    return out


def _aneis(g):
    out = []
    for p in (g.geoms if isinstance(g, MultiPolygon) else [g]):
        if p.is_empty:
            continue
        out.append(list(p.exterior.coords))
        out += [list(i.coords) for i in p.interiors]
    return out


def isolacao(cu, area_livre, borda=None):
    """Lista de caminhos (lista de pontos). 1a passada inteira, as outras so na area livre.
    Com um plano dono da borda, tira de todas as passadas o que fica entre ele e a beira."""
    P = []
    for k in range(PASSES):
        d = R + k * STEP
        aneis = _aneis(cu.buffer(d, SEG_ISO).simplify(SIMPLIFICA))
        fora = descarte(borda, d)
        for anel in aneis:
            if k == 0 and fora is None:
                P.append(anel)
                continue
            g = LineString(anel)
            if k > 0:
                g = g.intersection(area_livre)
            if fora is not None:
                g = g.difference(fora)
                if g.geom_type == 'MultiLineString':
                    g = linemerge(g)                  # junta o pedaco cortado no inicio do anel
            P += _pedacos(g)
    return P


def acabamento(cu, livre, borda=None):
    """Passada que corre ao longo da beira das areas proibidas (a linha onde as passadas 2 a 4
    sao recortadas), so na faixa que essas passadas cobrem. Sem ela, cada passada termina numa
    ponta redonda e sobra um dentinho de cobre entre duas pontas vizinhas.

    livre ja vem encolhida meio sulco, entao o sulco desta passada encosta na area sem entrar.
    A faixa comeca a R do cobre (igual a 1a passada) e vai ate a ultima passada: nunca corta
    cobre do projeto. Onde o lado do plano dono da borda e descartado, aqui tambem.
    """
    faixa = cu.buffer(R + (PASSES - 1) * STEP + 0.01, SEG_ISO).difference(cu.buffer(R - 0.01, SEG_ISO))
    linha = livre.boundary.intersection(faixa)
    if borda:
        fora = descarte(borda, R + (PASSES - 1) * STEP)
        if fora is not None:
            linha = linha.difference(fora)
    if linha.is_empty:
        return []
    if linha.geom_type == 'MultiLineString':
        linha = linemerge(linha)
    return _pedacos(linha)


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
