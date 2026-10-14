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


def esperado_python(arquivo, m1, m2):
    f, info = corrigir.transformacao([(-13.0, 0.0), (13.0, 0.0)], [corrigir.visto_pela_camera(m) for m in (m1, m2)])
    py = corrigir.aplicar(open(arquivo).read(), f, f"CORRIGIDO pelos fiduciais: giro {info['giro_graus']:.2f} graus, "
                                                  f"centro da placa em X{info['centro'][0]:.2f} Y{info['centro'][1]:.2f}")
    return py if py.endswith('\n') else py + '\n'


def test_marcar_e_corrigir_o_desenho_aberto(arq3_copia, tmp_path):
    s = simular(arq3_copia, [
        {'foto': 'aberto'},
        {'pos': M1}, {'clicar': 'cmdMarcar1'},
        {'pos': M2}, {'clicar': 'cmdMarcar2'},
        {'foto': 'marcado'},
        {'clicar': 'cmdCorrigir'},
        {'foto': 'corrigido'},
    ], tmp_path)
    ab, mc, co = s['fotos']
    assert 'Precisa da correção' in ab['lblArquivo']['text']
    assert ab['cmdMarcar1']['enabled'] and not ab['cmdCorrigir']['enabled']
    assert mc['cmdMarcar1']['text'].endswith('✓') and mc['cmdMarcar2']['text'].endswith('✓')
    assert 'Giro 1.10' in mc['lblResultado']['text'] and mc['cmdCorrigir']['enabled']
    # o desenho aberto e trocado pelo corrigido, gravado ao lado, igual ao do Python
    corrigido = arq3_copia[:-3] + '-CORRIGIDO.nc'
    assert s['log']['carregados'] == [corrigido] and s['programa'] == corrigido
    assert open(corrigido).read() == esperado_python(arq3_copia, M1, M2)
    assert 'Já corrigido' in co['lblArquivo']['text'] and not co['cmdCorrigir']['enabled']
    assert 'centro da placa em X -1.165 Y -4.950' in co['lblResultado']['text']
    assert s['log']['avisos'] == []          # e nunca moveu a maquina


def test_medida_ruim_nao_deixa_corrigir(arq3_copia, tmp_path):
    s = simular(arq3_copia, [
        {'pos': M1}, {'clicar': 'cmdMarcar1'},
        {'pos': (M2[0] + 0.3, M2[1])}, {'clicar': 'cmdMarcar2'},
        {'foto': 'ruim'}, {'clicar': 'cmdCorrigir'},
    ], tmp_path)
    f = s['fotos'][0]
    assert not f['cmdCorrigir']['enabled'] and 'marque os dois de novo' in f['lblResultado']['text']
    assert s['log']['carregados'] == []


def test_so_marca_com_a_maquina_parada_e_nao_corrige_rodando(arq3_copia, tmp_path):
    s = simular(arq3_copia, [{'estado': 13}, {'pos': M1}, {'clicar': 'cmdMarcar1'}, {'foto': 'andando'},
                             {'estado': 1}, {'clicar': 'cmdMarcar1'}, {'pos': M2}, {'clicar': 'cmdMarcar2'},
                             {'remetente': 0}, {'clicar': 'cmdCorrigir'}], tmp_path)
    assert not s['fotos'][0]['cmdMarcar1']['text'].endswith('✓')
    assert s['log']['carregados'] == []
    assert len(s['log']['avisos']) == 2 and not any('MOVEU' in a for a in s['log']['avisos'])


def test_abrir_outro_arquivo_zera_as_marcas(arq3_copia, arquivo3, tmp_path):
    outro = tmp_path / 'outro.nc'
    shutil.copy(arquivo3, outro)
    s = simular(arq3_copia, [{'pos': M1}, {'clicar': 'cmdMarcar1'}, {'abrir': str(outro)}, {'tick': 1}, {'foto': 'f'}],
                tmp_path)
    assert not s['fotos'][0]['cmdMarcar1']['text'].endswith('✓')


def test_deslocamento_da_camera_nas_configuracoes(arq3_copia, tmp_path):
    # outro deslocamento: as mesmas posicoes de maquina dao outra correcao
    s = simular(arq3_copia, [
        {'foto': 'padrao'},
        {'config': ['35,1', -6.05]},
        {'pos': M1}, {'clicar': 'cmdMarcar1'}, {'pos': M2}, {'clicar': 'cmdMarcar2'},
        {'clicar': 'cmdCorrigir'}, {'foto': 'f'},
    ], tmp_path)
    assert s['fotos'][0]['txtCamX']['text'] == '35.065' and s['fotos'][0]['txtCamY']['text'] == '-6.000'
    assert s['armazenamento'] == {'FresaPCB/camX': 35.1, 'FresaPCB/camY': -6.05}
    assert 'centro da placa em X -1.200 Y -4.900' in s['fotos'][1]['lblResultado']['text']


def test_arquivo_sem_cabecalho_nao_deixa_marcar(tmp_path):
    a = tmp_path / 'qualquer.nc'
    a.write_text('G21 G90\nG0 X1.000 Y2.000\nM30\n')
    s = simular(str(a), [{'foto': 'f'}], tmp_path)
    f = s['fotos'][0]
    assert 'Sem cabeçalho FRESA' in f['lblArquivo']['text'] and not f['cmdMarcar1']['enabled']


def test_janela_tem_a_camera_com_a_configuracao_do_plugin_camera(arq3_copia, tmp_path):
    s = simular(arq3_copia, [], tmp_path)
    assert s['camera'] == {
        'abertaCom': '640x480', 'cameraName': 'USB2.0 PC CAMERA', 'resolution': [640, 480], 'zoom': 1.5, 'pos': [10, 20],
        'aimPos': [0.5, 0.48], 'aimSize': 30, 'aimLineWidth': 2, 'aimColor': -65536,
        'mirrorHorizontal': False, 'mirrorVertical': True}


def test_camera_nao_escolhida_usa_a_da_especificacao_com_mira_no_centro(arq3_copia, tmp_path, monkeypatch):
    # como esta no Candle do Aluisio: o plugin Camera oficial nunca teve camera escolhida
    monkeypatch.setenv('CAMERA_CONFIG', json.dumps({'name': '', 'resolution': '1280x720', 'zoom': '1',
                                                    'position': '0, 0', 'aimPosition': '0, 0'}))
    monkeypatch.setenv('CAMERAS', json.dumps(['Integrated Webcam', 'USB2.0 PC CAMERA']))
    s = simular(arq3_copia, [{'foto': 'f'}], tmp_path)
    c = s['camera']
    assert c['cameraName'] == 'USB2.0 PC CAMERA' and c['aimPos'] == [0.5, 0.5]
    assert c['abertaCom'] == '640x480'          # a camera LIGOU com a resolucao que ela tem
    assert 'Leve a câmera' in s['fotos'][0]['lblResultado']['text']   # sem aviso de camera


def test_resolucao_salva_que_a_camera_nao_tem_e_trocada(arq3_copia, tmp_path, monkeypatch):
    monkeypatch.setenv('CAMERA_CONFIG', json.dumps({'name': 'USB2.0 PC CAMERA', 'resolution': '1280x720'}))
    monkeypatch.setenv('RESOLUCOES', json.dumps(['352x288', '640x480']))
    s = simular(arq3_copia, [], tmp_path)
    assert s['camera']['abertaCom'] == '640x480'


def test_sem_camera_ligada_avisa(arq3_copia, tmp_path, monkeypatch):
    monkeypatch.setenv('CAMERA_CONFIG', json.dumps({'name': ''}))
    monkeypatch.setenv('CAMERAS', '[]')
    s = simular(arq3_copia, [{'pos': M1}, {'clicar': 'cmdMarcar1'}, {'foto': 'f'}], tmp_path)
    assert 'Nenhuma câmera encontrada' in s['fotos'][0]['lblResultado']['text']


def test_duas_cameras_desconhecidas_pede_para_escolher(arq3_copia, tmp_path, monkeypatch):
    monkeypatch.setenv('CAMERA_CONFIG', json.dumps({'name': ''}))
    monkeypatch.setenv('CAMERAS', json.dumps(['Cam A', 'Cam B']))
    s = simular(arq3_copia, [{'foto': 'f'}], tmp_path)
    assert 'escolha qual' in s['fotos'][0]['lblResultado']['text'] and 'Cam A, Cam B' in s['fotos'][0]['lblResultado']['text']


SIM_PROBE = os.path.join(RAIZ, 'candle_plugin', 'testes', 'simulador_probe.js')


def trava(roteiro, tmp_path):
    r_json = tmp_path / 'roteiro_probe.json'
    r_json.write_text(json.dumps(roteiro))
    r = subprocess.run([NODE, SIM_PROBE, str(r_json)], capture_output=True, text=True, encoding='utf-8')
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.fixture
def dois_arquivos(arquivo3, tmp_path):
    a, b = tmp_path / '1-cobre-cima.nc', tmp_path / '2-furos.nc'
    shutil.copy(arquivo3, a)
    shutil.copy(arquivo3, b)
    return str(a), str(b)


def test_probe_feito_depois_de_abrir_nao_pergunta(dois_arquivos, tmp_path):
    a, _ = dois_arquivos
    s = trava([{'abrir': a}, {'tick': 1}, {'probe': True}, {'remetente': 0}], tmp_path)
    assert s == {'tempoReal': [], 'perguntas': 0}


def test_esqueceu_o_probe_segura_e_para(dois_arquivos, tmp_path):
    a, _ = dois_arquivos
    s = trava([{'abrir': a}, {'tick': 1}, {'responder': 'nao'}, {'remetente': 0}], tmp_path)
    assert s == {'tempoReal': ['!', 'RESET'], 'perguntas': 1}


def test_esqueceu_mas_confirma_que_fez_continua(dois_arquivos, tmp_path):
    a, _ = dois_arquivos
    s = trava([{'abrir': a}, {'tick': 1}, {'responder': 'sim'}, {'remetente': 0},
               {'remetente': 2}, {'remetente': 0}, {'remetente': 4}, {'remetente': 0}], tmp_path)
    # pergunta uma vez so: nem ao voltar da pausa, nem ao rodar de novo o mesmo arquivo
    assert s == {'tempoReal': ['!', '~'], 'perguntas': 1}


def test_probe_que_falhou_nao_conta(dois_arquivos, tmp_path):
    a, _ = dois_arquivos
    s = trava([{'abrir': a}, {'tick': 1}, {'probe': False}, {'responder': 'nao'}, {'remetente': 0}], tmp_path)
    assert s['perguntas'] == 1


def test_abrir_outro_arquivo_pede_probe_de_novo(dois_arquivos, tmp_path):
    # troca de ferramenta (arquivo de furos) ou arquivo corrigido pela camera: probe novo
    a, b = dois_arquivos
    s = trava([{'abrir': a}, {'tick': 1}, {'probe': True}, {'remetente': 0}, {'remetente': 4},
               {'abrir': b}, {'tick': 1}, {'responder': 'nao'}, {'remetente': 0}], tmp_path)
    assert s == {'tempoReal': ['!', 'RESET'], 'perguntas': 1}


def test_arquivo_que_nao_e_fresa_nao_e_vigiado(tmp_path):
    q = tmp_path / 'qualquer.nc'
    q.write_text('G21 G90\nG0 X1 Y1\nM30\n')
    s = trava([{'abrir': str(q)}, {'tick': 1}, {'remetente': 0}], tmp_path)
    assert s == {'tempoReal': [], 'perguntas': 0}


def test_mira_nao_sai_do_lugar(arq3_copia, tmp_path, monkeypatch):
    # Shift + arrastar move a mira no CameraWidget; a calibracao vale para ela no centro
    monkeypatch.setenv('CAMERA_CONFIG', json.dumps({'name': ''}))
    s = simular(arq3_copia, [{'arrastarMira': [0.62, 0.41]}], tmp_path)
    assert s['camera']['aimPos'] == [0.5, 0.5]
