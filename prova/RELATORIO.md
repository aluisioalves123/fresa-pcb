# Prova: o nucleo reproduz a blink v5

Gerbers: `testes\dados\blink-v5` (prefixo `blink blink-roteado-`)  
shapely 2.2.0, GEOS 3.14.1

## Validacao

- OK: nenhum erro de validacao (0 erros)
  - info: placa 30.00 x 30.00 mm
  - info: 8 redes, 1 ilhas em cima, 9 ilhas em baixo
  - info: menor vao entre redes no cobre de cima: 0.503 mm
  - info: menor vao entre redes no cobre de baixo: 0.401 mm
  - info: fiduciais em X-13.000 Y0.000 e X13.000 Y0.000, distancia 26.000 mm
  - info: areas proibidas: os 4 cantos e 2 de 2x2 mm em volta dos fiduciais
  - aviso: 2 furo(s) com diametro diferente de 0.8, serao feitos com a broca 0.8: 1.00 em X2.50 Y-4.25, 1.00 em X2.50 Y-6.79
  - aviso: o sulco da primeira passada no cobre de cima entra 0.12 mm numa area proibida perto de X-10.40 Y-8.69: e ela que isola o cobre ali, entao nao da para tirar; afaste o cobre uns 0.2 mm se a fresa nao puder passar
  - aviso: o sulco da primeira passada no cobre de baixo entra 0.12 mm numa area proibida perto de X-10.40 Y-8.69: e ela que isola o cobre ali, entao nao da para tirar; afaste o cobre uns 0.2 mm se a fresa nao puder passar

## Arquivo 1, cobre de cima

- OK: cortes identicos, ponto a ponto, ao gerador original rodado agora (63 caminhos, 4936 pontos)
- OK: contra exemplo-1-cobre-cima.nc: 63 x 63 caminhos, mesma ordem, 48 identicos, maior desvio 0.003 mm (limite 0.05)
- OK: voo 1 em cruz com os mesmos 4 extremos do exemplo: (-11.567, 0.000), (11.317, 0.000), (0.000, -12.817), (0.000, 14.468)
- OK: voo 2 no contorno com os mesmos 14 vertices do exemplo

## Arquivo 2, furos

- OK: os 24 furos de exemplo-2-furos.nc estao todos no arquivo 2
- OK: 28 furos = os 3 arquivos de furo do gerador original juntos (componentes e vias + conector + 2 fiduciais), agora numa broca so
- OK: ciclo de furacao identico ao exemplo: G0 Z0.5 / G1 Z-0.40 F30 / G0 Z0.5 / G1 Z-0.80 F30 / G0 Z0.5 / G1 Z-1.20 F30 / G0 Z0.5 / G1 Z-1.60 F30 / G0 Z0.5 / G1 Z-2.00 F30 / G0 Z0.5 / G0 Z2

## Arquivo 3, cobre de baixo

- OK: cortes identicos ao 4-cobre-baixo-SEM-CORRECAO do gerador original (49 caminhos, espelhado em X)
- OK: 49 x 49 caminhos contra exemplo-4-cobre-baixo-CORRIGIDO.nc
- OK: correcao que leva o arquivo 3 ao exemplo-4: giro 1.102 graus, centro X-1.165 Y-4.950; o exemplo diz `( CORRIGIDO pelos fiduciais: giro 1.10 graus, centro da placa em X-1.16 Y-4.95 )`
- OK: arquivo 3 corrigido pelos fiduciais (camera em X20.902 Y-11.200 e X46.898 Y-10.700) contra o exemplo-4: maior desvio 0.004 mm
- OK: a correcao tira a trava M0 do inicio e marca corrigir=feito

## Regras de G-code

- OK: 1-cobre-cima.nc: cabecalho FRESA, ASCII, inicio e fim padrao, sem Z alto
- OK: 2-furos.nc: cabecalho FRESA, ASCII, inicio e fim padrao, sem Z alto
- OK: 3-cobre-baixo.nc: cabecalho FRESA, ASCII, inicio e fim padrao, sem Z alto

## Areas proibidas

- na regra da v5, o sulco entrava ate 0.194 mm nas areas proibidas (o centro da fresa parava na beira)
- OK: cima: nenhuma passada recortavel entra nas areas proibidas (0.000 mm)
- OK: cima: a 1a passada, que isola o cobre, entra 0.112 mm e a validacao avisa
- OK: baixo: nenhuma passada recortavel entra nas areas proibidas (0.000 mm)
- OK: baixo: a 1a passada, que isola o cobre, entra 0.112 mm e a validacao avisa
- os caminhos de corte do arquivo 1 so mudam onde as passadas 2 a 4 encostavam nas areas: 71 caminhos contra 63

## Resultado

**TUDO OK**

Arquivos gerados em `prova/gcode/` (regra atual) e `prova/gcode/regra-v5/` (regra da v5, usada na comparacao).
