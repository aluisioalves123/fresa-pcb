"""Carrega os arquivos exportados pelo KiCad e monta a placa com origem no centro."""
import glob
import os
from dataclasses import dataclass, field

from shapely import affinity
from shapely.geometry import Polygon

from . import excellon, gerber

GARRA = 11.0          # perna do triangulo proibido em cada canto (mm)
SUFIXOS = {
    'F': 'F_Cu.gbr',
    'B': 'B_Cu.gbr',
    'borda': 'Edge_Cuts.gbr',
    'pth': 'PTH.drl',
    'npth': 'NPTH.drl',
}


class ErroArquivos(Exception):
    pass


@dataclass
class Placa:
    nome: str
    contorno: Polygon
    F: list
    B: list
    furos: list
    avisos_leitura: list = field(default_factory=list)
    deslocamento: tuple = (0.0, 0.0)   # quanto foi somado para centralizar
    info_origem: str | None = None

    @property
    def limites(self):
        return self.contorno.bounds

    @property
    def largura(self):
        x0, y0, x1, y1 = self.limites
        return x1 - x0

    @property
    def altura(self):
        x0, y0, x1, y1 = self.limites
        return y1 - y0

    def area_livre(self, margem_extra=0.0):
        """Regiao fora dos 4 triangulos das garras: intersecao de 4 semiplanos.

        Na placa 30x30 centrada vira o losango |x|+|y| <= 19 da referencia.
        Nao e recortada pela borda, de proposito (igual a v5).
        """
        x0, y0, x1, y1 = self.limites
        g = GARRA + margem_extra
        big = 1000.0
        cortes = [   # (sx, sy, lim): semiplano sx*x + sy*y <= lim, um por canto
            (1, 1, x1 + y1 - g), (-1, 1, -x0 + y1 - g),
            (-1, -1, -x0 - y0 - g), (1, -1, x1 - y0 - g),
        ]
        reg = Polygon([(-big, -big), (big, -big), (big, big), (-big, big)])
        for sx, sy, lim in cortes:
            reg = reg.intersection(_semiplano(sx, sy, lim, big))
        return reg

    def triangulos_garras(self):
        x0, y0, x1, y1 = self.limites
        g = GARRA
        return [
            Polygon([(x1, y1), (x1 - g, y1), (x1, y1 - g)]),
            Polygon([(x0, y1), (x0 + g, y1), (x0, y1 - g)]),
            Polygon([(x0, y0), (x0 + g, y0), (x0, y0 + g)]),
            Polygon([(x1, y0), (x1 - g, y0), (x1, y0 + g)]),
        ]

    def furos_npth(self):
        return [f for f in self.furos if f.funcao == 'npth']


def _semiplano(sx, sy, lim, big):
    """Poligono grande do semiplano sx*x + sy*y <= lim, com sx, sy em {-1, 1}."""
    # reta: sy*y = lim - sx*x ; pega dois pontos nela e fecha do lado permitido
    ys = lambda x: (lim - sx * x) / sy
    a, b = (-big, ys(-big)), (big, ys(big))
    lado = -sy * 4 * big   # deslocamento em y para o lado permitido
    return Polygon([a, b, (b[0], b[1] + lado), (a[0], a[1] + lado)])


def achar_prefixos(pasta):
    """Prefixos que tem todos os arquivos necessarios na pasta."""
    achados = {}
    for chave, suf in SUFIXOS.items():
        for f in glob.glob(os.path.join(pasta, '*' + suf)):
            achados.setdefault(os.path.basename(f)[:-len(suf)], set()).add(chave)
    obrig = {'F', 'B', 'borda', 'pth'}
    return sorted(p for p, ch in achados.items() if obrig <= ch)


def carregar(pasta, prefixo=None):
    if prefixo is None:
        ps = achar_prefixos(pasta)
        if not ps:
            raise ErroArquivos(f'nenhum conjunto completo F_Cu, B_Cu, Edge_Cuts e PTH em {pasta}')
        if len(ps) > 1:
            raise ErroArquivos('mais de um projeto na pasta, escolha um com --prefixo: '
                               + ' | '.join(repr(p) for p in ps))
        prefixo = ps[0]
    arq = {k: os.path.join(pasta, prefixo + s) for k, s in SUFIXOS.items()}
    for k in ('F', 'B', 'borda', 'pth'):
        if not os.path.exists(arq[k]):
            raise ErroArquivos(f'arquivo nao encontrado: {arq[k]}')

    contorno = gerber.ler_contorno(arq['borda'])
    F = gerber.ler(arq['F'])
    B = gerber.ler(arq['B'])
    furos, avisos = excellon.ler(arq['pth'])
    if os.path.exists(arq['npth']):
        f2, a2 = excellon.ler(arq['npth'], npth=True)
        furos += f2
        avisos += a2

    # origem = centro do contorno
    x0, y0, x1, y1 = contorno.bounds
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    desloc = (0.0, 0.0)
    info = None
    if abs(cx) > 1e-3 or abs(cy) > 1e-3:
        desloc = (-cx, -cy)
        info = (f'a origem dos arquivos nao estava no centro da placa, '
                f'tudo foi deslocado X{-cx:+.3f} Y{-cy:+.3f}')
        contorno = affinity.translate(contorno, -cx, -cy)
        for L in (F, B):
            for e in L:
                e.geom = affinity.translate(e.geom, -cx, -cy)
                if e.pos:
                    e.pos = (e.pos[0] - cx, e.pos[1] - cy)
        for f in furos:
            f.x -= cx
            f.y -= cy
    nome = prefixo.rstrip('-_ ') or 'placa'
    return Placa(nome, contorno, F, B, furos, avisos, desloc, info)
