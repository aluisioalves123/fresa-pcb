"""Corrige um G-code para a posicao real da placa, a partir de 2 pontos de referencia.
desenho: posicao dos 2 pontos no arquivo (ja espelhada se a placa foi virada)
medido:  X,Y do Candle com o ponto centralizado na mira da camera
"""
import re, math, sys
CAM_DX, CAM_DY = 35.065, -6.000   # broca em (X,Y) => camera ve (X-35.065, Y+6)

def real(m): return (m[0] - CAM_DX, m[1] - CAM_DY)

def transformacao(desenho, medido):
    (a, b), (A, B) = desenho, [real(m) for m in medido]
    ang_d = math.atan2(b[1]-a[1], b[0]-a[0]); ang_r = math.atan2(B[1]-A[1], B[0]-A[0])
    th = ang_r - ang_d
    c, s = math.cos(th), math.sin(th)
    # centroide para dividir o erro entre os dois pontos
    cd = ((a[0]+b[0])/2, (a[1]+b[1])/2); cr = ((A[0]+B[0])/2, (A[1]+B[1])/2)
    def f(x, y):
        x0, y0 = x-cd[0], y-cd[1]
        return (cr[0] + c*x0 - s*y0, cr[1] + s*x0 + c*y0)
    info = dict(giro_graus=math.degrees(th), dist_desenho=math.dist(a, b), dist_medida=math.dist(A, B),
                desloc=(cr[0]-cd[0], cr[1]-cd[1]))
    return f, info

def aplica(entrada, saida, f, titulo):
    out = []
    for l in open(entrada).read().split('\n'):
        m = re.match(r'^(G[01]) X(-?[\d.]+) Y(-?[\d.]+)(.*)$', l)
        if m and l.strip() != 'G0 X0 Y0':
            x, y = f(float(m.group(2)), float(m.group(3)))
            l = f"{m.group(1)} X{x:.3f} Y{y:.3f}{m.group(4)}"
        out.append(l)
    out.insert(1, f"( {titulo} )")
    open(saida, 'w').write('\n'.join(out))
