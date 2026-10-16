# Fresa PCB: especificação para o Claude Code

Objetivo: transformar tudo o que aprendemos fresando placas na TTC3018 em software, para que fazer uma placa de dupla face vire um processo de **3 fases** sem decisões manuais nem esquecimentos:

1. **Cobre de cima** (fresa em V)
2. **Furos** (broca 0,8, todos iguais, incluindo os 2 fiduciais)
3. **Cobre de baixo** (vira a placa, câmera acha os fiduciais, G-code corrigido, fresa em V)

São dois softwares:

- **A. Extensão do KiCad**: exporta o projeto direto para os 3 arquivos que o Candle aceita, com os processos, medidas e voos de teste embutidos, e valida o projeto antes de exportar.
- **B. Plugin do Candle**: um assistente de fases que guia a pessoa, impede os erros humanos clássicos e faz a virada da placa com a câmera.

Tudo o que está aqui foi medido ou validado na prática. Os números não são sugestões: são o que funcionou. A pasta `referencias/` tem o código Python que gerou as placas que deram certo; use como base, não reinvente.

Regras de escrita do projeto: textos para o usuário em português, **nunca usar travessão**, tema escuro nas interfaces.

---

## 1. A máquina (fatos fixos)

- TwoTrees **TTC3018 Pro**, GRBL rodando num **ESP32**, controlada pelo **Candle** (versão nova do Denvi, com plugins em JavaScript).
- Fins de curso nos 3 eixos, homing e limites de software já configurados e gravados no ESP32:
  - `$5=1` (sinal invertido), `$20=1` (soft limits), `$22=1` (homing), `$23=2` (direção do Y invertida), `$25=300`, `$27=1`
  - `$130=258`, `$131=123`, `$132=36`
  - Depois do homing a máquina fica em X=-1, Y=+1, Z=-1 (coordenadas de máquina).
- **Zero XY fixo (G54)** no centro da área útil, gravado e persistente. O fluxo diário é: liga, `$H`, probe do Z, roda. Nunca dependa do valor numérico do G54, só de que ele existe.
- **Probe do Z** com garra jacaré na broca e a placa no cobre (`G38.2`).
- **Botão de "ir para casa"** que já existe no Candle: `app.device.sendCommands(["G53 G0 Z-2", "G90", "G0 X0 Y0"]);`

### Alturas (lição aprendida com alarme)

Brocas de PCB têm um anel plástico que define o comprimento, e uma broca longa fez `G0 Z15` estourar o limite de software (ALARM:2). Por isso:

- **Altura segura** = `G53 G0 Z-2` (2 mm abaixo do topo da máquina). Funciona com qualquer ferramenta.
- **Deslocamento entre cortes/furos** = `Z2` (coordenada de trabalho), sempre dentro da área livre das garras.
- Nunca usar alturas de trabalho grandes como Z10 ou Z15.

---

## 2. Ferramentas e parâmetros de corte (validados)

### Fresa em V (cobre)
- 30°, ponta 0,3 mm. Largura do sulco ≈ `0,3 + 2·prof·tan(15°)`, ou seja ≈ 0,41 mm a 0,2 de profundidade.
- **Profundidade fixa 0,2 mm, sem heightmap.** Um único probe no centro da placa basta (testado).
- Isolação: largura efetiva da ferramenta no gerador `TOOL = 0,35`, **4 passadas**, passo `0,35 × 0,85 = 0,2975`.
- **A 1ª passada é sempre completa** (é ela que isola). As passadas 2 a 4 só alargam e são **cortadas fora da área das garras**.
- Avanços: corte **F100**, mergulho **F30**, aproximação a Z1 antes de mergulhar, spindle **M3 S1000** com `G4 P3` antes de cortar.

### Broca (furos)
- **Uma broca só: 0,8 mm para todos os furos** (componentes, vias, conectores e fiduciais). Decisão do projeto: furos padronizados, como numa perfboard.
- Furação em degraus: desce 0,4 mm por vez até -2,0, `F30`, volta a Z0,5 entre degraus, Z2 entre furos.

### Garras
- As garras prendem os 4 cantos da placa. Área proibida = triângulos de **11 mm** em cada canto.
- Para placa 30×30 centrada: área livre `|x| + |y| ≤ 19`. Generalizar para qualquer tamanho a partir do contorno (Edge.Cuts).
- A fresa em V é um cone: ela pode raspar na garra com a lateral mesmo com a ponta longe. Por isso existe o voo 2 em Z0,5 (abaixo).

---

## 3. Regras de projeto da placa (o que o KiCad tem que respeitar)

- Pads redondos **2,5 mm**; ovais **1,8 × 3,0** no passo de 2,54.
- Trilhas **1,0 mm** (mínimo 0,8). Isolação/clearance **0,5 mm**.
- Cobre a pelo menos **1 mm** da borda.
- Cantos: triângulos de 11 mm sem cobre (garras).
- **Furos: todos 0,8 mm.**
- **Solda de um lado só por peça:** peça normal é soldada embaixo, e trilha de cima nunca encosta no pad dela. Peça virada no KiCad (corpo no B.Cu, como o Roteador CNC faz para fechar a placa menor) é soldada em cima, e é a trilha de baixo que não pode encostar. (Vias, inclusive a via térmica `VIAT` do Roteador CNC, são fio soldado dos dois lados, pois não há furo metalizado.)
- **Fiduciais:** footprint `Fiducial_Furo_0.8` (biblioteca `fresa-rino`, já criado pelo usuário): furo NPTH de 0,8 com pad = furo e uma área de regra de 2×2 mm sem nada em F.Cu e B.Cu. Dois deles, **no meio da borda esquerda e no meio da borda direita, na mesma altura Y, a ~2 mm da borda** (na placa 30×30: X ±13, Y 0).
- **Origem** = centro do contorno da placa. Tudo é gerado com o (0,0) no centro.

---

## 4. A. Extensão do KiCad

### O que faz
Um botão no editor de PCB que:
1. Roda as **validações** (seção 4.2). Se algo falhar, mostra a lista e não exporta (ou exporta só se a pessoa confirmar avisos não críticos).
2. Exporta Gerbers + furação (via `kicad-cli` ou API) com origem no centro da placa.
3. Gera os 3 arquivos `.nc` (seção 4.3) numa pasta `gcode/` ao lado do projeto, mais uma imagem de prévia de cada lado.

### Arquitetura recomendada
- **Núcleo em Python puro** (Gerber/Excellon → geometria com `shapely` → G-code). Esse núcleo já existe e funciona: `referencias/gerar_gcode_v5_gen5.py` e `referencias/validar_gerbers_check.py` (o parser de Gerber está no começo do `check.py`).
- **Casca fina do KiCad** que só exporta e chama o núcleo. O usuário usa **KiCad 10**: confira qual API de plugin é a atual nessa versão (Action Plugin com `pcbnew` ou a API IPC nova) antes de escolher. Usar `kicad-cli` para exportar deixa o núcleo independente da API.
- O núcleo também deve funcionar pela linha de comando (aponta a pasta de Gerbers, saem os `.nc`), para testes.

### 4.2 Validações antes de exportar
Já implementadas no `check.py`, generalizar:
- **Conectividade:** cada rede tem que formar uma única ilha de cobre, juntando cima + baixo pelos furos. Rede partida = erro.
- **Curto:** número de ilhas = número de redes. Duas redes que se tocam = erro.
- **Vão entre redes** menor que 0,40 mm = aviso (a fresa pode não separar). Na v5 existiam vãos de 0,40 a 0,45 e funcionou.
- **Trilha encostando em pad de componente do lado sem solda** = erro (quebra a regra de solda de um lado só).
- **Furo diferente de 0,8** = aviso listando os furos.
- **Fiduciais:** exatamente 2, na mesma altura Y, um de cada lado. Senão, erro (sem eles a fase 3 não existe).
- **Cobre dentro dos triângulos das garras** = erro.
- Nada de ligação não roteada (ratsnest) = erro.

### 4.3 Os 3 arquivos gerados
Nomes: `1-cobre-cima.nc`, `2-furos.nc`, `3-cobre-baixo.nc`.

**Cabeçalho de máquina em cada arquivo**, para o plugin do Candle reconhecer:
```
( FRESA fase=1 lado=cima ferramenta=vbit30 placa=30.0x30.0 )
( FRESA fiduciais=-13.000,0.000;13.000,0.000 )
```
- O arquivo 3 é gerado **espelhado em X** (a placa vira como página de livro, esquerda para a direita) e **sem correção**. Ele **não deve ser rodado direto**: o plugin do Candle aplica a correção dos fiduciais antes. Marcar no cabeçalho `fase=3 corrigir=sim` e começar o corpo com um `M0` e um comentário de aviso, para que, se alguém rodar sem o plugin, a máquina pare.

**Regras de G-code (lição aprendida):**
- Comentários **nunca** podem ter parênteses dentro de parênteses: o GRBL dá `error:1`.
- Comentários sem acento (ASCII), para não depender da codificação.
- Início: `G21 G90 G17`, depois `G53 G0 Z-2`.
- Fim: `G53 G0 Z-2`, `M5`, `G0 X0 Y0`, `M30`.

### 4.4 Voos de teste (pre-flight), obrigatórios nos arquivos de cobre
São a parte que o usuário considera mais importante. Com o spindle **desligado**, antes de cortar:

- **Voo 1, em cruz, a Z2:** passa pelo **centro da placa**, ao longo de X e depois de Y, até os extremos do corte. Para **2 s** (`G4 P2`) em cada extremo, `F600`, sobe para Z5 entre as duas linhas. Serve para ver se o desenho cabe na placa.
- **Voo 2, no contorno, a Z0,5:** percorre o **contorno convexo de todos os pontos de corte** (simplificado: tira vértices que mudam o contorno menos de 0,3 mm), `F600`, uma volta fechada. Serve para ver se o cone da fresa vai raspar numa garra (a ponta fica quase na altura real de corte).
- Depois: `G53 G0 Z-2`, vai para o **centro da placa**, comentário explicando a pausa e **`M0`**. Só depois `M3 S1000`, `G4 P3` e o corte.
- No arquivo de furos não precisa de voo.

Exemplo real em `referencias/exemplo-1-cobre-cima.nc`.

---

## 5. B. Plugin do Candle

### Base técnica
- O Candle novo tem plugins em JavaScript: cada plugin é uma pasta dentro de **`candleplugins`** na pasta de instalação, com `config.ini`, `script.js` e telas `.ui` (Qt Designer).
- Já existe um plugin de **câmera** oficial (mira com posição, tamanho, cor, zoom). Use como modelo: código em `src/candleplugins/camera/script.js` no repositório https://github.com/Denvi/Candle, e a documentação em `help/en/plugins/` e `help/en/scripting/` (veja `objects.md` para saber o que o script consegue fazer com o programa carregado e com o dispositivo).
- Antes de projetar o fluxo, confirme na documentação: como o plugin lê e substitui o G-code carregado, como lê a posição da máquina e o estado (Idle, Alarm), e como envia comandos.

### 5.1 Assistente de fases
Uma tela com as 3 fases e o passo atual em destaque. Para cada fase:

1. **Lê o cabeçalho do arquivo carregado** e confere se é a fase esperada. Arquivo da fase errada = bloqueia.
2. **Ferramenta:** mostra qual ferramenta a fase exige (fresa em V ou broca 0,8). Se for diferente da fase anterior, exige confirmar "troquei a ferramenta".
3. **Probe do Z obrigatório:** depois de qualquer troca de ferramenta, o botão de rodar fica bloqueado até a pessoa fazer o probe pelo plugin. O probe é feito **no centro real da placa** (na fase 3, o centro já corrigido).
4. **Homing:** bloqueia se a máquina não estiver referenciada.
5. Roda o arquivo. Os voos de teste e o `M0` já estão nele.

Erros humanos que já aconteceram e o plugin deve impedir:
- Achar que acabou a furação e tirar a placa antes da hora (aconteceu: os fiduciais ficavam num arquivo separado). Com tudo num arquivo de furos isso some, mas o assistente deve mostrar claramente "fase 2 concluída, pode virar".
- Esquecer o probe depois de trocar a broca.
- Rodar o arquivo de baixo sem correção.

### 5.2 Calibração da câmera
- Endoscópio USB 7,3 mm (`USB2.0 PC CAMERA`), ligado **direto no PC** (no hub não funciona). Fixo no bloco do spindle, então sobe e desce junto com o Z.
- Calibração: na madeira da mesa há uma régua gravada com uma **cruz no 0,0** feita pela própria fresa. Leva a câmera até a cruz ficar no centro da mira; a posição de trabalho nesse momento é o **deslocamento câmera → broca**.
- **Valor atual:** com a cruz 0,0 no centro da mira, a broca está em **X +35,065, Y -6,000**. Ou seja:
  - para a câmera olhar o ponto (x, y): `G0 X(x+35.065) Y(y-6.000)`
  - ponto que a câmera vê: `(X-35.065, Y+6.000)`
- Guardar nas configurações do plugin, com botão "recalibrar" (refazer sempre que o suporte da câmera for mexido).
- Imagem: direita = +X, cima = +Y. Escala ≈ 0,1 mm por pixel em 640×480.
- **Altura de olhar:** sempre a mesma. Recomendo `G53 G0 Z-2` (topo) para calibrar e para medir, assim não depende do comprimento da ferramenta.

### 5.3 Virada da placa (fase 3)
1. O assistente pede para virar a placa **como página de livro, da esquerda para a direita**, e prender.
2. Leva a câmera para onde o fiducial da esquerda deveria estar (posição de desenho + deslocamento da câmera). A pessoa ajusta com o jog até o furo ficar no centro da mira e clica **"marcar fiducial 1"**.
3. Mesma coisa no da direita, **"marcar fiducial 2"**. Dica: depois do primeiro, já mande a câmera para a posição prevista corrigida pelo deslocamento medido no primeiro (economiza procura).
4. **Conferência:** a distância medida entre os dois tem que bater com a de projeto. Diferença acima de **0,1 mm** = pede para mirar de novo. (Resultados reais: teste 0,036 mm, v5 0,005 mm.)
5. Calcula a **transformação rígida** (giro + deslocamento, sem escala) e aplica em todo X/Y do arquivo 3. Código pronto e testado em `referencias/corrigir_fiduciais.py` (usa o ponto médio dos dois fiduciais para dividir o erro).
6. Gera os voos com a cruz passando pelo **centro real** da placa e o contorno já girado. Mostra o giro e o deslocamento encontrados.
7. Probe do Z no centro corrigido e roda.

**O mesmo método serve para recolocar uma placa que saiu do lugar sem virar** (sem espelhamento): usa dois furos que já existem, o mais afastados possível. Isso salvou a v5 depois de a placa ter sido tirada antes de furar os fiduciais.

---

## 6. Resultados que validam o método
- **Teste de alinhamento** (`referencias/gerar_teste_alinhamento.py`): barrinha de 3×15 mm com furo em cada ponta, fiduciais em X ±10. Placa virada ficou girada 3,4° e 7 mm fora; a barrinha de baixo caiu certinha nos furos de cima.
- **Blink v5**: placa recolocada com giro de -1,7° corrigida pela câmera; lado de baixo com giro de 1,1° corrigido.

## 7. Ordem sugerida de construção
1. Núcleo Python de linha de comando: Gerbers → validações → 3 arquivos `.nc` com voos e cabeçalhos. Testar reproduzindo os arquivos da blink v5.
2. Casca da extensão do KiCad.
3. Plugin do Candle: calibração da câmera e virada (5.2 e 5.3).
4. Plugin do Candle: assistente de fases e travas (5.1).
