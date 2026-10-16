"""Macros de abertura do KiCad e lado da solda por peca (placas do Roteador CNC).

Rode na pasta fresa-pcb:  .venv\\Scripts\\python -m pytest testes
"""
import json
import math
import os
import shutil
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
from fresa import gerber, kicad, placa, validacao  # noqa: E402

GERBER = os.path.join(AQUI, 'dados', 'blink-v5')
PRE = 'blink blink-roteado-'

# as tres macros como o KiCad escreve (pad oval, retangular e arredondado girados)
MACROS = '''%FSLAX46Y46*%
%MOMM*%
%AMHorizOval*
0 Thick line with rounded ends*
0 $1 width*
0 $2 $3 position (X,Y) of the first rounded end (center of the circle)*
0 $4 $5 position (X,Y) of the second rounded end (center of the circle)*
0 Add line between two ends*
20,1,$1,$2,$3,$4,$5,0*
0 Add two circle primitives to create the rounded ends*
1,1,$1,$2,$3*
1,1,$1,$4,$5*%
%AMRotRect*
0 Rectangle, with rotation*
0 The origin of the aperture is its center*
0 $1 length*
0 $2 width*
0 $3 Rotation angle, in degrees counterclockwise*
0 Add horizontal line*
21,1,$1,$2,0,0,$3*%
%AMRoundRect*
0 Rectangle with rounded corners*
0 $1 Rounding radius*
0 $2 $3 $4 $5 $6 $7 $8 $9 X,Y pos of 4 corners*
0 Add a 4 corners polygon primitive as box body*
4,1,4,$2,$3,$4,$5,$6,$7,$8,$9,$2,$3,0*
0 Add four circle primitives for the rounded corners*
1,1,$1+$1,$2,$3*
1,1,$1+$1,$4,$5*
1,1,$1+$1,$6,$7*
1,1,$1+$1,$8,$9*
0 Add four rect primitives between the rounded corners*
20,1,$1+$1,$2,$3,$4,$5,0*
20,1,$1+$1,$4,$5,$6,$7,0*
20,1,$1+$1,$6,$7,$8,$9,0*
20,1,$1+$1,$8,$9,$2,$3,0*%
%TA.AperFunction,ComponentPad*%
%ADD10HorizOval,1.800000X-0.424264X0.424264X0.424264X-0.424264X0*%
%ADD11RotRect,2.000000X1.000000X45.000000*%
%ADD12RoundRect,0.250000X-0.750000X-0.250000X0.750000X-0.250000X0.750000X0.250000X-0.750000X0.250000X0*%
%TD*%
%TO.N,A*%
%TO.P,P1,1*%
D10*
X10000000Y5000000D03*
D11*
X20000000Y5000000D03*
D12*
X30000000Y5000000D03*
%TD*%
M02*
'''


def test_macros_do_kicad(tmp_path):
    c = tmp_path / 'm.gtl'
    c.write_text(MACROS)
    oval, rot, arred = gerber.ler(str(c))
    # oval 1,8 x 3,0 a 45 graus, centrado no flash
    assert oval.geom.area == pytest.approx(math.pi * 0.9 ** 2 + 1.2 * 1.8, rel=2e-3)
    assert oval.geom.centroid.x == pytest.approx(10) and oval.geom.centroid.y == pytest.approx(5)
    x0, y0, x1, y1 = oval.geom.bounds
    assert x1 - x0 == pytest.approx(1.2 / math.sqrt(2) + 1.8, rel=1e-2)
    # retangulo 2 x 1 girado 45: a rotacao nao pode ser escalada como comprimento
    assert rot.geom.area == pytest.approx(2.0)
    assert rot.geom.bounds[2] - rot.geom.bounds[0] == pytest.approx(3 / math.sqrt(2))
    # retangulo 2 x 1 com canto de raio 0,25 ($1+$1 e conta dentro da macro)
    assert arred.geom.area == pytest.approx(2 - (4 - math.pi) * 0.25 ** 2, rel=2e-3)
    assert arred.geom.bounds == pytest.approx((29.0, 4.5, 31.0, 5.5), abs=1e-3)
    assert {e.funcao for e in (oval, rot, arred)} == {'ComponentPad'}


def test_macro_em_polegadas(tmp_path):
    c = tmp_path / 'p.gtl'
    c.write_text(MACROS.replace('%MOMM*%', '%MOIN*%'))
    _, rot, _ = gerber.ler(str(c))
    assert rot.geom.area == pytest.approx(2.0 * 25.4 ** 2)


def test_lados_de_solda_do_kicad(tmp_path):
    pcb = tmp_path / 'p.kicad_pcb'
    pcb.write_text('''(kicad_pcb
\t(footprint "lib:R"
\t\t(layer "F.Cu")
\t\t(property "Reference" "R1" (at 0 0 0) (layer "F.SilkS"))
\t)
\t(footprint "lib:C"
\t\t(layer "B.Cu")
\t\t(property "Reference" "C1" (at 0 0 0) (layer "B.SilkS"))
\t)
\t(footprint "lib:via_termica"
\t\t(layer "F.Cu")
\t\t(property "Reference" "VIAT3" (at 0 0 0) (layer "F.SilkS"))
\t)
)
''', encoding='utf-8')
    assert kicad.lados_de_solda(str(pcb)) == {'R1': 'baixo', 'C1': 'cima', 'VIAT3': 'ambos'}


@pytest.fixture
def pasta(tmp_path):
    if not os.path.isdir(GERBER):
        pytest.skip('Gerbers da blink nao encontrados')
    for f in os.listdir(GERBER):
        if f.startswith(PRE):
            shutil.copy(os.path.join(GERBER, f), tmp_path)
    return tmp_path


def validar(pasta, lados):
    with open(os.path.join(pasta, PRE + placa.ARQ_LADOS), 'w', encoding='utf-8') as f:
        json.dump(lados, f)
    return validacao.validar(placa.carregar(str(pasta), PRE))


def test_peca_virada_e_soldada_em_cima(pasta):
    # a blink liga o R2 por baixo: virado, o anel de baixo nao liga em nada
    r = validar(pasta, {'R2': 'cima'})
    assert any('trilha de baixo encostando no pino R2' in m and 'so do lado de cima' in m for m in r.erros)
    assert not any('de cima encostando' in m for m in r.erros)


def test_pad_soldado_dos_dois_lados_aceita_trilha_nos_dois(pasta):
    c = os.path.join(pasta, PRE + 'F_Cu.gbr')
    t = open(c).read()
    open(c, 'w').write(t.replace('M02*', '%TO.N,Net-(D1-K)*%\nD13*\nX-1000000Y-1000000D02*\n'
                                          'X-1000000Y-3500000D01*\n%TD*%\nM02*'))
    assert any('trilha de cima encostando no pino R2' in m for m in validar(pasta, {}).erros)
    assert not any('encostando no pino R2' in m for m in validar(pasta, {'R2': 'ambos'}).erros)
