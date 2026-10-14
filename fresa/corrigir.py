"""Correcao do arquivo 3 pelos fiduciais (porte de referencias/corrigir_fiduciais.py).

O plugin do Candle vai fazer isto em JavaScript. Aqui fica a versao de
referencia, usada nos testes e como plano B pela linha de comando.
"""
import math
import re

CAM_DX, CAM_DY = 35.065, -6.000   # broca em (X, Y) => camera ve (X-35.065, Y+6)
TOL_DISTANCIA = 0.1

_COORD = re.compile(r'^(G[01]) X(-?\d+\.\d{3}) Y(-?\d+\.\d{3})(.*)$')


def visto_pela_camera(m):
    return (m[0] - CAM_DX, m[1] - CAM_DY)


def transformacao(desenho, real):
    """Giro + deslocamento (sem escala) que leva os 2 pontos de desenho aos 2 reais.
    Usa o ponto medio para dividir o erro entre os dois."""
    (a, b), (A, B) = desenho, real
    th = math.atan2(B[1] - A[1], B[0] - A[0]) - math.atan2(b[1] - a[1], b[0] - a[0])
    c, s = math.cos(th), math.sin(th)
    cd = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    cr = ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2)

    def f(x, y):
        x0, y0 = x - cd[0], y - cd[1]
        return (cr[0] + c * x0 - s * y0, cr[1] + s * x0 + c * y0)

    info = dict(giro_graus=math.degrees(th), dist_desenho=math.dist(a, b), dist_medida=math.dist(A, B),
                desloc=(cr[0] - cd[0], cr[1] - cd[1]), centro=f(0, 0))
    return f, info


def ajuste_rigido(origem, destino):
    """Giro + deslocamento de minimos quadrados entre pares de pontos (para conferencia)."""
    n = len(origem)
    ox = sum(p[0] for p in origem) / n
    oy = sum(p[1] for p in origem) / n
    dx = sum(p[0] for p in destino) / n
    dy = sum(p[1] for p in destino) / n
    sxx = sum((p[0] - ox) * (q[0] - dx) + (p[1] - oy) * (q[1] - dy) for p, q in zip(origem, destino))
    sxy = sum((p[0] - ox) * (q[1] - dy) - (p[1] - oy) * (q[0] - dx) for p, q in zip(origem, destino))
    th = math.atan2(sxy, sxx)
    c, s = math.cos(th), math.sin(th)

    def f(x, y):
        x0, y0 = x - ox, y - oy
        return (dx + c * x0 - s * y0, dy + s * x0 + c * y0)

    return f, math.degrees(th)


def aplicar(texto, f, titulo):
    """Aplica f em toda coordenada de placa (3 casas), tira a trava M0 do inicio."""
    out, trava = [], False
    for l in texto.split('\n'):
        if l.startswith('( ATENCAO: arquivo SEM correcao'):
            trava = True
            continue
        if trava and l == 'M0':
            trava = False
            continue
        if l.startswith('( FRESA fase=3') and 'corrigir=sim' in l:
            l = l.replace('corrigir=sim', 'corrigir=feito')
        m = _COORD.match(l)
        if m:
            x, y = f(float(m.group(2)), float(m.group(3)))
            l = f'{m.group(1)} X{x:.3f} Y{y:.3f}{m.group(4)}'
        out.append(l)
    out.insert(2, f'( {titulo} )')
    return '\n'.join(out)
