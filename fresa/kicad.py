"""Ponte com o KiCad pelo kicad-cli: .kicad_pcb -> Gerbers + furacao + DRC -> nucleo.

Nao depende da API do KiCad. A casca (kicad_plugin/) so salva a placa aberta e chama isto.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

from . import placa as placa_mod
from . import validacao


class ErroKicad(Exception):
    pass


def achar_kicad_cli(sugestao=None):
    candidatos = [sugestao, os.environ.get('FRESA_KICAD_CLI'), shutil.which('kicad-cli')]
    if sys.platform == 'win32':
        candidatos += sorted(glob.glob(r'C:\Program Files\KiCad\*\bin\kicad-cli.exe'), reverse=True)
    elif sys.platform == 'darwin':
        candidatos.append('/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')
    for c in candidatos:
        if c and os.path.isfile(c):
            return c
    raise ErroKicad('kicad-cli nao encontrado. Instale o KiCad ou defina FRESA_KICAD_CLI')


def _rodar(cli, *args):
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    r = subprocess.run([cli, *args], capture_output=True, text=True, errors='replace', creationflags=flags)
    if r.returncode != 0:
        raise ErroKicad(f'kicad-cli {args[0]} {args[1]} {args[2]} falhou: {(r.stderr or r.stdout).strip()}')
    return r


def exportar_fabricacao(pcb, pasta, cli):
    """Gerbers de cobre e borda + furacao PTH/NPTH, com a origem de furacao (centro da placa)."""
    os.makedirs(pasta, exist_ok=True)
    for f in glob.glob(os.path.join(pasta, '*')):
        if f.endswith(('.gbr', '.drl', '.gbrjob', '.json')):
            os.remove(f)
    _rodar(cli, 'pcb', 'export', 'gerbers', '-o', pasta, '-l', 'F.Cu,B.Cu,Edge.Cuts',
           '--use-drill-file-origin', '--no-protel-ext', pcb)
    _rodar(cli, 'pcb', 'export', 'drill', '-o', pasta + os.sep, '--drill-origin', 'plot',
           '--excellon-separate-th', '--excellon-zeros-format', 'decimal', '-u', 'mm', pcb)
    return os.path.splitext(os.path.basename(pcb))[0] + '-'


def ligacoes_nao_roteadas(pcb, pasta, cli):
    """Itens desconectados segundo o DRC do proprio KiCad (o ratsnest)."""
    saida = os.path.join(pasta, 'drc.json')
    _rodar(cli, 'pcb', 'drc', '--format', 'json', '--units', 'mm', '-o', saida, pcb)
    d = json.load(open(saida, encoding='utf-8'))
    out = []
    for v in d.get('unconnected_items', []):
        itens = ' com '.join(i.get('description', '?') for i in v.get('items', []))
        out.append(itens or v.get('description', '?'))
    return out


def _blocos(texto, cabeca):
    """Cada bloco '(cabeca ...)' do arquivo, com os parenteses casados."""
    i = 0
    while True:
        i = texto.find('(' + cabeca, i)
        if i < 0:
            return
        prof = 0
        for j in range(i, len(texto)):
            prof += (texto[j] == '(') - (texto[j] == ')')
            if prof == 0:
                yield texto[i:j + 1]
                break
        i += 1


def areas_proibidas(pcb):
    """Areas proibidas (rule areas com cobre proibido) do .kicad_pcb, em coordenadas de
    Gerber exportado com a origem de furacao: X = x - ox, Y = oy - y (o KiCad tem Y para baixo)."""
    texto = open(pcb, encoding='utf-8').read()
    m = re.search(r'\(aux_axis_origin\s+(-?[\d.]+)\s+(-?[\d.]+)\)', texto)
    ox, oy = (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)
    out = []
    for z in _blocos(texto, 'zone'):
        if '(keepout' not in z:
            continue
        if not re.search(r'\((?:tracks|copperpour) not_allowed\)', z):
            continue
        camadas = re.findall(r'"([^"]*Cu)"', ' '.join(re.findall(r'\(layers?\s+[^)]*\)', z)))
        if not camadas:
            continue
        for pol in _blocos(z, 'polygon'):
            pts = [((float(x) - ox), (oy - float(y)))
                   for x, y in re.findall(r'\(xy\s+(-?[\d.]+)\s+(-?[\d.]+)\)', pol)]
            if len(pts) >= 3:
                out.append(pts)
    return out


def processar(pcb, cli=None, pasta_saida=None, pasta_fab=None):
    """Exporta, carrega e valida. Devolve (placa, relatorio, pasta_gcode)."""
    pcb = os.path.abspath(pcb)
    if not os.path.isfile(pcb):
        raise ErroKicad(f'placa nao encontrada: {pcb}')
    cli = achar_kicad_cli(cli)
    pasta_gcode = pasta_saida or os.path.join(os.path.dirname(pcb), 'gcode')
    pasta_fab = pasta_fab or os.path.join(pasta_gcode, 'gerber')
    prefixo = exportar_fabricacao(pcb, pasta_fab, cli)
    with open(os.path.join(pasta_fab, prefixo + placa_mod.ARQ_PROIBIDAS), 'w', encoding='utf-8') as f:
        json.dump(areas_proibidas(pcb), f)
    p = placa_mod.carregar(pasta_fab, prefixo)
    rel = validacao.validar(p)
    for item in ligacoes_nao_roteadas(pcb, pasta_fab, cli):
        rel.erro(f'ligacao nao roteada segundo o KiCad: {item}')
    return p, rel, pasta_gcode
