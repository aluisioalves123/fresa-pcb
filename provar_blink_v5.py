"""Prova de que o nucleo reproduz os arquivos que fresaram a blink v5.

  .venv\\Scripts\\python provar_blink_v5.py [pasta-gerber]

Compara o que o nucleo gera com referencias/exemplo-*.nc e com o gerador
original (referencias/gerar_gcode_v5_gen5.py) rodado agora, na mesma maquina.
Escreve prova/RELATORIO.md e os arquivos gerados em prova/gcode/.
"""
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

import shapely
from shapely.geometry import LineString

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from fresa import corrigir, exportar, placa, validacao  # noqa: E402

GERBER = os.path.join(AQUI, 'testes', 'dados', 'blink-v5')
PREFIXO = 'blink blink-roteado-'
REF = os.path.join(AQUI, 'referencias')
TOL_CORTE = 0.05      # mm: diferenca aceitavel entre caminhos (versao do GEOS)


def ler_cortes(caminho):
    """Caminhos de corte de um .nc: cada um comeca no G0 antes do mergulho."""
    L = open(caminho).read().split('\n')
    i = L.index('M3 S1000')
    P, cur, ult = [], None, None
    for l in L[i:]:
        m = re.match(r'^G([01]) X(-?[\d.]+) Y(-?[\d.]+)', l)
        if m:
            pt = (float(m.group(2)), float(m.group(3)))
            if m.group(1) == '0':
                ult = pt
            elif cur is not None:
                cur.append(pt)
            continue
        if l.startswith('G1 Z-'):
            cur = [ult]
        elif l.startswith('G0 Z') and cur is not None:
            P.append(cur)
            cur = None
    return P


def ler_bloco(caminho, ini, fim):
    L = open(caminho).read().split('\n')
    a = next(k for k, l in enumerate(L) if l.startswith(ini))
    b = next(k for k in range(a + 1, len(L)) if L[k].startswith(fim))
    return L[a:b]


def pontos_voo2(caminho):
    B = ler_bloco(caminho, '( VOO 2', '( PAUSA')
    return [(float(m.group(1)), float(m.group(2)))
            for l in B for m in [re.match(r'^G[01] X(-?[\d.]+) Y(-?[\d.]+)', l)] if m]


def pontos_voo1(caminho):
    B = ler_bloco(caminho, '( VOO 1', '( VOO 2')
    return [(float(m.group(1)), float(m.group(2)))
            for l in B for m in [re.match(r'^G[01] X(-?[\d.]+) Y(-?[\d.]+)', l)] if m]


def comparar(A, B):
    """Caminho a caminho: maior desvio (Hausdorff) e quantos sao identicos."""
    pior, iguais = 0.0, 0
    for a, b in zip(A, B):
        d = LineString(a).hausdorff_distance(LineString(b)) if len(a) > 1 and len(b) > 1 else math.dist(a[0], b[0])
        pior = max(pior, d)
        iguais += a == b
    return pior, iguais


def rodar_gerador_original(tmp):
    """Roda o gerador da v5 sem mudar a logica: so troca o caminho dos Gerbers."""
    chk = open(os.path.join(REF, 'validar_gerbers_check.py')).read()
    u = 'U = ' + repr(os.path.join(os.path.abspath(GERBER), PREFIXO))
    chk = re.sub(r"^U = .*$", lambda m: u, chk, count=1, flags=re.M)
    open(os.path.join(tmp, 'check.py'), 'w').write(chk)
    shutil.copy(os.path.join(REF, 'gerar_gcode_v5_gen5.py'), tmp)
    r = subprocess.run([sys.executable, 'gerar_gcode_v5_gen5.py'], cwd=tmp, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit('gerador original falhou:\n' + r.stderr)
    return os.path.join(tmp, 'out')


def main():
    gerber = sys.argv[1] if len(sys.argv) > 1 else GERBER
    saida = os.path.join(AQUI, 'prova', 'gcode')
    p = placa.carregar(gerber, PREFIXO)
    rel = validacao.validar(p)
    # para comparar com a v5: a regra dela parava o centro da fresa na beira das areas proibidas
    res = exportar.gerar(p, rel, os.path.join(saida, 'regra-v5'), sulco_fora=False)
    nc1, nc2, nc3 = res.arquivos
    # o que o nucleo gera hoje: a beira do sulco, e nao o centro, para na area proibida
    novo = exportar.gerar(p, rel, saida)
    linhas, ok_geral = [], True

    def item(ok, texto):
        nonlocal ok_geral
        ok_geral &= bool(ok)
        linhas.append(f'- {"OK" if ok else "FALHOU"}: {texto}')

    linhas += ['# Prova: o nucleo reproduz a blink v5', '',
               f'Gerbers: `{os.path.relpath(gerber, AQUI)}` (prefixo `{PREFIXO}`)  ',
               f'shapely {shapely.__version__}, GEOS {shapely.geos_version_string}', '',
               '## Validacao', '']
    item(rel.ok, f'nenhum erro de validacao ({len(rel.erros)} erros)')
    linhas += [f'  - info: {m}' for m in rel.info] + [f'  - aviso: {m}' for m in rel.avisos]

    with tempfile.TemporaryDirectory() as tmp:
        orig = rodar_gerador_original(tmp)
        o1 = ler_cortes(os.path.join(orig, '1-cobre-cima.nc'))
        o4 = ler_cortes(os.path.join(orig, '4-cobre-baixo-SEM-CORRECAO.nc'))
        furos_orig = set()
        for n in ('2-furos-componentes-e-vias.nc', '3-furos-conector-e-fiduciais.nc'):
            furos_orig |= set(re.findall(r'^G0 (X-?[\d.]+ Y-?[\d.]+)$',
                                         open(os.path.join(orig, n)).read(), re.M)) - {'X0 Y0'}

    # 1. cobre de cima
    c1, e1 = ler_cortes(nc1), ler_cortes(os.path.join(REF, 'exemplo-1-cobre-cima.nc'))
    linhas += ['', '## Arquivo 1, cobre de cima', '']
    item(c1 == o1, f'cortes identicos, ponto a ponto, ao gerador original rodado agora '
                   f'({len(c1)} caminhos, {sum(map(len, c1))} pontos)')
    pior, iguais = comparar(c1, e1)
    item(len(c1) == len(e1) and pior <= TOL_CORTE,
         f'contra exemplo-1-cobre-cima.nc: {len(c1)} x {len(e1)} caminhos, mesma ordem, '
         f'{iguais} identicos, maior desvio {pior:.3f} mm (limite {TOL_CORTE})')
    v1, ve1 = pontos_voo1(nc1), pontos_voo1(os.path.join(REF, 'exemplo-1-cobre-cima.nc'))
    item(v1 == ve1, 'voo 1 em cruz com os mesmos 4 extremos do exemplo: '
                    + ', '.join(f'({x:.3f}, {y:.3f})' for x, y in v1))
    h1, he1 = pontos_voo2(nc1), pontos_voo2(os.path.join(REF, 'exemplo-1-cobre-cima.nc'))
    item(h1 == he1, f'voo 2 no contorno com os mesmos {len(h1) - 1} vertices do exemplo')

    # 2. furos
    linhas += ['', '## Arquivo 2, furos', '']
    f2 = set(re.findall(r'^G0 (X-?[\d.]+ Y-?[\d.]+)$', open(nc2).read(), re.M)) - {'X0 Y0', 'X0.000 Y0.000'}
    fe2 = set(re.findall(r'^G0 (X-?[\d.]+ Y-?[\d.]+)$',
                         open(os.path.join(REF, 'exemplo-2-furos.nc')).read(), re.M)) - {'X0 Y0'}
    item(fe2 <= f2, f'os {len(fe2)} furos de exemplo-2-furos.nc estao todos no arquivo 2')
    item(f2 == furos_orig, f'{len(f2)} furos = os 3 arquivos de furo do gerador original juntos '
                           f'(componentes e vias + conector + 2 fiduciais), agora numa broca so')
    ciclo = ler_bloco(nc2, 'G0 X-1.000 Y-1.000', 'G0 X')
    ciclo_e = ler_bloco(os.path.join(REF, 'exemplo-2-furos.nc'), 'G0 X-1.000 Y-1.000', 'G0 X')
    item(ciclo == ciclo_e, 'ciclo de furacao identico ao exemplo: ' + ' / '.join(ciclo[1:]))

    # 3. cobre de baixo
    linhas += ['', '## Arquivo 3, cobre de baixo', '']
    c3 = ler_cortes(nc3)
    e4 = ler_cortes(os.path.join(REF, 'exemplo-4-cobre-baixo-CORRIGIDO.nc'))
    item(c3 == o4, f'cortes identicos ao 4-cobre-baixo-SEM-CORRECAO do gerador original '
                   f'({len(c3)} caminhos, espelhado em X)')
    # acha o giro e deslocamento que a camera aplicou, a partir do inicio de cada caminho
    f, giro = corrigir.ajuste_rigido([p[0] for p in c3], [p[0] for p in e4])
    cx, cy = f(0, 0)
    item(len(c3) == len(e4), f'{len(c3)} x {len(e4)} caminhos contra exemplo-4-cobre-baixo-CORRIGIDO.nc')
    cab = open(os.path.join(REF, 'exemplo-4-cobre-baixo-CORRIGIDO.nc')).read().split('\n')[1]
    item(abs(giro - 1.10) < 0.01 and abs(cx + 1.16) < 0.01 and abs(cy + 4.95) < 0.01,
         f'correcao que leva o arquivo 3 ao exemplo-4: giro {giro:.3f} graus, centro X{cx:.3f} Y{cy:.3f}; '
         f'o exemplo diz `{cab}`')
    # agora aplica a correcao pelo caminho real: fiduciais medidos -> transformacao -> arquivo
    fid = [(-13.0, 0.0), (13.0, 0.0)]
    medido = [(x + corrigir.CAM_DX, y + corrigir.CAM_DY) for x, y in (f(*q) for q in fid)]
    g, info = corrigir.transformacao(fid, [corrigir.visto_pela_camera(m) for m in medido])
    texto = corrigir.aplicar(open(nc3).read(), g, 'teste')
    nc3c = os.path.join(saida, '3-cobre-baixo-CORRIGIDO-como-na-v5.nc')
    open(nc3c, 'w', newline='\n').write(texto)
    c3c = ler_cortes(nc3c)
    pior, _ = comparar(c3c, e4)
    item(len(c3c) == len(e4) and pior <= TOL_CORTE,
         f'arquivo 3 corrigido pelos fiduciais (camera em '
         + ' e '.join(f'X{m[0]:.3f} Y{m[1]:.3f}' for m in medido)
         + f') contra o exemplo-4: maior desvio {pior:.3f} mm')
    item('M0' not in texto.split('( PAUSA')[0].split('\n')[:6] and 'corrigir=feito' in texto,
         'a correcao tira a trava M0 do inicio e marca corrigir=feito')

    # regras de G-code
    linhas += ['', '## Regras de G-code', '']
    for c in res.arquivos:
        L = open(c).read().split('\n')
        ok = (all(l.isascii() for l in L) and L[0].startswith('( FRESA fase=')
              and 'G53 G0 Z-2' in L and L[-5:-1] == ['G53 G0 Z-2', 'M5', 'G0 X0 Y0', 'M30']
              and not any(re.match(r'^G0 Z(1\d|[5-9]\d*)', l) and l != 'G0 Z5' for l in L))
        item(ok, f'{os.path.basename(c)}: cabecalho FRESA, ASCII, inicio e fim padrao, sem Z alto')
    linhas += ['', '## Areas proibidas', '']
    v = res.invasao_proibidas
    linhas.append(f'- na regra da v5, o sulco entrava ate {max(v.values()):.3f} mm nas areas proibidas '
                  f'(o centro da fresa parava na beira)')
    # a 1a passada isola o cobre e nao pode ser recortada: se encostar, a validacao avisa
    from fresa import caminhos as cm
    from shapely.geometry import Point as _P
    um = {'cima': cm.cobre(p.F).buffer(cm.R, cm.SEG_ISO).simplify(cm.SIMPLIFICA).boundary,
          'baixo': cm.cobre(p.B, True).buffer(cm.R, cm.SEG_ISO).simplify(cm.SIMPLIFICA).boundary}
    from shapely import affinity as _af
    for lado, P in (('cima', novo.caminhos_cima), ('baixo', novo.caminhos_baixo)):
        areas = p.areas_proibidas() if lado == 'cima' else             [_af.scale(a, -1, 1, origin=(0, 0)) for a in p.areas_proibidas()]
        outras = [q for q in P if max(um[lado].distance(_P(v)) for v in q) > 0.02]
        primeira = [q for q in P if q not in outras]
        inv_outras = exportar._invasao(areas, outras)
        inv_1a = exportar._invasao(areas, primeira)
        item(inv_outras < 1e-3, f'{lado}: nenhuma passada recortavel entra nas areas proibidas ({inv_outras:.3f} mm)')
        avisou = any(f'primeira passada no cobre de {lado}' in m for m in rel.avisos)
        item(inv_1a < 1e-3 or avisou, f'{lado}: a 1a passada, que isola o cobre, entra {inv_1a:.3f} mm'
             + (' e a validacao avisa' if avisou else ''))
    perdidos = len(c1) - len(ler_cortes(novo.arquivos[0]))
    linhas.append(f'- os caminhos de corte do arquivo 1 so mudam onde as passadas 2 a 4 encostavam nas areas: '
                  f'{len(ler_cortes(novo.arquivos[0]))} caminhos contra {len(c1)}')

    linhas += ['', '## Resultado', '', '**TUDO OK**' if ok_geral else '**HOUVE FALHAS**', '',
               'Arquivos gerados em `prova/gcode/` (regra atual) e `prova/gcode/regra-v5/` (regra da v5, usada na comparacao).']
    os.makedirs(os.path.join(AQUI, 'prova'), exist_ok=True)
    open(os.path.join(AQUI, 'prova', 'RELATORIO.md'), 'w', encoding='utf-8').write('\n'.join(linhas) + '\n')
    print('\n'.join(linhas))
    return 0 if ok_geral else 1


if __name__ == '__main__':
    sys.exit(main())
