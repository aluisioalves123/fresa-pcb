"""Linha de comando.

  python -m fresa gerar  <pasta-gerber> [--prefixo P] [--saida PASTA] [--aceitar-avisos] [--json]
  python -m fresa validar <pasta-gerber> [--prefixo P] [--json]
  python -m fresa kicad  <placa.kicad_pcb> [--saida PASTA] [--aceitar-avisos] [--json]
  python -m fresa corrigir <3-cobre-baixo.nc> --medido X1,Y1 X2,Y2 [--saida ARQ]

Codigos de saida: 0 ok, 1 erro de validacao ou de leitura, 2 avisos nao aceitos.
"""
import argparse
import json
import os
import re
import sys

from . import corrigir, exportar, placa, validacao


def _imprime(rel):
    for m in rel.info:
        print('  ' + m)
    for m in rel.avisos:
        print('  AVISO: ' + m)
    for m in rel.erros:
        print('  ERRO: ' + m)


def _carrega(a):
    try:
        return placa.carregar(a.pasta, a.prefixo)
    except Exception as e:   # leitura: mensagem curta, sem traceback
        print(f'ERRO ao ler os arquivos: {e}', file=sys.stderr)
        sys.exit(1)


def cmd_validar(a):
    p = _carrega(a)
    rel = validacao.validar(p)
    if a.json:
        print(json.dumps(rel.como_dict(), ensure_ascii=False, indent=1))
    else:
        print(f'Validando {p.nome}')
        _imprime(rel)
        print('OK, sem erros.' if rel.ok else f'{len(rel.erros)} erro(s).')
    return 0 if rel.ok else 1


def cmd_gerar(a):
    p = _carrega(a)
    rel = validacao.validar(p)
    return _exportar(a, p, rel, a.saida or os.path.join(a.pasta, 'gcode'))


def cmd_kicad(a):
    from . import kicad
    try:
        p, rel, saida = kicad.processar(a.pcb, pasta_saida=a.saida, pasta_fab=a.pasta_gerber)
    except Exception as e:
        print(f'ERRO: {e}', file=sys.stderr)
        return 1
    if a.so_validar:
        if a.json:
            print(json.dumps(dict(rel.como_dict(), arquivos=[]), ensure_ascii=False, indent=1))
        else:
            print(f'Validando {p.nome}')
            _imprime(rel)
        return 0 if rel.ok else 1
    return _exportar(a, p, rel, saida)


def _exportar(a, p, rel, saida):
    if not a.json:
        print(f'Validando {p.nome}')
        _imprime(rel)
    if not rel.ok:
        if a.json:
            print(json.dumps(dict(rel.como_dict(), arquivos=[]), ensure_ascii=False, indent=1))
        else:
            print(f'{len(rel.erros)} erro(s): nada foi exportado. Corrija no KiCad e exporte de novo.')
        return 1
    if rel.avisos and not a.aceitar_avisos:
        if sys.stdin.isatty() and not a.json:
            try:
                r = input(f'{len(rel.avisos)} aviso(s). Exportar mesmo assim? [s/N] ').strip().lower()
            except EOFError:
                r = ''
            if r not in ('s', 'sim'):
                print('Cancelado.')
                return 2
        else:
            if a.json:
                print(json.dumps(dict(rel.como_dict(), arquivos=[]), ensure_ascii=False, indent=1))
            else:
                print('Ha avisos: rode de novo com --aceitar-avisos para exportar.')
            return 2
    res = exportar.gerar(p, rel, saida, previa=not a.sem_previa)
    if a.json:
        print(json.dumps(dict(rel.como_dict(), arquivos=res.arquivos, previas=res.previas),
                         ensure_ascii=False, indent=1))
    else:
        for c in res.arquivos + res.previas:
            print('  gerado: ' + c)
    return 0


def _ponto(s):
    m = re.match(r'^\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*$', s)
    if not m:
        raise argparse.ArgumentTypeError(f'ponto invalido: {s}, use X,Y')
    return float(m.group(1)), float(m.group(2))


def cmd_corrigir(a):
    texto = open(a.arquivo, encoding='ascii').read()
    m = re.search(r'\( FRESA fiduciais=(-?[\d.]+),(-?[\d.]+);(-?[\d.]+),(-?[\d.]+) \)', texto)
    if not m:
        print('ERRO: arquivo sem a linha FRESA fiduciais', file=sys.stderr)
        return 1
    v = [float(g) for g in m.groups()]
    desenho = [(v[0], v[1]), (v[2], v[3])]
    real = [corrigir.visto_pela_camera(p) for p in a.medido]
    f, info = corrigir.transformacao(desenho, real)
    dif = abs(info['dist_medida'] - info['dist_desenho'])
    print(f"  giro {info['giro_graus']:.2f} graus, centro da placa em "
          f"X{info['centro'][0]:.3f} Y{info['centro'][1]:.3f}")
    print(f"  distancia projeto {info['dist_desenho']:.3f}, medida {info['dist_medida']:.3f}, "
          f"diferenca {dif:.3f} mm")
    if dif > corrigir.TOL_DISTANCIA:
        print(f'ERRO: diferenca acima de {corrigir.TOL_DISTANCIA} mm, mire os fiduciais de novo.')
        return 1
    titulo = (f"CORRIGIDO pelos fiduciais: giro {info['giro_graus']:.2f} graus, centro da placa em "
              f"X{info['centro'][0]:.2f} Y{info['centro'][1]:.2f}")
    saida = a.saida or re.sub(r'\.nc$', '', a.arquivo) + '-CORRIGIDO.nc'
    with open(saida, 'w', encoding='ascii', newline='\n') as fh:
        fh.write(corrigir.aplicar(texto, f, titulo))
    print('  gerado: ' + saida)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='fresa', description='Gerbers do KiCad para os 3 arquivos do Candle')
    sub = ap.add_subparsers(dest='cmd', required=True)
    for nome in ('gerar', 'validar'):
        s = sub.add_parser(nome)
        s.add_argument('pasta')
        s.add_argument('--prefixo', help='inicio dos nomes, ex "blink blink-roteado-"')
        s.add_argument('--json', action='store_true')
        if nome == 'gerar':
            s.add_argument('--saida')
            s.add_argument('--aceitar-avisos', action='store_true')
            s.add_argument('--sem-previa', action='store_true')
    s = sub.add_parser('kicad', help='exporta direto de um .kicad_pcb pelo kicad-cli')
    s.add_argument('pcb')
    s.add_argument('--saida', help='padrao: pasta gcode ao lado da placa')
    s.add_argument('--pasta-gerber', help='onde gravar os Gerbers exportados, padrao: SAIDA/gerber')
    s.add_argument('--so-validar', action='store_true', help='exporta e valida, sem gerar os .nc')
    s.add_argument('--json', action='store_true')
    s.add_argument('--aceitar-avisos', action='store_true')
    s.add_argument('--sem-previa', action='store_true')
    s = sub.add_parser('corrigir')
    s.add_argument('arquivo')
    s.add_argument('--medido', nargs=2, type=_ponto, required=True,
                   metavar='X,Y', help='posicao da maquina com cada fiducial na mira, esquerda e direita')
    s.add_argument('--saida')
    a = ap.parse_args(argv)
    return {'gerar': cmd_gerar, 'validar': cmd_validar, 'kicad': cmd_kicad,
            'corrigir': cmd_corrigir}[a.cmd](a)
