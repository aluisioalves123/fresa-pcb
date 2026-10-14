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
    assert len(r.avisos) == 1 and 'diferente de 0.8' in r.avisos[0]
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


def test_cobre_na_garra(pasta):
    editar(pasta, 'B_Cu.gbr', antes_do_fim('%TO.N,GND*%\nD10*\nX13000000Y13000000D03*\n%TD*%\n'))
    assert tem(validar(pasta).erros, 'triangulo de 11 mm da garra')


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
