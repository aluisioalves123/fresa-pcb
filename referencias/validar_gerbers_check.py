import re, math
from shapely.geometry import Point, LineString, box
from shapely.ops import unary_union
U = '/mnt/user-data/uploads/Desktop/Rino Eletronica/Projetos/blink blink/gerber/blink blink-roteado-'
def parse(fn):
    ap = {}; afn = {}; cur = None; x = y = 0.0; feats = []; net = None; func = None
    for raw in open(fn).read().split('*'):
        s = re.sub(r'[%\s]', '', raw)
        m = re.match(r'TA\.AperFunction,(\w+)', s)
        if m: func = m.group(1); continue
        m = re.match(r'ADD(\d+)([A-Za-z]+),?(.*)', s)
        if m:
            v = [float(t) for t in m.group(3).replace('X', ' ').split()] if m.group(3) else []
            ap[int(m.group(1))] = (m.group(2), v); afn[int(m.group(1))] = func; continue
        m = re.match(r'TO\.N,(.*)', s)
        if m: net = m.group(1); continue
        if s == 'TD': continue
        m = re.match(r'^D(\d+)$', s)
        if m and int(m.group(1)) >= 10: cur = int(m.group(1)); continue
        m = re.match(r'^(?:X(-?\d+))?(?:Y(-?\d+))?D0([123])$', s)
        if not m: continue
        nx = int(m.group(1))/1e6 if m.group(1) else x
        ny = int(m.group(2))/1e6 if m.group(2) else y
        k, v = ap[cur]
        if m.group(3) == '3':
            if k == 'C': g = Point(nx, ny).buffer(v[0]/2, 48)
            elif k == 'R': g = box(nx-v[0]/2, ny-v[1]/2, nx+v[0]/2, ny+v[1]/2)
            elif k == 'O':
                w, h = v[0], v[1]
                g = (LineString([(nx, ny-(h-w)/2), (nx, ny+(h-w)/2)]).buffer(w/2, 48) if h >= w
                     else LineString([(nx-(w-h)/2, ny), (nx+(w-h)/2, ny)]).buffer(h/2, 48))
            else: raise SystemExit('abertura ' + k)
            feats.append((net, g, afn[cur]))
        elif m.group(3) == '1':
            feats.append((net, LineString([(x, y), (nx, ny)]).buffer(v[0]/2, 16), afn[cur]))
        x, y = nx, ny
    return feats
F = parse(U + 'F_Cu.gbr'); B = parse(U + 'B_Cu.gbr')
print('F', len(F), 'B', len(B))
# folgas entre redes
for nome, L in [('cima', F), ('baixo', B)]:
    by = {}
    for n, g, f in L: by.setdefault(n, []).append(g)
    Un = {n: unary_union(v) for n, v in by.items()}; ns = list(Un); worst = 9
    for i in range(len(ns)):
        for j in range(i+1, len(ns)):
            d = Un[ns[i]].distance(Un[ns[j]]); worst = min(worst, d)
            if d < 0.45: print('PERTO', nome, ns[i], ns[j], round(d, 3))
    print(nome, 'redes', len(ns), 'menor vao', round(worst, 3))
# conectividade (furos ligam as camadas)
by = {}
for n, g, f in F + B: by.setdefault(n, []).append(g)
for n, gs in by.items():
    u = unary_union(gs); k = len(u.geoms) if hasattr(u, 'geoms') else 1
    print(('OK  ' if k == 1 else 'DESCONECTADA ') + str(n), k)
# regra: trilha de cima nao encosta em pad de componente
pads_top = [(n, g) for n, g, f in F if f == 'ComponentPad']
tr_top = [(n, g) for n, g, f in F if f == 'Conductor']
bad = 0
for n, t in tr_top:
    for pn, p in pads_top:
        if t.intersects(p): bad += 1; print('TRILHA DE CIMA NO PINO', n)
print('trilhas de cima:', len(tr_top), 'tocando pinos:', bad)
print('furos/vias no F:', sum(1 for n,g,f in F if f=='ViaPad'))
