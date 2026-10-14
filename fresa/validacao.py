"""Validacoes antes de exportar (secao 4.2 da especificacao).

Modelo eletrico de placa caseira sem furo metalizado:
- o pino de componente e soldado so embaixo, entao o pad de cima nao liga em nada;
- a via e um fio soldado dos dois lados, entao so ela liga cima com baixo.
"""
from dataclasses import dataclass, field

from shapely.geometry import MultiPolygon, Point, box
from shapely.ops import unary_union

BROCA = 0.8
VAO_MIN = 0.40
BORDA_MIN = 1.0
FIDUCIAL_LIVRE = 1.0   # meia largura da area 2x2 sem cobre em volta do fiducial
TOL = 1e-3
R_FRESA = 0.35 / 2    # meia largura da 1a passada (caminhos.R)


@dataclass
class Relatorio:
    erros: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    info: list = field(default_factory=list)
    fiduciais: list = field(default_factory=list)   # [(x, y) esquerda, (x, y) direita]

    def erro(self, m):
        self.erros.append(m)

    def aviso(self, m):
        self.avisos.append(m)

    @property
    def ok(self):
        return not self.erros

    def como_dict(self):
        return dict(erros=self.erros, avisos=self.avisos, info=self.info, fiduciais=self.fiduciais)


def _rede_valida(n):
    return bool(n) and not n.startswith('unconnected-') and n != 'N/C'


def _polys(g):
    return [p for p in (g.geoms if isinstance(g, MultiPolygon) else [g]) if not p.is_empty]


def _onde(g):
    p = g.representative_point()
    return f'X{p.x:.2f} Y{p.y:.2f}'


def _ilhas(elementos):
    """Ilhas de cobre de uma camada e quais elementos caem em cada uma."""
    ilhas = _polys(unary_union([e.geom for e in elementos]))
    membros = [[] for _ in ilhas]
    for e in elementos:
        pt = e.geom.representative_point()
        for i, il in enumerate(ilhas):
            if il.intersects(pt):
                membros[i].append(e)
                break
    return ilhas, membros


def achar_fiduciais(placa, rel):
    npth = placa.furos_npth()
    pares = []
    for i in range(len(npth)):
        for j in range(i + 1, len(npth)):
            a, b = sorted((npth[i], npth[j]), key=lambda f: f.x)
            if abs(a.y - b.y) <= 0.01 and a.x < 0 < b.x:
                pares.append((a, b))
    if len(pares) != 1:
        if not npth:
            rel.erro('fiduciais: nenhum furo NPTH. Coloque 2 Fiducial_Furo_0.8, no meio das '
                     'bordas esquerda e direita, na mesma altura Y')
        elif not pares:
            rel.erro('fiduciais: nenhum par de furos NPTH na mesma altura Y, um de cada lado do centro. '
                     'Furos NPTH: ' + ', '.join(f'X{f.x:.2f} Y{f.y:.2f}' for f in npth))
        else:
            rel.erro('fiduciais: mais de um par possivel, deixe so 2 furos NPTH alinhados em Y. '
                     'Furos NPTH: ' + ', '.join(f'X{f.x:.2f} Y{f.y:.2f}' for f in npth))
        return None
    a, b = pares[0]
    if len(npth) > 2:
        rel.aviso(f'{len(npth) - 2} furo(s) NPTH alem dos fiduciais')
    rel.fiduciais = [(a.x, a.y), (b.x, b.y)]
    rel.info.append(f'fiduciais em X{a.x:.3f} Y{a.y:.3f} e X{b.x:.3f} Y{b.y:.3f}, '
                    f'distancia {b.x - a.x:.3f} mm')
    return a, b


def validar(placa):
    rel = Relatorio()
    for m in placa.avisos_leitura:
        rel.aviso(m)
    rel.info.append(f'placa {placa.largura:.2f} x {placa.altura:.2f} mm')
    if placa.info_origem:
        rel.info.append(placa.info_origem)

    camadas = {'cima': placa.F, 'baixo': placa.B}
    if not any(e.rede for e in placa.F + placa.B) or not any(e.funcao for e in placa.F + placa.B):
        rel.erro('os Gerbers vieram sem os atributos X2 de rede e de funcao: no KiCad, exporte com '
                 '"Usar formato X2" e "Incluir atributos de netlist" ligados')
        return rel

    # trilha de cima encostando em pad de componente (regra: solda so embaixo)
    pads_cima = [e for e in placa.F if e.funcao == 'ComponentPad']
    outros_cima = [e for e in placa.F if e.funcao != 'ComponentPad']
    for t in outros_cima:
        for p in pads_cima:
            if t.geom.intersects(p.geom):
                o = 'trilha' if t.funcao == 'Conductor' else 'cobre'
                rel.erro(f'{o} de cima encostando no pino {p.ref or "?"} da rede {t.rede} '
                         f'em {_onde(t.geom.intersection(p.geom))}: solda e so do lado de baixo, '
                         f'ligue por baixo ou por uma via')

    # ilhas, curtos e conectividade
    ilhas = {}
    for lado, L in camadas.items():
        il, mem = _ilhas(L)
        ilhas[lado] = []
        for g, es in zip(il, mem):
            redes = {e.rede for e in es if _rede_valida(e.rede)}
            if len(redes) > 1:
                rel.erro(f'curto no cobre de {lado} entre as redes {", ".join(sorted(redes))} '
                         f'perto de {_onde(g)}')
            so_pad = all(e.funcao == 'ComponentPad' for e in es)
            ilhas[lado].append((g, redes, so_pad and lado == 'cima'))

    vias = [(e.pos, e.rede) for e in placa.F + placa.B if e.funcao == 'ViaPad' and e.pos]
    vias += [((f.x, f.y), None) for f in placa.furos if f.funcao == 'via']
    pai = {}

    def ach(k):
        while pai.setdefault(k, k) != k:
            pai[k] = pai[pai[k]]
            k = pai[k]
        return k

    def ilha_em(lado, pt):
        for i, (g, redes, ignora) in enumerate(ilhas[lado]):
            if not ignora and g.intersects(Point(pt)):
                return (lado, i)
        return None

    for pos, _ in vias:
        a, b = ilha_em('cima', pos), ilha_em('baixo', pos)
        if a and b:
            pai[ach(a)] = ach(b)

    por_rede = {}
    for lado in camadas:
        for i, (g, redes, ignora) in enumerate(ilhas[lado]):
            if ignora:
                continue
            for n in redes:
                por_rede.setdefault(n, []).append((lado, i))
    for n, nos in sorted(por_rede.items()):
        grupos = {}
        for k in nos:
            grupos.setdefault(ach(k), []).append(k)
        if len(grupos) > 1:
            locais = ['; '.join(f'{lado} {_onde(ilhas[lado][i][0])}' for lado, i in gs)
                      for gs in grupos.values()]
            rel.erro(f'rede {n} partida em {len(grupos)} pedacos (ligacao nao roteada ou via faltando): '
                     + ' | '.join(locais))
    rel.info.append(f'{len(por_rede)} redes, '
                    + ', '.join(f'{len([x for x in ilhas[l] if not x[2]])} ilhas em {l}' for l in camadas))

    # vao entre redes
    for lado, L in camadas.items():
        por = {}
        for e in L:
            if _rede_valida(e.rede):
                por.setdefault(e.rede, []).append(e.geom)
        U = {n: unary_union(v) for n, v in por.items()}
        ns = sorted(U)
        pior = None
        for i in range(len(ns)):
            for j in range(i + 1, len(ns)):
                d = U[ns[i]].distance(U[ns[j]])
                pior = d if pior is None else min(pior, d)
                if 0 < d < VAO_MIN - TOL:
                    rel.aviso(f'vao de {d:.3f} mm no cobre de {lado} entre {ns[i]} e {ns[j]}, '
                              f'a fresa pode nao separar (minimo {VAO_MIN})')
        if pior is not None:
            rel.info.append(f'menor vao entre redes no cobre de {lado}: {pior:.3f} mm')

    # furos
    dif = [f for f in placa.furos if abs(f.diametro - BROCA) > TOL]
    if dif:
        rel.aviso(f'{len(dif)} furo(s) com diametro diferente de {BROCA}, serao feitos com a broca '
                  f'{BROCA}: ' + ', '.join(f'{f.diametro:.2f} em X{f.x:.2f} Y{f.y:.2f}' for f in dif))

    # fiduciais
    fid = achar_fiduciais(placa, rel)
    tudo = unary_union([e.geom for e in placa.F + placa.B])
    if fid:
        for f in fid:
            q = box(f.x - FIDUCIAL_LIVRE, f.y - FIDUCIAL_LIVRE, f.x + FIDUCIAL_LIVRE, f.y + FIDUCIAL_LIVRE)
            if tudo.intersects(q):
                rel.aviso(f'tem cobre na area 2x2 mm do fiducial X{f.x:.2f} Y{f.y:.2f}, '
                          f'a camera pode confundir')

    # garras e borda
    for t in placa.triangulos_garras():
        inter = tudo.intersection(t)
        if inter.area > 1e-6:
            rel.erro(f'cobre dentro do triangulo de {11:.0f} mm da garra perto de {_onde(inter)}')
        elif tudo.buffer(R_FRESA, 32).intersection(t).area > 1e-6:
            rel.aviso(f'a primeira passada da fresa encosta no triangulo da garra perto de {_onde(t)}')
    perto = tudo.difference(placa.contorno.buffer(-BORDA_MIN, 32))
    if perto.area > 1e-6:
        rel.aviso(f'cobre a menos de {BORDA_MIN} mm da borda perto de {_onde(perto)}')
    return rel
