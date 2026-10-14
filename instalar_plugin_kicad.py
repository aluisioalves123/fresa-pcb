"""Instala (ou atualiza) o plugin Fresa PCB no KiCad, no jeito classico (ActionPlugin).

  python instalar_plugin_kicad.py [--versao 10.0]

1. Cria .venv-kicad nesta pasta com o Python do proprio KiCad e instala shapely e
   matplotlib (so na primeira vez, ou se faltar algo).
2. Copia kicad_plugin/ para Documentos/KiCad/<versao>/scripting/plugins/fresa_pcb
   e grava la o config.json apontando para este projeto.

O plugin roda o nucleo direto desta pasta: mudou o codigo do nucleo, nao precisa
reinstalar. Mudou a janela (kicad_plugin/), rode de novo.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(AQUI, '.venv-kicad')
NOME = 'fresa_pcb'


def python_do_kicad(versao):
    if sys.platform == 'win32':
        c = rf'C:\Program Files\KiCad\{versao}\bin\python.exe'
        if os.path.isfile(c):
            return c
        achados = sorted(glob.glob(r'C:\Program Files\KiCad\*\bin\python.exe'), reverse=True)
        if achados:
            return achados[0]
    return sys.executable


def python_do_venv():
    return os.path.join(VENV, 'Scripts', 'python.exe') if sys.platform == 'win32' \
        else os.path.join(VENV, 'bin', 'python')


def pasta_plugins(versao):
    base = os.environ.get('KICAD_DOCUMENTS_HOME')
    if not base:
        if sys.platform in ('win32', 'darwin'):
            base = os.path.join(os.path.expanduser('~'), 'Documents', 'KiCad')
        else:
            base = os.path.expanduser('~/.local/share/kicad')
    return os.path.join(base, versao, 'scripting', 'plugins')


def preparar_venv(versao):
    py = python_do_venv()
    if not os.path.isfile(py):
        base = python_do_kicad(versao)
        print(f'Criando o ambiente do nucleo com {base} ...')
        subprocess.run([base, '-m', 'venv', VENV], check=True)
    ok = subprocess.run([py, '-c', 'import shapely, matplotlib'], capture_output=True).returncode == 0
    if not ok:
        print('Instalando shapely e matplotlib ...')
        subprocess.run([py, '-m', 'pip', 'install', '-q', '-r',
                        os.path.join(AQUI, 'requirements-nucleo.txt')], check=True)
    return py


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--versao', default='10.0')
    a = ap.parse_args()
    py = preparar_venv(a.versao)
    destino = os.path.join(pasta_plugins(a.versao), NOME)
    if os.path.isdir(destino):
        shutil.rmtree(destino)
    shutil.copytree(os.path.join(AQUI, 'kicad_plugin'), destino,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    with open(os.path.join(destino, 'config.json'), 'w', encoding='utf-8') as f:
        json.dump({'python': py, 'raiz': AQUI}, f, ensure_ascii=False, indent=1)
    print(f'Plugin instalado em {destino}')
    print('No KiCad, editor de PCB: Ferramentas > Plugins externos > Atualizar plugins')
    print('(ou feche e abra o editor). O botao "Exportar para a fresa" aparece na barra.')


if __name__ == '__main__':
    main()
