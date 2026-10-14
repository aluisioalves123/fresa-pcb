"""Escreve os 3 arquivos .nc (secao 4.3 e 4.4 da especificacao).

Convencao para o plugin do Candle: toda coordenada X/Y de placa sai com 3 casas
decimais (G0 X0.000 Y0.000 inclusive). So o G0 X0 Y0 final, sem casas, nao e
coordenada de placa e nao deve ser corrigido.
"""
import math
import unicodedata

from . import caminhos as cam

DEPTH = cam.DEPTH
F_CORTE, F_MERGULHO, F_VOO = 100, 30, 600
Z_APROX, Z_DESLOC = 1, 2
Z_VOO1, Z_VOO1_ENTRE, Z_VOO2 = 2, 5, 0.5
TOPO = 'G53 G0 Z-2'
INICIO = ['G21 G90 G17', TOPO]
SPIN = ['M3 S1000', 'G4 P3']
FIM = [TOPO, 'M5', 'G0 X0 Y0', 'M30']

BROCA = 0.8
FURO_PASSO, FURO_FUNDO, FURO_ALIVIO = 0.4, 2.0, 0.5

f3 = lambda v: f'{v:.3f}' if abs(v) >= 0.0005 else '0.000'


def comentario(texto):
    """Comentario seguro para o GRBL: ASCII, sem parenteses dentro."""
    t = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    t = t.replace('(', '[').replace(')', ']').replace('\n', ' ')
    return f'( {t} )'


def cabecalho_maquina(fase, lado, ferramenta, placa, fiduciais, extra=''):
    fid = ';'.join(f'{f3(x)},{f3(y)}' for x, y in fiduciais)
    return [
        comentario(f'FRESA fase={fase} lado={lado} ferramenta={ferramenta} '
                   f'placa={placa.largura:.1f}x{placa.altura:.1f}{extra}'),
        comentario(f'FRESA fiduciais={fid}'),
    ]


def voos(P, furos=()):
    """Voo 1 em cruz pelo centro a Z2 e voo 2 no contorno a Z0.5, fresa desligada.
    Com furos (arquivo 1), os dois voos cobrem o corte E os furos: os fiduciais ficam fora do
    cobre, perto da beira, e e preciso saber logo no comeco se eles cabem na placa."""
    pontos = list(P) + [[tuple(f)] for f in furos]
    x0, x1, y0, y1 = cam.extremos(pontos)
    o_que = 'o desenho e os furos cabem' if furos else 'o desenho cabe'
    G = [comentario('VOO 1 em cruz pelo centro da placa, fresa DESLIGADA, Z2: '
                    f'para 2 s em cada extremo, confira se {o_que} na placa'),
         comentario(f'extremos do corte{" e dos furos" if furos else ""}: '
                    f'X {x0:.1f} a {x1:.1f} | Y {y0:.1f} a {y1:.1f}')]
    if furos:
        G.append(comentario('os fiduciais ficam na linha do centro: as paradas em X sao em cima deles'))
    for a, b in [((x0, 0), (x1, 0)), ((0, y0), (0, y1))]:
        G += [f'G0 X{f3(a[0])} Y{f3(a[1])}', f'G0 Z{Z_VOO1}', 'G4 P2',
              f'G1 X{f3(b[0])} Y{f3(b[1])} F{F_VOO}', 'G4 P2', f'G0 Z{Z_VOO1_ENTRE}']
    H = cam.contorno_voo(pontos)
    G += [comentario(f'VOO 2 no contorno de tudo o que vai ser cortado{" e furado" if furos else ""}, '
                     'fresa DESLIGADA, Z0.5: confira se a ponta passa longe das areas proibidas'),
          f'G0 X{f3(H[0][0])} Y{f3(H[0][1])}', f'G0 Z{Z_VOO2}', 'G4 P2']
    G += [f'G1 X{f3(x)} Y{f3(y)} F{F_VOO}' for x, y in H[1:] + [H[0]]]
    G += ['G4 P2', TOPO, 'G0 X0.000 Y0.000',
          comentario('PAUSA: voos conferidos? Aperte Pause de novo no Candle para ligar a fresa '
                     'e cortar, ou Stop para cancelar'),
          'M0']
    return G, H, (x0, x1, y0, y1)


def cortes(P):
    G = []
    for p in P:
        G += [f'G0 X{f3(p[0][0])} Y{f3(p[0][1])}', f'G0 Z{Z_APROX}', f'G1 Z-{DEPTH} F{F_MERGULHO}']
        G += [f'G1 X{f3(x)} Y{f3(y)} F{F_CORTE}' for x, y in p[1:]]
        G += [f'G0 Z{Z_DESLOC}']
    return G


def arquivo_cobre(placa, P, fase, fiduciais_arquivo, titulo, rede_borda=None, furos=()):
    lado = 'cima' if fase == 1 else 'baixo'
    extra = '' if fase == 1 else ' espelhado=x corrigir=sim'
    G = cabecalho_maquina(fase, lado, 'vbit30', placa, fiduciais_arquivo, extra)
    if fase == 3:
        G += [comentario('ATENCAO: arquivo SEM correcao, espelhado em X para a placa virada. '
                         'Rode so pelo plugin FRESA do Candle, que corrige pelos fiduciais '
                         'e tira esta parada'),
              'M0']
    G += [comentario(titulo),
          comentario(f'V-bit 30 graus | {cam.PASSES} passadas | profundidade {DEPTH} | sem heightmap'),
          comentario('zero XY: G54 apos homing | zero Z: probe no cobre, uma vez so, no centro da placa')]
    if rede_borda:
        G.append(comentario(f'borda: o plano {rede_borda} vai ate a beira e nao e isolado dela, '
                            f'todas as outras redes tem isolacao completa'))
    G += INICIO
    gv, H, cruz = voos(P, furos)
    G += gv + SPIN + cortes(P) + FIM
    return G, H, cruz


def arquivo_furos(placa, furos, fiduciais_arquivo, titulo):
    G = cabecalho_maquina(2, 'cima', f'broca{BROCA}', placa, fiduciais_arquivo)
    G += [comentario(titulo),
          comentario(f'broca {BROCA} em todos os furos, inclusive os 2 fiduciais | '
                     f'desce {FURO_PASSO} mm por vez ate -{FURO_FUNDO}'),
          comentario('zero XY: G54 apos homing | zero Z: probe no cobre com a broca')]
    G += INICIO + SPIN
    for x, y in furos:
        G += [f'G0 X{f3(x)} Y{f3(y)}', f'G0 Z{FURO_ALIVIO}']
        z = 0.0
        while z > -FURO_FUNDO + 1e-9:
            z = max(z - FURO_PASSO, -FURO_FUNDO)
            G += [f'G1 Z{z:.2f} F{F_MERGULHO}', f'G0 Z{FURO_ALIVIO}']
        G += [f'G0 Z{Z_DESLOC}']
    G += FIM
    return G


def conferir(linhas):
    """Regras do GRBL: comentario sem parenteses aninhados e so ASCII."""
    for n, l in enumerate(linhas, 1):
        if not l.isascii():
            raise ValueError(f'linha {n} com caractere nao ASCII: {l}')
        prof = 0
        for ch in l:
            prof += (ch == '(') - (ch == ')')
            if prof > 1 or prof < 0:
                raise ValueError(f'linha {n} com parenteses aninhados: {l}')
        if prof:
            raise ValueError(f'linha {n} com parenteses abertos: {l}')
