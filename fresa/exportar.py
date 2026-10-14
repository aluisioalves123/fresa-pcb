"""Junta tudo: placa validada -> 1-cobre-cima.nc, 2-furos.nc, 3-cobre-baixo.nc e previas."""
import os
from dataclasses import dataclass

from . import caminhos as cam
from . import gcode

NOMES = ('1-cobre-cima.nc', '2-furos.nc', '3-cobre-baixo.nc')


@dataclass
class Resultado:
    arquivos: list
    previas: list
    caminhos_cima: list
    caminhos_baixo: list
    contorno_cima: list
    contorno_baixo: list
    furos: list
    invasao_garras: dict     # lado -> maior entrada de ponto de corte no triangulo (mm)


def _invasao(placa, P):
    """Quanto a ponta entra nos triangulos das garras (0 = nada)."""
    x0, y0, x1, y1 = placa.limites
    g = 11.0
    pior = 0.0
    for p in P:
        for x, y in p:
            for v in (x + y - (x1 + y1 - g), -x + y - (-x0 + y1 - g),
                      -x - y - (-x0 - y0 - g), x - y - (x1 - y0 - g)):
                pior = max(pior, v / 2 ** 0.5)
    return pior


def gerar(placa, relatorio, saida, previa=True):
    os.makedirs(saida, exist_ok=True)
    fid = relatorio.fiduciais
    fid_baixo = sorted([(-x, y) for x, y in fid])
    livre = placa.area_livre()

    Pc = cam.ordenar(cam.isolacao(cam.cobre(placa.F), livre))
    Pb = cam.ordenar(cam.isolacao(cam.cobre(placa.B, espelhar=True), livre))

    pts = []
    for f in placa.furos:
        if all(abs(f.x - a) > 1e-3 or abs(f.y - b) > 1e-3 for a, b in pts):
            pts.append((f.x, f.y))
    furos = cam.ordenar_pontos(pts)

    nome = placa.nome.upper()
    g1, H1 = gcode.arquivo_cobre(placa, Pc, 1, fid,
                                 f'{nome}: fase 1, cobre de CIMA, com voos de teste e pausa no inicio')
    g2 = gcode.arquivo_furos(placa, furos, fid, f'{nome}: fase 2, {len(furos)} furos')
    g3, H3 = gcode.arquivo_cobre(placa, Pb, 3, fid_baixo,
                                 f'{nome}: fase 3, cobre de BAIXO, placa virada como pagina de livro')
    arquivos = []
    for n, G in zip(NOMES, (g1, g2, g3)):
        gcode.conferir(G)
        c = os.path.join(saida, n)
        with open(c, 'w', encoding='ascii', newline='\n') as fh:
            fh.write('\n'.join(G) + '\n')
        arquivos.append(c)

    res = Resultado(arquivos, [], Pc, Pb, H1, H3, furos,
                    {'cima': _invasao(placa, Pc), 'baixo': _invasao(placa, Pb)})
    if previa:
        from . import previa as pv
        res.previas = pv.desenhar(placa, res, fid, saida)
    return res
