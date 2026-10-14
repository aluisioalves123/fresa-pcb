"""Instala (ou atualiza) os plugins Fresa PCB no Candle.

  python instalar_plugin_candle.py [--candle "C:/Program Files/Candle"]

Copia candle_plugin/fresa (correcao pelos fiduciais, com a camera) e candle_plugin/fresaprobe
(trava do probe, sem janela) para <Candle>/candleplugins. Essa pasta fica em
Arquivos de Programas, entao o Windows pede permissao de administrador: o script
se reabre como administrador sozinho. Feche e abra o Candle depois.
"""
import argparse
import ctypes
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
PLUGINS = ('fresa', 'fresaprobe')


def copiar(candle):
    destinos = []
    for nome in PLUGINS:
        destino = os.path.join(candle, 'candleplugins', nome)
        if os.path.isdir(destino):
            shutil.rmtree(destino)
        shutil.copytree(os.path.join(AQUI, 'candle_plugin', nome), destino,
                        ignore=shutil.ignore_patterns('__pycache__'))
        destinos.append(destino)
    return ', '.join(destinos)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--candle', default=r'C:\Program Files\Candle')
    ap.add_argument('--elevado', action='store_true', help=argparse.SUPPRESS)
    a = ap.parse_args()
    if not os.path.isfile(os.path.join(a.candle, 'candle.exe')):
        sys.exit(f'Candle nao encontrado em {a.candle}: use --candle')
    try:
        destino = copiar(a.candle)
    except PermissionError:
        if a.elevado or sys.platform != 'win32':
            raise
        print('Pedindo permissao de administrador ao Windows...')
        params = subprocess.list2cmdline([os.path.abspath(__file__), '--candle', a.candle, '--elevado'])
        r = ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable, params, AQUI, 1)
        if r <= 32:
            sys.exit('Permissao negada: o plugin nao foi instalado.')
        print('Continue na janela de administrador que abriu. Depois feche e abra o Candle.')
        return
    print(f'Plugins instalados em {destino}')
    print('Feche e abra o Candle.')
    if a.elevado:
        input('Enter para fechar...')


if __name__ == '__main__':
    main()
