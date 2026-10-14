exec(open('check.py').read().split("print('F'")[0])
import math, os
from shapely.geometry import MultiPolygon, Polygon
from shapely import affinity
F = parse(U + 'F_Cu.gbr'); B = parse(U + 'B_Cu.gbr')

TOOL = 0.35; r = TOOL/2; STEP = TOOL*0.85; PASSES = 4; DEPTH = 0.2
f3 = lambda v: f"{v:.3f}"
SAFE, TRAVEL = 15, 10
HEAD = ["G21 G90 G17", f"G0 Z{SAFE}"]
SPIN = ["M3 S1000", "G4 P3"]
TAIL = [f"G0 Z{SAFE}", "M5", "G0 X0 Y0", "M30"]

def rings(g):
    out = []
    for p in (g.geoms if isinstance(g, MultiPolygon) else [g]):
        out.append(list(p.exterior.coords)); out += [list(i.coords) for i in p.interiors]
    return out
def order(P):
    res, cur, P = [], (0, 0), P[:]
    while P:
        i = min(range(len(P)), key=lambda k: math.hypot(P[k][0][0]-cur[0], P[k][0][1]-cur[1]))
        p = P.pop(i); res.append(p); cur = p[-1]
    return res
def iso_paths(feats, mirror):
    cu = unary_union([g for n, g, f in feats])
    if mirror: cu = affinity.scale(cu, -1, 1, origin=(0, 0))
    # area livre: fora dos triangulos de 11 mm dos grampos (|x|+|y| <= 19)
    livre = Polygon([(19, 0), (0, 19), (-19, 0), (0, -19)])
    P = []
    for k in range(PASSES):
        R = rings(cu.buffer(r + k*STEP, 32).simplify(0.005))
        if k == 0:
            P += R   # 1a passada: e ela que isola, fica inteira
            continue
        for ring in R:   # passadas de alargar: cortadas fora da area dos grampos
            g = LineString(ring).intersection(livre)
            for sgm in (g.geoms if hasattr(g, 'geoms') else [g]):
                if isinstance(sgm, LineString) and sgm.length > 0.05: P.append(list(sgm.coords))
    return P, cu

def voo_de_teste(P):
    xs = [x for p in P for x, y in p]; ys = [y for p in P for x, y in p]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    G = ["( VOO DE TESTE em cruz, fresa DESLIGADA: confira se as 4 paradas ficam sobre o cobre )",
         f"( extremos do corte: X {x0:.1f} a {x1:.1f} | Y {y0:.1f} a {y1:.1f} )"]
    for a, b in [((x0, 0), (x1, 0)), ((0, y0), (0, y1))]:
        G += [f"G0 X{f3(a[0])} Y{f3(a[1])}", "G0 Z2", "G4 P2",
              f"G1 X{f3(b[0])} Y{f3(b[1])} F600", "G4 P2", f"G0 Z{SAFE}"]
    G += ["G0 X0 Y0",
          "( PAUSA: aperte Pause de novo no Candle para continuar, ou Stop para cancelar )",
          "M0"]
    return G

def iso_file(name, feats, mirror, titulo, voo):
    P, cu = iso_paths(feats, mirror)
    G = [f"( {titulo} )",
         f"( V-bit 30 graus | {PASSES} passadas | profundidade {DEPTH} | SEM heightmap )",
         "( zero XY: G54 apos homing | zero Z: probe no cobre, uma vez so no centro )"] + HEAD
    if voo: G += voo_de_teste(P)
    G += SPIN
    for p in order(P):
        G += [f"G0 X{f3(p[0][0])} Y{f3(p[0][1])}", "G0 Z1", f"G1 Z-{DEPTH} F30"]
        G += [f"G1 X{f3(x)} Y{f3(y)} F100" for x, y in p[1:]]
        G += [f"G0 Z{TRAVEL}"]
    open(name, 'w').write("\n".join(G + TAIL) + "\n")
    return P, cu

def read_drl(fn):
    tools, cur, holes = {}, None, []
    for line in open(fn):
        line = line.strip()
        m = re.match(r'T(\d+)C([\d.]+)', line)
        if m: tools[m.group(1)] = float(m.group(2)); continue
        m = re.match(r'^T(\d+)$', line)
        if m: cur = m.group(1); continue
        m = re.match(r'X(-?[\d.]+)Y(-?[\d.]+)', line)
        if m: holes.append((float(m.group(1)), float(m.group(2)), tools[cur]))
    return holes
def drill_file(name, holes, titulo, broca):
    G = [f"( {titulo} )", f"( broca {broca} | atravessa subindo a cada 0.4 mm )",
         "( zero XY: G54 apos homing | zero Z: probe no cobre com a broca )"] + HEAD + SPIN
    cur, pts = (0, 0), holes[:]
    while pts:
        i = min(range(len(pts)), key=lambda k: math.hypot(pts[k][0]-cur[0], pts[k][1]-cur[1]))
        x, y = pts.pop(i); cur = (x, y)
        G += [f"G0 X{f3(x)} Y{f3(y)}", "G0 Z0.5"]
        z = 0
        while z > -2.0 + 1e-9:
            z = max(z - 0.4, -2.0); G += [f"G1 Z{z:.2f} F30", "G0 Z0.5"]
        G += [f"G0 Z{TRAVEL}"]
    open(name, 'w').write("\n".join(G + TAIL) + "\n")

pth = read_drl(U + 'PTH.drl'); npth = read_drl(U + 'NPTH.drl')
pequenos = [(x, y) for x, y, d in pth if d < 0.9]          # componentes e vias -> broca 0.4
grandes  = [(x, y) for x, y, d in pth if d >= 0.9]         # conector -> broca 0.8
fiduciais = [(x, y) for x, y, d in npth]                   # fiduciais -> broca 0.8
print(len(pequenos), 'pequenos', len(grandes), 'conector', len(fiduciais), 'fiduciais', fiduciais)

os.makedirs('out', exist_ok=True)
Pt, cut = iso_file('out/1-cobre-cima.nc', F, False, 'BLINK v5: cobre de CIMA, com voo de teste e pausa no inicio', True)
drill_file('out/2-furos-componentes-e-vias.nc', pequenos, 'BLINK v5: furos dos componentes e vias, %d furos' % len(pequenos), '0.4')
drill_file('out/3-furos-conector-e-fiduciais.nc', grandes + fiduciais, 'BLINK v5: furos do conector e os 2 fiduciais, %d furos' % (len(grandes)+len(fiduciais)), '0.8')
Pb, cub = iso_file('out/4-cobre-baixo-SEM-CORRECAO.nc', B, True, 'BLINK v5: cobre de BAIXO, placa virada. Versao sem correcao de giro', False)

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
bg = '#16181d'
fig, axs = plt.subplots(1, 2, figsize=(13, 6.8), facecolor=bg)
allh = [(x, y) for x, y, d in pth]
for ax, P, cu, t, mir in [(axs[0], Pt, cut, 'Cobre de CIMA', False), (axs[1], Pb, cub, 'Cobre de BAIXO (placa virada)', True)]:
    ax.set_facecolor(bg); ax.set_aspect('equal'); ax.set_xlim(-16, 16); ax.set_ylim(-16, 16)
    ax.add_patch(plt.Rectangle((-15, -15), 30, 30, fc='#b87333', alpha=.35))
    for p in (cu.geoms if isinstance(cu, MultiPolygon) else [cu]):
        xs, ys = p.exterior.xy; ax.fill(xs, ys, fc='#e8a050', ec='none')
    for p in P: ax.plot([q[0] for q in p], [q[1] for q in p], color='#5ad1ff', lw=.5)
    for x, y in allh: ax.add_patch(plt.Circle(((-x if mir else x), y), .25, fc=bg))
    for x, y in fiduciais: ax.add_patch(plt.Circle(((-x if mir else x), y), .4, fc='#ff5a5a'))
    ax.set_title(t, color='w'); ax.tick_params(colors='#aaa')
axs[0].plot([min(q[0] for p in Pt for q in p), max(q[0] for p in Pt for q in p)], [0, 0], color='#7dff6a', lw=1, ls='--')
axs[0].plot([0, 0], [min(q[1] for p in Pt for q in p), max(q[1] for p in Pt for q in p)], color='#7dff6a', lw=1, ls='--')
plt.tight_layout(); plt.savefig('out/preview-v5.png', dpi=90, facecolor=bg)

def cantos(P, nome):
    pior = max(abs(x) + abs(y) for p in P for x, y in p)
    n = sum(1 for p in P for x, y in p if abs(x) + abs(y) > 19)
    print(nome, 'maior |x|+|y| =', round(pior, 2), '| pontos dentro da area dos grampos:', n)
cantos(Pt, 'cima'); cantos(Pb, 'baixo')
