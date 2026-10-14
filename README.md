# Fresa PCB

Placa de dupla face fresada em casa, na TwoTrees TTC3018 Pro com Candle, em **3 fases** sem decisões manuais nem esquecimentos:

1. **Cobre de cima** (fresa em V 30°)
2. **Furos** (broca 0,8 em todos, incluindo os 2 fiduciais)
3. **Cobre de baixo** (vira a placa, a câmera acha os fiduciais, o G-code é corrigido)

Tudo o que está aqui foi medido ou validado fresando placas de verdade. A especificação completa, com as medidas e as lições aprendidas, está em [`ESPECIFICACAO.md`](ESPECIFICACAO.md).

## Estado

| Passo | O que é | Estado |
|---|---|---|
| 1 | Núcleo em Python: Gerbers → validações → 3 arquivos `.nc` com voos de teste | pronto, provado contra a blink v5 |
| 2 | Plugin do KiCad 10: um botão que valida e gera os 3 arquivos | pronto |
| 3 | Plugin do Candle: calibração da câmera e virada da placa | a fazer |
| 4 | Plugin do Candle: assistente de fases e travas | a fazer |

## Plugin do KiCad

Plugin no jeito clássico (ActionPlugin do `pcbnew`). A janela roda dentro do KiCad. O cálculo (shapely, matplotlib) roda num processo separado, no ambiente `.venv-kicad` criado com o Python do próprio KiCad, para nada brigar com o numpy e o wx que o KiCad já carregou.

Instalar ou atualizar:

```
python instalar_plugin_kicad.py
```

Isso cria `.venv-kicad` (só na primeira vez) e copia `kicad_plugin/` para `Documentos/KiCad/10.0/scripting/plugins/fresa_pcb`, com um `config.json` apontando para esta pasta. O núcleo roda direto daqui: mudou `fresa/`, não precisa reinstalar; mudou `kicad_plugin/`, rode de novo. No KiCad: **Ferramentas > Plugins externos > Atualizar plugins**.

O botão **Exportar para a fresa**:

1. grava uma cópia da placa como está na tela numa pasta temporária (o arquivo do projeto não é salvo nem alterado);
2. exporta dessa cópia, numa pasta de rascunho, F.Cu, B.Cu, Edge.Cuts e a furação PTH/NPTH com a origem de furação;
3. roda as validações do núcleo e o DRC do KiCad só para ligações não roteadas, sem gravar nada ainda;
4. com erro, mostra a lista e não deixa gerar; sem erro, mostra **Gerar arquivos** (ou **Gerar mesmo assim**, se houver aviso);
5. **Salvar em** mostra a pasta de saída (padrão: `gcode/` ao lado do projeto); **Trocar pasta...** escolhe outra, e o plugin lembra a escolha para cada placa (em `%APPDATA%/fresa-pcb/pastas.json`);
6. ao gerar, grava os 3 `.nc`, as prévias e os Gerbers na pasta escolhida e mostra as prévias.

## Linha de comando

Instalar o núcleo para usar sem o KiCad:

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Usar:

```
.venv\Scripts\python -m fresa kicad    "placa.kicad_pcb"
.venv\Scripts\python -m fresa validar  "pasta-dos-gerbers" --prefixo "blink blink-roteado-"
.venv\Scripts\python -m fresa gerar    "pasta-dos-gerbers" --prefixo "blink blink-roteado-"
.venv\Scripts\python -m fresa corrigir "gcode\3-cobre-baixo.nc" --medido 20.902,-11.200 46.898,-10.700
```

- `kicad` exporta pelo `kicad-cli` e faz o mesmo que o botão. `--so-validar` só valida; `--pasta-gerber` escolhe onde ficam os Gerbers.
- Com erro de validação nada é gerado (saída 1). Com aviso, pergunta; fora de um terminal precisa de `--aceitar-avisos` (senão saída 2). `--json` devolve o relatório para outros programas.
- `--prefixo` só é preciso quando a pasta tem mais de um projeto.
- `corrigir` é o plano B da fase 3 sem o plugin do Candle: recebe a posição da máquina com cada fiducial na mira da câmera (esquerda e direita) e grava o `-CORRIGIDO.nc`. Recusa se a distância medida errar mais que 0,1 mm.

Exportação esperada do KiCad (o plugin já faz assim): Gerber **X2 com atributos de netlist**, furação em formato **decimal métrico**, PTH e NPTH em arquivos separados. Sem os atributos de rede o núcleo dá erro, porque as validações dependem deles.

## Validações

Antes de gerar qualquer arquivo:

- **erro:** rede partida ou ligação não roteada, curto entre redes, trilha de cima encostando em pino de componente (a solda é só embaixo), fiduciais faltando ou desalinhados, cobre dentro dos triângulos das garras, Gerber sem atributos de rede;
- **aviso:** vão entre redes menor que 0,40 mm, furo diferente de 0,8, primeira passada encostando na garra, cobre a menos de 1 mm da borda ou na área do fiducial.

## Prova com a blink v5

A blink v5 foi a placa fresada com o gerador original (`referencias/`). Os Gerbers dela estão em `testes/dados/blink-v5/`.

```
.venv\Scripts\python provar_blink_v5.py
.venv\Scripts\python -m pytest testes
```

O relatório fica em [`prova/RELATORIO.md`](prova/RELATORIO.md). Resumo:

| Arquivo | Comparado com | Resultado |
|---|---|---|
| 1, cobre de cima | gerador original rodado agora | idêntico, ponto a ponto |
| 1, cobre de cima | `exemplo-1-cobre-cima.nc` | 63 caminhos na mesma ordem, maior desvio 0,003 mm; voo 1 e voo 2 idênticos |
| 2, furos | `exemplo-2-furos.nc` + Excellon | os 28 furos (24 + conector + 2 fiduciais) num arquivo só, ciclo idêntico |
| 3, cobre de baixo | `exemplo-4-cobre-baixo-CORRIGIDO.nc` | corrigido com giro 1,10° e centro X-1,16 Y-4,95 (o que diz o exemplo), maior desvio 0,004 mm |

Os desvios de milésimos vêm da versão do shapely/GEOS (o `simplify(0.005)` escolhe vértices um pouco diferentes), não do algoritmo.

## Decisões (o plugin do Candle precisa seguir)

- **Coordenadas de placa sempre com 3 casas** (`G0 X0.000 Y0.000` inclusive). Só o `G0 X0 Y0` do fim, sem casas, não é coordenada de placa. A correção mexe em toda linha `G0/G1 X#.### Y#.###` e em nenhuma outra.
- **Fiduciais no cabeçalho** estão no sistema do próprio arquivo, ordenados por X (esquerda primeiro). No arquivo 3 já estão espelhados.
- **Trava do arquivo 3:** comentário que começa com `( ATENCAO: arquivo SEM correcao` seguido de `M0`, logo após o cabeçalho. A correção tira as duas linhas e troca `corrigir=sim` por `corrigir=feito`.
- **Pausa dos voos:** vai para o centro da placa com `G0 X0.000 Y0.000`, então depois da correção a pausa fica no centro real.
- **Voo 2:** casco convexo de todos os pontos de corte; tira, um por vez, o vértice que muda menos o contorno, enquanto a mudança for menor que 0,3 mm. Na blink dá exatamente os 13 vértices do exemplo.
- **Garras:** 4 semiplanos a partir dos cantos do retângulo que envolve o Edge.Cuts (na 30×30 vira `|x|+|y| ≤ 19`).
- **Origem:** se os Gerbers não vierem com a origem no centro, o núcleo desloca tudo e informa.
- **Conectividade sem furo metalizado:** pino de componente liga só embaixo; só a via liga cima e baixo. Ilha de cima que é só pad de componente é ignorada.
- **Furos:** todos com a broca 0,8, ordem por vizinho mais próximo a partir do centro.
- Macros de abertura (pads retangulares arredondados) não são suportadas: a regra do projeto é pad redondo ou oval, e o erro diz isso.

## Estrutura

```
fresa/gerber.py           leitor Gerber X2 (formato, polegadas, arcos, regiões)
fresa/excellon.py         leitor de furação
fresa/placa.py            carrega, centraliza, garras
fresa/validacao.py        validações
fresa/caminhos.py         isolação (igual à v5), ordem, contorno do voo 2
fresa/gcode.py            cabeçalhos, voos de teste, cortes e furos
fresa/exportar.py         junta tudo
fresa/previa.py           PNG de cada lado, tema escuro
fresa/corrigir.py         correção pelos fiduciais (referência para o plugin do Candle)
fresa/kicad.py            ponte com o kicad-cli
fresa/cli.py              linha de comando
kicad_plugin/             plugin do KiCad (ActionPlugin)
instalar_plugin_kicad.py  instala o plugin e o ambiente .venv-kicad
provar_blink_v5.py        prova contra os arquivos reais da blink v5
referencias/              código e G-code que fresaram as placas que deram certo
testes/                   testes, com os Gerbers da blink v5
```
