"""O nucleo.js do plugin do Candle tem que dar o mesmo resultado que fresa/corrigir.py,
que ja foi provado contra o arquivo de baixo corrigido da blink v5."""
import json
import os
import shutil
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from fresa import corrigir, exportar, placa, validacao  # noqa: E402

NODE = shutil.which('node')
CLI = os.path.join(RAIZ, 'candle_plugin', 'testes', 'corrigir_cli.js')
GERBER = os.path.join(RAIZ, 'testes', 'dados', 'blink-v5')

pytestmark = pytest.mark.skipif(not NODE, reason='node nao encontrado')


@pytest.fixture(scope='module')
def arquivo3(tmp_path_factory):
    p = placa.carregar(GERBER, 'blink blink-roteado-')
    res = exportar.gerar(p, validacao.validar(p), str(tmp_path_factory.mktemp('g')), previa=False)
    return res.arquivos[2]


def node(arquivo, cam, m1, m2):
    r = subprocess.run([NODE, CLI, arquivo, *map(str, (*cam, *m1, *m2))], capture_output=True,
                       text=True, encoding='utf-8')
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# medidas da v5 (as que levam o arquivo 3 ao exemplo-4) e uma placa bem torta
CASOS = [((20.902, -11.200), (46.898, -10.700)),
         ((10.123, 3.456), (35.6, 9.8))]


@pytest.mark.parametrize('m1,m2', CASOS)
def test_igual_ao_python(arquivo3, m1, m2):
    cam = (corrigir.CAM_DX, corrigir.CAM_DY)
    j = node(arquivo3, cam, m1, m2)
    texto = open(arquivo3).read()
    f, info = corrigir.transformacao([(-13.0, 0.0), (13.0, 0.0)],
                                     [corrigir.visto_pela_camera(m) for m in (m1, m2)])
    py = corrigir.aplicar(texto, f, j['texto'].split('\n')[2][2:-2])
    assert abs(j['giro'] - info['giro_graus']) < 1e-9
    assert j['texto'] == py


def test_cabecalho_e_trava(arquivo3):
    j = node(arquivo3, (35.065, -6.0), *CASOS[0])
    c = j['cabecalho']
    assert c['fase'] == 3 and c['lado'] == 'baixo' and c['corrigir'] == 'sim'
    assert c['fiduciais'] == [[-13, 0], [13, 0]]
    linhas = j['texto'].split('\n')
    assert 'corrigir=feito' in linhas[0]
    assert linhas[2].startswith('( CORRIGIDO pelos fiduciais: giro 1.10 graus, centro da placa em X-1.16 Y-4.95')
    assert not any(l.startswith('( ATENCAO') for l in linhas)
    assert linhas.index('M0') > linhas.index('G21 G90 G17')   # so sobrou a pausa dos voos
    assert j['ok'] is True


SIM = os.path.join(RAIZ, 'candle_plugin', 'testes', 'simulador.js')
M1, M2 = (20.902, -11.200), (46.898, -10.700)     # medidas da v5


def simular(arquivo, roteiro, tmp_path):
    r_json = tmp_path / 'roteiro.json'
    r_json.write_text(json.dumps(roteiro))
    r = subprocess.run([NODE, SIM, arquivo, str(r_json)], capture_output=True, text=True, encoding='utf-8')
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.fixture
def arq3_copia(arquivo3, tmp_path):
    c = tmp_path / '3-cobre-baixo.nc'
    shutil.copy(arquivo3, c)
    return str(c)


def test_virada_completa_no_simulador(arq3_copia, tmp_path):
    s = simular(arq3_copia, [
        {'foto': 'inicio'},
        {'clicar': 'cmdIr1'},
        {'pos': M1}, {'clicar': 'cmdMarcar1'},
        {'clicar': 'cmdIr2'},
        {'pos': M2}, {'clicar': 'cmdMarcar2'},
        {'foto': 'medido'},
        {'clicar': 'cmdAplicar'},
        {'foto': 'aplicado'},
        {'clicar': 'cmdCentro'},
    ], tmp_path)
    ini, med, apl = s['fotos']
    assert ini['txtF1']['text'] == '-13.000, 0.000' and ini['txtF2']['text'] == '13.000, 0.000'
    assert 'Precisa da correção' in ini['lblArquivo']['text'] and not ini['cmdAplicar']['enabled']
    c = s['log']['comandos']
    # Ir 1: camera sobre o fiducial de projeto; Ir 2: ja corrigido pelo erro medido no 1
    assert c[0] == ['G53 G0 Z-2', 'G90 G0 X22.065 Y-6.000']
    assert c[1] == ['G53 G0 Z-2', 'G90 G0 X46.902 Y-11.200']
    assert 'giro' in med['lblResultado']['text'].lower() and med['cmdAplicar']['enabled']
    # o arquivo corrigido gravado ao lado e carregado e igual ao do Python
    corrigido = arq3_copia[:-3] + '-CORRIGIDO.nc'
    assert s['log']['carregados'] == [corrigido] and s['programa'] == corrigido
    f, info = corrigir.transformacao([(-13.0, 0.0), (13.0, 0.0)], [corrigir.visto_pela_camera(m) for m in (M1, M2)])
    texto = open(arq3_copia).read()
    py = corrigir.aplicar(texto, f, f"CORRIGIDO pelos fiduciais: giro {info['giro_graus']:.2f} graus, centro da placa "
                                    f"em X{info['centro'][0]:.2f} Y{info['centro'][1]:.2f}")
    assert open(corrigido).read() == py + ('' if py.endswith('\n') else '\n')
    assert 'Já corrigido' in apl['lblArquivo']['text'] and not apl['cmdAplicar']['enabled']
    # broca no centro real (o que o exemplo-4 diz: X-1.16 Y-4.95)
    assert c[2][0] == 'G53 G0 Z-2' and c[2][1].startswith('G90 G0 X-1.165 Y-4.950')
    assert s['log']['avisos'] == []


def test_medida_ruim_nao_deixa_aplicar(arq3_copia, tmp_path):
    s = simular(arq3_copia, [
        {'pos': M1}, {'clicar': 'cmdMarcar1'},
        {'pos': (M2[0] + 0.3, M2[1])}, {'clicar': 'cmdMarcar2'},
        {'foto': 'ruim'}, {'clicar': 'cmdAplicar'},
    ], tmp_path)
    f = s['fotos'][0]
    assert not f['cmdAplicar']['enabled'] and 'mire os dois fiduciais de novo' in f['lblDica']['text']
    assert s['log']['carregados'] == []


def test_maquina_em_alarme_ou_rodando_nao_move(arq3_copia, tmp_path):
    s = simular(arq3_copia, [{'estado': 2}, {'clicar': 'cmdIr1'}, {'clicar': 'cmdMarcar1'},
                             {'estado': 1, 'remetente': 0}, {'clicar': 'cmdIr1'}], tmp_path)
    assert s['log']['comandos'] == []
    assert len(s['log']['avisos']) == 3


def test_calibrar(arq3_copia, tmp_path):
    s = simular(arq3_copia, [
        {'clicar': 'cmdOlharCruz'},
        {'pos': (35.1, -6.05)}, {'responder': 'nao'}, {'clicar': 'cmdCalibrar'}, {'foto': 'recusou'},
        {'responder': 'sim'}, {'clicar': 'cmdCalibrar'}, {'foto': 'aceitou'},
        {'clicar': 'cmdOlharCruz'},
    ], tmp_path)
    assert s['log']['comandos'][0] == ['G53 G0 Z-2', 'G90 G0 X35.065 Y-6.000']
    assert 'X 35.065' in s['fotos'][0]['lblCamera']['text']
    assert s['armazenamento'] == {'FresaPCB/camX': 35.1, 'FresaPCB/camY': -6.05}
    assert 'X 35.100' in s['fotos'][1]['lblCamera']['text']
    assert s['log']['comandos'][1] == ['G53 G0 Z-2', 'G90 G0 X35.100 Y-6.050']
