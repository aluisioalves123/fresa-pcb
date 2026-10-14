"""Leitor de Gerber X2 (o que o KiCad exporta) para geometria shapely.

Base: o parser de referencias/validar_gerbers_check.py, generalizado para
formato de coordenadas do cabecalho, polegadas, arcos, regioes (G36/G37) e
aberturas de poligono. Macros de abertura (AM) nao sao suportadas: pads
redondos e ovais, que sao a regra do projeto, nao usam macro.
"""
import math
import re
from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union

# mesmas resolucoes do gerador que fez a blink v5 (nao mudar: muda o G-code)
SEG_FLASH = 48
SEG_TRACO = 16


class ErroGerber(Exception):
    pass


@dataclass
class Elemento:
    rede: str | None       # %TO.N  (None = sem rede)
    geom: object           # Polygon
    funcao: str | None     # %TA.AperFunction: ComponentPad, ViaPad, Conductor...
    pos: tuple | None      # centro do flash (pads e vias), None para trilhas
    ref: str | None        # %TO.P  componente, ex "R1"


def _blocos(texto):
    """Quebra o arquivo em comandos, sem % e sem espacos (igual a referencia)."""
    for raw in texto.split('*'):
        s = re.sub(r'[%\s]', '', raw)
        if s:
            yield s


def _arco(x0, y0, x1, y1, i, j, horario, multi):
    cx, cy = x0 + i, y0 + j
    if not multi:
        raise ErroGerber('arco em modo de quadrante unico (G74) nao suportado')
    r = math.hypot(x0 - cx, y0 - cy)
    a0 = math.atan2(y0 - cy, x0 - cx)
    a1 = math.atan2(y1 - cy, x1 - cx)
    if horario:
        d = a0 - a1
        while d <= 1e-12:
            d += 2 * math.pi
        d = -d
    else:
        d = a1 - a0
        while d <= 1e-12:
            d += 2 * math.pi
    n = max(2, int(abs(d) / (2 * math.pi) * 128) + 1)
    return [(cx + r * math.cos(a0 + d * k / n), cy + r * math.sin(a0 + d * k / n)) for k in range(n + 1)]


def _flash(tipo, v, x, y):
    if tipo == 'C':
        return Point(x, y).buffer(v[0] / 2, SEG_FLASH)
    if tipo == 'R':
        return box(x - v[0] / 2, y - v[1] / 2, x + v[0] / 2, y + v[1] / 2)
    if tipo == 'O':
        w, h = v[0], v[1]
        if h >= w:
            return LineString([(x, y - (h - w) / 2), (x, y + (h - w) / 2)]).buffer(w / 2, SEG_FLASH)
        return LineString([(x - (w - h) / 2, y), (x + (w - h) / 2, y)]).buffer(h / 2, SEG_FLASH)
    if tipo == 'P':
        d, n = v[0], int(v[1])
        rot = math.radians(v[2]) if len(v) > 2 else 0.0
        return Polygon([(x + d / 2 * math.cos(rot + 2 * math.pi * k / n),
                         y + d / 2 * math.sin(rot + 2 * math.pi * k / n)) for k in range(n)])
    raise ErroGerber(f'abertura {tipo} nao suportada: use pads redondos ou ovais')


def _traco(tipo, v, pts):
    if tipo == 'C':
        if len(pts) == 2 and pts[0] == pts[1]:
            return Point(pts[0]).buffer(v[0] / 2, SEG_FLASH)
        return LineString(pts).buffer(v[0] / 2, SEG_TRACO)
    if tipo == 'R':   # retangulo arrastado: uniao dos cascos de cada segmento
        w, h = v[0] / 2, v[1] / 2
        partes = []
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            q = [(ax - w, ay - h), (ax + w, ay - h), (ax + w, ay + h), (ax - w, ay + h),
                 (bx - w, by - h), (bx + w, by - h), (bx + w, by + h), (bx - w, by + h)]
            partes.append(Polygon(q).convex_hull)
        return unary_union(partes)
    raise ErroGerber(f'trilha desenhada com abertura {tipo} nao suportada')


def ler(caminho):
    """Le um Gerber de cobre. Devolve a lista de Elementos (um por flash ou trilha)."""
    texto = open(caminho, encoding='utf-8', errors='replace').read()
    ap, ap_func = {}, {}
    cur = None
    x = y = 0.0
    escala_mm, dec = 1.0, 6
    rede = ref = func = None
    modo, multi = 1, True
    regiao, contorno = False, []
    regioes_contornos = []
    out = []

    def num(s):
        return int(s) / 10 ** dec * escala_mm

    for s in _blocos(texto):
        m = re.match(r'FSLAX(\d)(\d)Y(\d)(\d)$', s)
        if m:
            dec = int(m.group(2))
            continue
        if s.startswith('FS'):
            raise ErroGerber(f'formato de coordenadas nao suportado: {s}')
        if s == 'MOIN':
            escala_mm = 25.4
            continue
        if s == 'MOMM':
            escala_mm = 1.0
            continue
        if s.startswith('LP'):
            if s != 'LPD':
                raise ErroGerber('polaridade negativa (LPC) nao suportada')
            continue
        m = re.match(r'TA\.AperFunction,(\w+)', s)
        if m:
            func = m.group(1)
            continue
        if s.startswith('AM'):
            continue
        m = re.match(r'ADD(\d+)([A-Za-z_][\w.]*?),?([\d.X-]*)$', s)
        if m:
            tipo = m.group(2)
            v = [float(t) * escala_mm for t in m.group(3).split('X')] if m.group(3) else []
            if tipo == 'P' and len(v) >= 2:
                v[1] /= escala_mm
                if len(v) > 2:
                    v[2] /= escala_mm
            ap[int(m.group(1))] = (tipo, v)
            ap_func[int(m.group(1))] = func
            continue
        m = re.match(r'TO\.N,(.*)$', s)
        if m:
            rede = m.group(1) or None
            continue
        m = re.match(r'TO\.P,([^,]*)', s)
        if m:
            ref = m.group(1)
            continue
        if s.startswith('TO') or s.startswith('TF'):
            continue
        if s.startswith('TD'):
            if s in ('TD', 'TD.N'):
                rede = None
            if s in ('TD', 'TD.P'):
                ref = None
            if s in ('TD', 'TD.AperFunction'):
                func = None
            continue
        if s.startswith('G04') or s in ('M02', 'M00'):
            continue
        if s == 'G36':
            regiao, contorno, regioes_contornos = True, [], []
            func_regiao = func
            continue
        if s == 'G37':
            if len(contorno) >= 3:
                regioes_contornos.append(contorno)
            pols = [Polygon(c).buffer(0) for c in regioes_contornos]
            if pols:
                out.append(Elemento(rede, unary_union(pols), func_regiao, None, ref))
            regiao = False
            continue
        if s == 'G75':
            multi = True
            continue
        if s == 'G74':
            multi = False
            continue
        m = re.match(r'^(?:G54)?D(\d+)$', s)
        if m and int(m.group(1)) >= 10:
            cur = int(m.group(1))
            continue
        m = re.match(r'^(G0?[123])?(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?(?:D0?([123]))?$', s)
        if not m or not s:
            continue
        if m.group(1):
            modo = int(m.group(1)[1:])
        if not m.group(6):
            continue
        nx = num(m.group(2)) if m.group(2) else x
        ny = num(m.group(3)) if m.group(3) else y
        i = num(m.group(4)) if m.group(4) else 0.0
        j = num(m.group(5)) if m.group(5) else 0.0
        op = m.group(6)
        if op == '1':
            pts = [(x, y), (nx, ny)] if modo == 1 else _arco(x, y, nx, ny, i, j, modo == 2, multi)
            if regiao:
                if not contorno:
                    contorno = [(x, y)]
                contorno += pts[1:]
            else:
                if cur not in ap:
                    raise ErroGerber('trilha sem abertura selecionada')
                tipo, v = ap[cur]
                out.append(Elemento(rede, _traco(tipo, v, pts), ap_func[cur], None, ref))
        elif op == '2':
            if regiao and len(contorno) >= 3:
                regioes_contornos.append(contorno)
            contorno = []
        elif op == '3':
            if cur not in ap:
                raise ErroGerber('flash sem abertura selecionada')
            tipo, v = ap[cur]
            out.append(Elemento(rede, _flash(tipo, v, nx, ny), ap_func[cur], (nx, ny), ref))
        x, y = nx, ny
    return out


def ler_contorno(caminho):
    """Le o Edge.Cuts e devolve o poligono da placa (o maior fechado)."""
    texto = open(caminho, encoding='utf-8', errors='replace').read()
    x = y = 0.0
    escala_mm, dec = 1.0, 6
    modo, multi = 1, True
    linhas = []
    for s in _blocos(texto):
        m = re.match(r'FSLAX(\d)(\d)Y(\d)(\d)$', s)
        if m:
            dec = int(m.group(2))
            continue
        if s == 'MOIN':
            escala_mm = 25.4
            continue
        if s == 'G75':
            multi = True
            continue
        m = re.match(r'^(G0?[123])?(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?(?:D0?([123]))?$', s)
        if not m:
            continue
        if m.group(1):
            modo = int(m.group(1)[1:])
        if not m.group(6):
            continue
        n = lambda g: int(g) / 10 ** dec * escala_mm
        nx = n(m.group(2)) if m.group(2) else x
        ny = n(m.group(3)) if m.group(3) else y
        if m.group(6) == '1':
            pts = [(x, y), (nx, ny)] if modo == 1 else _arco(
                x, y, nx, ny, n(m.group(4) or '0'), n(m.group(5) or '0'), modo == 2, multi)
            linhas.append(LineString([(round(a, 4), round(b, 4)) for a, b in pts]))
        x, y = nx, ny
    pols = list(polygonize(unary_union(linhas))) if linhas else []
    if not pols:
        raise ErroGerber('o Edge.Cuts nao forma um contorno fechado')
    return max(pols, key=lambda p: p.area)
