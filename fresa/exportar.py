"""Junta tudo: placa validada -> 1-cobre-cima.nc, 2-furos.nc, 3-cobre-baixo.nc e previas."""
import os
from dataclasses import dataclass

from shapely import affinity

from . import caminhos as cam
from . import gcode

PROIBIDA_TOL = 0.01    # mm: arredondamento de coordenadas na beira de uma area proibida

NOMES = ('1-cobre-cima.nc', '2-furos.nc', '3-cobre-baixo.nc')


@dataclass
class Resultado:
    arquivos: list
    previas: list
    caminhos_cima: list
    caminhos_baixo: list
    contorno_cima: list
    cruz_cima: tuple         # extremos do voo 1: x0, x1, y0, y1
    cruz_baixo: tuple
    contorno_baixo: list
    furos: list
    invasao_proibidas: dict  # lado -> quanto o corte mais fundo entra numa area proibida (mm)


def _invasao(proibidas, P):
    """Quanto o SULCO (nao so o centro da fresa) entra nas areas proibidas, em mm (0 = nada)."""
    from shapely.geometry import LineString, Point
    pior = 0.0
    linhas = [LineString(p) for p in P if len(p) > 1]
    for a in proibidas:
        dentro = a.buffer(-PROIBIDA_TOL)
        for ln in linhas:
            d = ln.distance(dentro)
            if d >= cam.MEIO_SULCO:
                continue
            if d > 0:
                pior = max(pior, cam.MEIO_SULCO - d)
            else:
                fundo = max((a.exterior.distance(Point(q)) for q in ln.coords if dentro.contains(Point(q))),
                            default=0.0)
                pior = max(pior, cam.MEIO_SULCO + fundo)
    return pior


def gerar(placa, relatorio, saida, previa=True, regra_v5=False):
    """regra_v5=True reproduz o gerador que fresou a v5: parava o CENTRO da fresa na beira das
    areas proibidas (o sulco entrava meio sulco nelas) e o pre-flight do arquivo 1 nao incluia
    os furos. So a prova usa, para comparar com os arquivos da v5."""
    sulco_fora = not regra_v5
    os.makedirs(saida, exist_ok=True)
    fid = relatorio.fiduciais
    fid_baixo = sorted([(-x, y) for x, y in fid])
    livre = placa.area_livre()
    if sulco_fora:
        livre = livre.buffer(-cam.MEIO_SULCO, cam.SEG_ISO)

    proibidas = placa.areas_proibidas()
    borda_c = cam.dono_da_borda(placa.F, placa.contorno, proibidas=proibidas)
    borda_b = cam.dono_da_borda(placa.B, placa.contorno, espelhar=True, proibidas=proibidas)
    # a regra antiga tambem parava o centro na beira para o lado do plano
    for b in (borda_c, borda_b):
        if b and not sulco_fora:
            b['proibidas'] = b['proibidas'].buffer(-cam.MEIO_SULCO, cam.SEG_ISO)
    # o lado de baixo e cortado espelhado: as areas proibidas tambem
    livre_b = livre if not placa.proibidas_extra else affinity.scale(livre, -1, 1, origin=(0, 0))
    cu_c, cu_b = cam.cobre(placa.F), cam.cobre(placa.B, espelhar=True)
    Pc = cam.isolacao(cu_c, livre, borda_c)
    Pb = cam.isolacao(cu_b, livre_b, borda_b)
    if sulco_fora:   # acabamento na beira das areas proibidas: tira os dentinhos entre as passadas
        Pc += cam.acabamento(cu_c, livre, borda_c)
        Pb += cam.acabamento(cu_b, livre_b, borda_b)
    Pc, Pb = cam.ordenar(Pc), cam.ordenar(Pb)

    pts = []
    for f in placa.furos:
        if all(abs(f.x - a) > 1e-3 or abs(f.y - b) > 1e-3 for a, b in pts):
            pts.append((f.x, f.y))
    furos = cam.ordenar_pontos(pts)

    nome = placa.nome.upper()
    # pre-flight do arquivo 1 inclui todos os furos: na placa tem que caber o desenho e os furos
    furos_voo = [] if regra_v5 else furos
    g1, H1, cruz1 = gcode.arquivo_cobre(placa, Pc, 1, fid,
                                        f'{nome}: fase 1, cobre de CIMA, com voos de teste e pausa no inicio',
                                        borda_c and borda_c['rede'], furos_voo)
    g2 = gcode.arquivo_furos(placa, furos, fid, f'{nome}: fase 2, {len(furos)} furos')
    g3, H3, cruz3 = gcode.arquivo_cobre(placa, Pb, 3, fid_baixo,
                                 f'{nome}: fase 3, cobre de BAIXO, placa virada como pagina de livro',
                                 borda_b and borda_b['rede'])
    arquivos = []
    for n, G in zip(NOMES, (g1, g2, g3)):
        gcode.conferir(G)
        c = os.path.join(saida, n)
        with open(c, 'w', encoding='ascii', newline='\n') as fh:
            fh.write('\n'.join(G) + '\n')
        arquivos.append(c)

    res = Resultado(arquivos, [], Pc, Pb, H1, cruz1, cruz3, H3, furos,
                    {'cima': _invasao(proibidas, Pc),
                     'baixo': _invasao([affinity.scale(a, -1, 1, origin=(0, 0)) for a in proibidas], Pb)})
    if previa:
        from . import previa as pv
        res.previas = pv.desenhar(placa, res, fid, saida)
    return res
