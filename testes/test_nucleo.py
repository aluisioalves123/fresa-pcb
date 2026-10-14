"""Testes do nucleo. Rode na pasta fresa-pcb:  .venv\\Scripts\\python -m pytest testes

Usa os Gerbers da blink v5 e versoes estragadas de proposito deles.
"""
import os
import re
import shutil
import subprocess
import sys

import pytest
from shapely.geometry import LineString

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
from fresa import cli, exportar, gcode, placa, validacao  # noqa: E402

GERBER = os.path.join(AQUI, 'dados', 'blink-v5')
PRE = 'blink blink-roteado-'

pytestmark = pytest.mark.skipif(not os.path.isdir(GERBER), reason='Gerbers da blink nao encontrados')


@pytest.fixture
def pasta(tmp_path):
    for f in os.listdir(GERBER):
        if f.startswith(PRE):
            shutil.copy(os.path.join(GERBER, f), tmp_path)
    return tmp_path


def editar(pasta, sufixo, fn):
    c = os.path.join(pasta, PRE + sufixo)
    t = open(c).read()
    novo = fn(t)
    assert novo != t, 'a edicao do teste nao mudou nada'
    open(c, 'w').write(novo)


def antes_do_fim(extra):
    return lambda t: t.replace('M02*', extra + 'M02*')


def validar(pasta):
    return validacao.validar(placa.carregar(str(pasta), PRE))


def tem(lista, trecho):
    return any(trecho in m for m in lista)


def test_blink_sem_erros(pasta):
    r = validar(pasta)
    assert r.erros == []
    assert len(r.avisos) == 3 and 'diferente de 0.8' in r.avisos[0]
    # o pad do R4 fica a 0,26 mm do canto proibido: o sulco que o isola encosta nele, nos dois lados
    assert tem(r.avisos, 'primeira passada no cobre de cima') and tem(r.avisos, 'primeira passada no cobre de baixo')
    assert r.fiduciais == [(-13.0, 0.0), (13.0, 0.0)]


def test_rede_partida(pasta):
    editar(pasta, 'B_Cu.gbr', lambda t: t.replace('X4075000Y-12575000D02*\nX-5225000Y-12575000D01*\n', ''))
    r = validar(pasta)
    assert tem(r.erros, 'rede Net-(D2-K) partida em 2 pedacos')


def test_curto(pasta):
    editar(pasta, 'B_Cu.gbr', antes_do_fim(
        '%TO.N,GND*%\nD13*\nX1875000Y-6775000D02*\nX1875000Y-12575000D01*\n%TD*%\n'))
    r = validar(pasta)
    assert tem(r.erros, 'curto no cobre de baixo')


def test_trilha_de_cima_no_pino(pasta):
    editar(pasta, 'F_Cu.gbr', antes_do_fim(
        '%TO.N,Net-(D1-K)*%\nD13*\nX-1000000Y-1000000D02*\nX-1000000Y-3500000D01*\n%TD*%\n'))
    r = validar(pasta)
    assert tem(r.erros, 'trilha de cima encostando no pino R2')


def test_vao_pequeno_e_aviso(pasta):
    editar(pasta, 'B_Cu.gbr', antes_do_fim('%TO.N,TESTE*%\nD10*\nX9000000Y1930000D03*\n%TD*%\n'))
    r = validar(pasta)
    assert r.erros == []
    assert tem(r.avisos, 'vao de 0.300 mm no cobre de baixo entre +5V e TESTE')


def test_sem_fiducial(pasta):
    editar(pasta, 'NPTH.drl', lambda t: t.replace('X13.0Y0.0\n', ''))
    r = validar(pasta)
    assert tem(r.erros, 'fiduciais: nenhum par')


def test_fiduciais_desalinhados(pasta):
    editar(pasta, 'NPTH.drl', lambda t: t.replace('X13.0Y0.0', 'X13.0Y0.5'))
    assert tem(validar(pasta).erros, 'fiduciais: nenhum par')


def test_cobre_na_area_proibida(pasta):
    editar(pasta, 'B_Cu.gbr', antes_do_fim('%TO.N,GND*%\nD10*\nX13000000Y13000000D03*\n%TD*%\n'))
    assert tem(validar(pasta).erros, 'cobre de baixo dentro de uma area proibida')


def test_origem_fora_do_centro_e_recentrada(pasta, tmp_path_factory):
    """KiCad exportado com a origem absoluta: o nucleo recentra e gera o mesmo corte."""
    ref = exportar.gerar(placa.carregar(str(pasta), PRE), validar(pasta), str(tmp_path_factory.mktemp('a')),
                         previa=False)
    dx, dy = 100.0, -50.0
    for suf in ('F_Cu.gbr', 'B_Cu.gbr', 'Edge_Cuts.gbr'):
        editar(pasta, suf, lambda t: re.sub(
            r'X(-?\d+)Y(-?\d+)D0', lambda m: f'X{int(m.group(1)) + int(dx * 1e6)}Y{int(m.group(2)) + int(dy * 1e6)}D0', t))
    for suf in ('PTH.drl', 'NPTH.drl'):
        editar(pasta, suf, lambda t: re.sub(
            r'^X(-?[\d.]+)Y(-?[\d.]+)$', lambda m: f'X{float(m.group(1)) + dx:.3f}Y{float(m.group(2)) + dy:.3f}',
            t, flags=re.M))
    p = placa.carregar(str(pasta), PRE)
    r = validacao.validar(p)
    assert r.erros == [] and tem(r.info, 'origem dos arquivos nao estava no centro')
    res = exportar.gerar(p, r, str(tmp_path_factory.mktemp('b')), previa=False)
    for A, B in ((ref.caminhos_cima, res.caminhos_cima), (ref.caminhos_baixo, res.caminhos_baixo)):
        assert len(A) == len(B)
        # ruido de 1e-14 muda o vertice onde cada anel comeca e o simplify(0.005) escolhe outros
        # pontos, o que pode mudar a ordem; compara o conjunto, com a tolerancia da prova da v5
        LB = [LineString(b) for b in B]
        assert max(min(LineString(a).hausdorff_distance(b) for b in LB) for a in A) < 0.05


def test_arquivos_gerados(pasta, tmp_path):
    p = placa.carregar(str(pasta), PRE)
    res = exportar.gerar(p, validacao.validar(p), str(tmp_path / 'gcode'))
    nomes = sorted(os.listdir(tmp_path / 'gcode'))
    assert nomes == ['1-cobre-cima.nc', '2-furos.nc', '3-cobre-baixo.nc', 'previa-baixo.png', 'previa-cima.png']
    t1, t2, t3 = (open(c).read().split('\n') for c in res.arquivos)
    assert t1[:2] == ['( FRESA fase=1 lado=cima ferramenta=vbit30 placa=30.0x30.0 )',
                      '( FRESA fiduciais=-13.000,0.000;13.000,0.000 )']
    assert t2[0] == '( FRESA fase=2 lado=cima ferramenta=broca0.8 placa=30.0x30.0 )'
    assert t3[0] == '( FRESA fase=3 lado=baixo ferramenta=vbit30 placa=30.0x30.0 espelhado=x corrigir=sim )'
    # arquivo 3 trava logo no comeco
    assert t3[3] == 'M0' and t3.index('M0') < t3.index('G21 G90 G17')
    # voos antes do spindle, M0 antes do M3
    for t in (t1, t3):
        ini = lambda pre: next(i for i, l in enumerate(t) if l.startswith(pre))
        assert ini('( VOO 1') < ini('( VOO 2') < max(i for i, l in enumerate(t) if l == 'M0') < t.index('M3 S1000')
        assert t[t.index('M3 S1000') + 1] == 'G4 P3'
    assert 'M3 S1000' in t2 and not any(l.startswith('( VOO') for l in t2)
    assert sum(1 for l in t2 if re.match(r'^G0 X-?\d+\.\d{3} Y', l)) == 28


def test_comentarios_seguros():
    assert gcode.comentario('Atenção (teste) ok') == '( Atencao [teste] ok )'
    with pytest.raises(ValueError):
        gcode.conferir(['( a ( b ) )'])
    with pytest.raises(ValueError):
        gcode.conferir(['( cobre de baixo, placa virada é )'])


def test_cli(pasta, tmp_path):
    py = [sys.executable, '-m', 'fresa']
    run = lambda *a: subprocess.run(py + list(a), cwd=RAIZ, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert run('validar', str(pasta), '--prefixo', PRE).returncode == 0
    assert run('gerar', str(pasta), '--prefixo', PRE, '--saida', str(tmp_path / 'g')).returncode == 2
    r = run('gerar', str(pasta), '--saida', str(tmp_path / 'g'), '--aceitar-avisos', '--json')
    assert r.returncode == 0, r.stderr
    assert '3-cobre-baixo.nc' in r.stdout
    r = run('corrigir', str(tmp_path / 'g' / '3-cobre-baixo.nc'), '--medido', '20.902,-11.200', '46.898,-10.700')
    assert r.returncode == 0 and 'giro 1.10 graus' in r.stdout
    r = run('corrigir', str(tmp_path / 'g' / '3-cobre-baixo.nc'), '--medido', '20.902,-11.200', '47.100,-10.700')
    assert r.returncode == 1 and 'mire os fiduciais de novo' in r.stdout


def test_prova_blink_v5():
    r = subprocess.run([sys.executable, os.path.join(RAIZ, 'provar_blink_v5.py')], cwd=RAIZ,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert '**TUDO OK**' in r.stdout


def test_gerber_sem_atributos(pasta):
    tira = lambda t: re.sub(r'%T[OAD][^%]*%\n', '', t)
    editar(pasta, 'F_Cu.gbr', tira)
    editar(pasta, 'B_Cu.gbr', tira)
    assert tem(validar(pasta).erros, 'sem os atributos X2')


PCB = os.path.join(GERBER, 'blink blink-roteado.kicad_pcb')


def _tem_kicad():
    try:
        from fresa import kicad
        kicad.achar_kicad_cli()
        return os.path.isfile(PCB)
    except Exception:
        return False


@pytest.mark.skipif(not _tem_kicad(), reason='kicad-cli ou a placa da blink nao encontrados')
def test_kicad_cli_ponta_a_ponta(tmp_path):
    from fresa import kicad
    shutil.copy(PCB, tmp_path / 'blink.kicad_pcb')
    p, r, saida = kicad.processar(str(tmp_path / 'blink.kicad_pcb'))
    assert r.erros == [] and saida == str(tmp_path / 'gcode')
    res = exportar.gerar(p, r, saida, previa=False)
    assert [os.path.basename(c) for c in res.arquivos] == list(exportar.NOMES)
    # trilha apagada: o nucleo e o DRC do KiCad acusam
    t = open(PCB, encoding='utf-8').read()
    seg = list(re.finditer(r'\n\t\(segment\b.*?\n\t\)', t, re.S))[3]
    (tmp_path / 'quebrada.kicad_pcb').write_text(t[:seg.start()] + t[seg.end():], encoding='utf-8')
    p, r, _ = kicad.processar(str(tmp_path / 'quebrada.kicad_pcb'))
    assert tem(r.erros, 'partida em 2 pedacos') and tem(r.erros, 'ligacao nao roteada segundo o KiCad')


PLANO = os.path.join(AQUI, 'dados', 'blink-v5-plano-gnd')


def test_plano_gnd_nao_isola_a_borda(tmp_path):
    """Blink v5 com plano de GND em B.Cu (preenchido pelo KiCad): nada de corte na beira nem
    nas areas proibidas, e a isolacao das outras redes continua completa."""
    from shapely.geometry import Point
    from shapely.ops import unary_union
    from fresa import caminhos as c
    p = placa.carregar(PLANO)
    r = validacao.validar(p)
    assert r.erros == []
    assert not tem(r.avisos, 'borda')
    assert tem(r.info, 'as 6 desenhada(s) no KiCad')
    assert tem(r.info, 'o plano GND do cobre de baixo vai ate a beira')
    res = exportar.gerar(p, r, str(tmp_path), previa=False)
    x0, y0, x1, y1 = p.limites
    from shapely import affinity
    for P, L, esp in ((res.caminhos_cima, p.F, False), (res.caminhos_baixo, p.B, True)):
        proib = unary_union([affinity.scale(a, -1 if esp else 1, 1, origin=(0, 0)) for a in p.areas_proibidas()])
        pts = [q for path in P for q in path]
        assert not any(proib.buffer(-0.001).contains(Point(q)) for q in pts)
        borda = c.dono_da_borda(L, p.contorno, esp)
        cu = c.cobre(L, esp)
        outros = borda['outros'] if borda else cu
        precisa = cu.buffer(c.R, c.SEG_ISO).simplify(c.SIMPLIFICA).boundary.intersection(outros.buffer(c.R + 0.02))
        cortes = unary_union([LineString(q) for q in P if len(q) > 1]).buffer(0.01)
        assert precisa.difference(cortes).length < 0.01          # 1a passada das outras redes inteira
    # lado de baixo: o plano chega a 0,5 mm da beira e o corte mais perto fica a mais de 1 mm
    beira = min(min(x - x0, x1 - x, y - y0, y1 - y) for path in res.caminhos_baixo for x, y in path)
    assert beira > 1.0
    assert 'borda: o plano GND' in open(res.arquivos[2]).read()
    assert 'borda:' not in open(res.arquivos[0]).read()


def test_sem_plano_nao_tem_dono_da_borda():
    from fresa import caminhos as c
    p = placa.carregar(GERBER, PRE)
    assert c.dono_da_borda(p.B, p.contorno) is None and c.dono_da_borda(p.F, p.contorno) is None


def test_area_proibida_tolera_contorno_de_zona_na_beira(pasta):
    # contorno de zona correndo na diagonal x+y=19 do canto proibido, 5 milionesimos de mm para dentro,
    # como o arredondamento das coordenadas do Gerber deixa: nao e erro
    editar(pasta, 'B_Cu.gbr', antes_do_fim(
        '%TO.N,GND*%\nG36*\nX6000000Y13000005D02*\nG01*\nX13000005Y6000000D01*\nX6000000Y6000000D01*\n'
        'X6000000Y13000005D01*\nG37*\n%TD*%\n'))
    p = placa.carregar(str(pasta), PRE)
    zona = [e for e in p.B if e.regiao][0].geom
    assert any(zona.intersection(t).area > 1e-6 for t in p.cantos_proibidos())   # sem a folga, seria erro
    assert not tem(validacao.validar(p).erros, 'area proibida')


def test_areas_proibidas_padrao_em_volta_dos_fiduciais():
    # so Gerbers, sem o arquivo de areas do KiCad: 2x2 mm em volta de cada furo NPTH de 0,8
    p = placa.carregar(GERBER, PRE)
    assert p.origem_proibidas == 'padrao'
    assert sorted(a.bounds for a in p.proibidas_extra) == [(-14.0, -1.0, -12.0, 1.0), (12.0, -1.0, 14.0, 1.0)]
    assert len(p.areas_proibidas()) == 6


def test_corte_nao_entra_em_area_proibida_do_projeto(pasta, tmp_path):
    # area proibida do KiCad cruzando trilhas: passadas 2 a 4 saem dela, a 1a fica e vira aviso
    import json
    from shapely.geometry import Point, Polygon
    (pasta / (PRE + 'areas-proibidas.json')).write_text(json.dumps([[(2, -10), (8, -10), (8, -6), (2, -6)]]))
    p = placa.carregar(str(pasta), PRE)
    assert p.origem_proibidas == 'kicad'
    r = validacao.validar(p)
    assert tem(r.erros, 'cobre de baixo dentro de uma area proibida')
    res = exportar.gerar(p, r, str(tmp_path), previa=False)
    area = Polygon([(-2, -10), (-8, -10), (-8, -6), (-2, -6)]).buffer(-0.01)   # espelhada no lado de baixo
    from fresa import caminhos as c
    passadas_extras = [q for q in res.caminhos_baixo if len(q) > 1]
    um = c.cobre(p.B, True).buffer(c.R, c.SEG_ISO).simplify(c.SIMPLIFICA).boundary
    fora_da_1a = [pt for q in passadas_extras for pt in q if um.distance(Point(pt)) > 0.02]
    assert not any(area.contains(Point(pt)) for pt in fora_da_1a)


def test_plano_pode_entrar_na_area_proibida_quando_nao_e_cortado(tmp_path):
    """Placa do Aluisio de 2026-10-14: as areas proibidas do KiCad (cantos de 10 mm) deixam o
    plano entrar (copperpour allowed). Nao e erro, e nenhum sulco entra nelas."""
    d = os.path.join(AQUI, 'dados', 'blink-plano-areas-kicad')
    p = placa.carregar(d, 'blink blink-roteado-')
    assert p.origem_proibidas == 'kicad' and len(p.proibidas_extra) == 6
    r = validacao.validar(p)
    assert r.erros == []
    res = exportar.gerar(p, r, str(tmp_path), previa=False)
    # valem so as areas desenhadas no KiCad: nenhum sulco encosta nelas, nem o da 1a passada
    assert res.invasao_proibidas == {'cima': 0.0, 'baixo': 0.0}
    assert not tem(r.avisos, 'area proibida')


def test_acabamento_tira_os_dentinhos_na_beira_das_areas(tmp_path):
    """As passadas 2 a 4 terminam em ponta redonda na beira das areas proibidas; a passada de
    acabamento ao longo da beira tira o cobre que sobrava entre as pontas (os dentinhos)."""
    from shapely import affinity
    from shapely.ops import unary_union
    from fresa import caminhos as c
    d = os.path.join(AQUI, 'dados', 'blink-plano-areas-kicad')
    p = placa.carregar(d, 'blink blink-roteado-')
    r = validacao.validar(p)

    def dentes(P, esp):
        proib = unary_union([affinity.scale(a, -1 if esp else 1, 1, origin=(0, 0)) for a in p.areas_proibidas()])
        sulcos = unary_union([LineString(q).buffer(c.MEIO_SULCO, 8) for q in P if len(q) > 1])
        fechado = sulcos.buffer(0.15, 8).buffer(-0.15, 8)          # o sulco sem os dentes
        junto = proib.buffer(2 * c.MEIO_SULCO + 0.05).difference(proib)
        return fechado.difference(sulcos).intersection(junto).area

    antes = exportar.gerar(p, r, str(tmp_path / 'a'), previa=False, sulco_fora=False)
    depois = exportar.gerar(p, r, str(tmp_path / 'b'), previa=False)
    assert dentes(antes.caminhos_cima, False) > 0.01
    for P, esp in ((depois.caminhos_cima, False), (depois.caminhos_baixo, True)):
        assert dentes(P, esp) < 0.002
    assert depois.invasao_proibidas == {'cima': 0.0, 'baixo': 0.0}
