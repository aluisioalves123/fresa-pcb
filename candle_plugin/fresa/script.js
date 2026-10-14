// Fresa PCB: plugin do Candle.
// Passo 3 da ESPECIFICACAO.md: calibracao da camera (5.2) e correcao pelos fiduciais (5.3).
// A camera continua na janela "Camera" oficial; este painel so le a posicao da maquina,
// faz a conta (nucleo.js) e troca o programa carregado pelo corrigido.

script.importExtension("qt.core");
script.importExtension("qt.gui");
script.importExtension("qt.widgets");
script.importExtension("qt.uitools");

var pluginPath = script.path;
var pluginName = script.name;
var designerPluginsPath = app.path + "/designerplugins";
var loader = new QUiLoader();
var ui;

var VERMELHO = "#ff5a5a", AMARELO = "#ffd84a", VERDE = "#7dff6a", CINZA = "#9aa0a6";
var CAM_PADRAO = [35.065, -6.000];        // valor medido em 2026-10, recalibre se mexer no suporte

var medido = [null, null];                // posicao da maquina com cada fiducial na mira
var trans = null;                         // ultima transformacao calculada
var arquivoVisto = null;
var confirmacaoPendente = null;

eval(lerTexto(pluginPath + "/nucleo.js"));  // define FresaNucleo
var N = FresaNucleo;

// ---------- utilitarios ----------

function lerTexto(caminho) {
    var f = new QFile(caminho);
    if (!f.open(QIODevice.ReadOnly)) throw "nao consegui ler " + caminho;
    var s = new QTextStream(f);
    s.setCodec("UTF-8");
    var t = s.readAll();
    f.close();
    return t;
}

function gravarTexto(caminho, texto) {
    var f = new QFile(caminho);
    if (!f.open(QIODevice.WriteOnly)) return false;
    var s = new QTextStream(f);
    s.setCodec("UTF-8");
    s.writeString(texto);
    f.close();
    return true;
}

function cor(c, t) { return "<span style=\"color:" + c + "\">" + t + "</span>"; }
function n3(v) { return v.toFixed(3); }

function avisar(texto) {
    try {
        QMessageBox.warning(app.window, "Fresa PCB", texto);
    } catch (e) {
        ui.lblDica.text = cor(VERMELHO, texto);
    }
}

// Pergunta sim/nao. Se a caixa de dialogo nao existir nesta versao do Candle,
// cai num "clique de novo para confirmar".
function confirmar(texto, chave, acao) {
    try {
        if (QMessageBox.question(app.window, "Fresa PCB", texto) == QMessageBox.Yes) acao();
        return;
    } catch (e) {}
    if (confirmacaoPendente === chave) {
        confirmacaoPendente = null;
        acao();
    } else {
        confirmacaoPendente = chave;
        ui.lblDica.text = cor(AMARELO, texto + " Clique de novo para confirmar.");
    }
}

function cam() {
    var g = app.storage.group(pluginName);
    return [parseFloat(g.value("camX", CAM_PADRAO[0])), parseFloat(g.value("camY", CAM_PADRAO[1]))];
}

function posicaoAtual() {
    return [app.device.work.x, app.device.work.y];
}

// Maquina parada e nenhum programa sendo enviado.
function podeMover() {
    var s = app.sender.state;
    if (s == 0 || s == 1 || s == 2 || s == 5) {
        avisar("Tem um programa rodando ou pausado. Pare o programa antes.");
        return false;
    }
    if (app.device.state != 1) {
        avisar("A máquina precisa estar parada e pronta (Idle). Faça o homing ou desbloqueie antes.");
        return false;
    }
    return true;
}

// Sobe ao topo da maquina (vale para qualquer ferramenta) e vai ao ponto.
function mover(p) {
    if (!podeMover()) return false;
    app.device.sendCommands(["G53 G0 Z-2", "G90 G0 X" + n3(p[0]) + " Y" + n3(p[1])]);
    return true;
}

function lerPonto(txt) {
    var m = /^\s*(-?[\d.]+)\s*[,;]\s*(-?[\d.]+)\s*$/.exec(txt.text);
    if (!m) {
        avisar("Posição inválida: use X, Y (por exemplo -13, 0).");
        return null;
    }
    return [parseFloat(m[1]), parseFloat(m[2])];
}

// ---------- programa carregado ----------

function programa() {
    var linhas = app.program.lines;
    return { linhas: linhas, cab: N.lerCabecalho(linhas), nome: app.program.fileName };
}

function atualizarPrograma(forcar) {
    var nome = app.program.fileName;
    if (!forcar && nome === arquivoVisto) return;
    arquivoVisto = nome;
    var p = programa();
    var curto = nome ? new QFileInfo(nome).fileName() : "programa sem arquivo";
    if (!p.cab) {
        ui.lblArquivo.text = curto + "<br>" + cor(CINZA, "Sem cabeçalho FRESA: dá para corrigir digitando a posição de 2 furos.");
    } else {
        var t = curto + "<br>fase " + p.cab.fase + ", lado " + (p.cab.lado || "?");
        if (p.cab.corrigir === "sim") t += "<br>" + cor(AMARELO, "Precisa da correção antes de rodar.");
        else if (p.cab.corrigir === "feito") t += "<br>" + cor(VERDE, "Já corrigido.");
        ui.lblArquivo.text = t;
        if (p.cab.fiduciais && p.cab.corrigir !== "feito") {
            ui.txtF1.text = n3(p.cab.fiduciais[0][0]) + ", " + n3(p.cab.fiduciais[0][1]);
            ui.txtF2.text = n3(p.cab.fiduciais[1][0]) + ", " + n3(p.cab.fiduciais[1][1]);
            medido = [null, null];
            trans = null;
            mostrarResultado();
        }
    }
    atualizarBotoes();
}

// ---------- tela ----------

function atualizarCamera() {
    var c = cam();
    ui.lblCamera.text = "Com a cruz 0,0 da mesa na mira, a máquina está em X " + n3(c[0]) + "  Y " + n3(c[1]) + ".";
}

function atualizarBotoes() {
    var p = programa();
    var jaFeito = p.cab && p.cab.corrigir === "feito";
    ui.cmdAplicar.enabled = !!(trans && trans.ok && p.linhas.length && !jaFeito);
    ui.cmdCentro.enabled = !!trans;
    ui.lblF1.text = "Fiducial 1" + (medido[0] ? " ✓" : "");
    ui.lblF2.text = "Fiducial 2" + (medido[1] ? " ✓" : "");
}

function mostrarResultado() {
    if (!medido[0] && !medido[1]) {
        ui.lblResultado.text = "";
        ui.lblDica.text = cor(CINZA, "Vire a placa como página de livro, da esquerda para a direita, e prenda. "
            + "Depois: Ir no fiducial 1, ajuste com o jog até o furo ficar no centro da mira e Marcar. Repita no 2.");
        return;
    }
    if (!trans) {
        ui.lblResultado.text = "";
        ui.lblDica.text = cor(CINZA, "Agora o fiducial 2: Ir já mira perto do lugar certo, ajuste e Marcar.");
        return;
    }
    var t = "Distância: projeto " + n3(trans.distDesenho) + ", medida " + n3(trans.distMedida)
        + ", diferença " + n3(trans.diferenca) + " mm<br>"
        + "Giro " + trans.giroGraus.toFixed(2) + "°, deslocamento X " + n3(trans.desloc[0]) + " Y " + n3(trans.desloc[1])
        + "<br>Centro real da placa: X " + n3(trans.centro[0]) + " Y " + n3(trans.centro[1]);
    ui.lblResultado.text = t;
    if (trans.ok) {
        ui.lblDica.text = cor(VERDE, "Medida confere. Aplicar correção troca o programa pelo corrigido.");
    } else {
        ui.lblDica.text = cor(VERMELHO, "Diferença acima de " + N.TOL_DISTANCIA + " mm: mire os dois fiduciais de novo.");
    }
}

function recalcular() {
    trans = null;
    if (medido[0] && medido[1]) {
        var d1 = lerPonto(ui.txtF1), d2 = lerPonto(ui.txtF2);
        if (!d1 || !d2) return;
        var c = cam();
        trans = N.transformacao([d1, d2], [N.vistoPelaCamera(medido[0], c), N.vistoPelaCamera(medido[1], c)]);
    }
    mostrarResultado();
    atualizarBotoes();
}

// ---------- botoes ----------

function onOlharCruz() {
    mover(N.posicaoParaVer([0, 0], cam()));
    ui.lblDica.text = cor(CINZA, "Ajuste só X e Y com o jog até a cruz ficar no centro da mira, e clique Calibrar aqui.");
}

function onCalibrar() {
    if (!podeMover()) return;
    var p = posicaoAtual();
    confirmar("A cruz 0,0 da mesa está no centro da mira, com a máquina no topo (G53 Z-2)?\n\n"
        + "O deslocamento da câmera passa a ser X " + n3(p[0]) + "  Y " + n3(p[1]) + ".", "calibrar", function () {
            var g = app.storage.group(pluginName);
            g.setValue("camX", p[0]);
            g.setValue("camY", p[1]);
            atualizarCamera();
            recalcular();
            ui.lblDica.text = cor(VERDE, "Câmera calibrada.");
        });
}

function onIr(i) {
    return function () {
        atualizarPrograma(false);
        var alvo = lerPonto(i === 0 ? ui.txtF1 : ui.txtF2);
        if (!alvo) return;
        // dica da especificacao: depois do primeiro, ja mira o segundo corrigido pelo erro do primeiro
        var outro = 1 - i;
        if (medido[outro]) {
            var dOutro = lerPonto(outro === 0 ? ui.txtF1 : ui.txtF2);
            var rOutro = N.vistoPelaCamera(medido[outro], cam());
            alvo = [alvo[0] + rOutro[0] - dOutro[0], alvo[1] + rOutro[1] - dOutro[1]];
        }
        mover(N.posicaoParaVer(alvo, cam()));
    };
}

function onMarcar(i) {
    return function () {
        if (!podeMover()) return;
        medido[i] = posicaoAtual();
        recalcular();
    };
}

function onAplicar() {
    if (!trans || !trans.ok) return;
    var s = app.sender.state;
    if (s == 0 || s == 1 || s == 2 || s == 5) {
        avisar("Tem um programa rodando ou pausado. Pare o programa antes.");
        return;
    }
    var p = programa();
    if (p.cab && p.cab.corrigir === "feito") {
        avisar("Este programa já foi corrigido. Carregue o arquivo original de novo.");
        return;
    }
    var novo = N.aplicar(p.linhas, trans.f, N.tituloCorrecao(trans));
    if (p.nome) {
        var saida = p.nome.replace(/\.(nc|gcode|ngc|tap|txt)$/i, "") + "-CORRIGIDO.nc";
        if (gravarTexto(saida, novo.join("\n") + "\n")) {
            app.loadFile(saida);
        } else {
            app.loadFile(novo);
        }
    } else {
        app.loadFile(novo);
    }
    atualizarPrograma(true);
    atualizarBotoes();
    ui.lblDica.text = cor(VERDE, "Programa corrigido carregado (giro " + trans.giroGraus.toFixed(2) + "°). "
        + "Agora: Broca no centro, probe do Z e rode. Os voos de teste já passam pelo centro real.");
}

function onCentro() {
    if (!trans) return;
    if (mover(trans.centro)) {
        ui.lblDica.text = cor(CINZA, "Broca sobre o centro real da placa. Faça o probe do Z aqui.");
    }
}

// ---------- ciclo de vida do plugin ----------

function init() {
    loader.setWorkingDirectory(new QDir(pluginPath));
    loader.addPluginPath(designerPluginsPath);
}

// O QtScript so enxerga os filhos DIRETOS de um widget pelo nome; os botoes ficam dentro
// dos quadros (QGroupBox). Junta todos num objeto so para o resto do script.
var NOMES = {
    grpCamera: ["lblCamera", "cmdOlharCruz", "cmdCalibrar"],
    grpVirada: ["lblArquivo", "lblF1", "txtF1", "cmdIr1", "cmdMarcar1", "lblF2", "txtF2", "cmdIr2",
                "cmdMarcar2", "lblResultado", "cmdAplicar", "cmdCentro", "lblDica"]
};

function juntarWidgets(raiz) {
    var u = {};
    for (var grupo in NOMES) {
        var g = raiz[grupo];
        if (!g) throw "widget.ui sem o quadro " + grupo;
        for (var i = 0; i < NOMES[grupo].length; i++) {
            var n = NOMES[grupo][i];
            if (!g[n]) throw "widget.ui sem o elemento " + n + " dentro de " + grupo;
            u[n] = g[n];
        }
    }
    return u;
}

function createPanelWidget() {
    var raiz = null;
    var f = new QFile(pluginPath + "/widget.ui");
    if (f.open(QIODevice.ReadOnly)) {
        raiz = loader.load(f);
        f.close();
    }
    ui = juntarWidgets(raiz);
    ui.cmdOlharCruz.clicked.connect(onOlharCruz);
    ui.cmdCalibrar.clicked.connect(onCalibrar);
    ui.cmdIr1.clicked.connect(onIr(0));
    ui.cmdIr2.clicked.connect(onIr(1));
    ui.cmdMarcar1.clicked.connect(onMarcar(0));
    ui.cmdMarcar2.clicked.connect(onMarcar(1));
    ui.cmdAplicar.clicked.connect(onAplicar);
    ui.cmdCentro.clicked.connect(onCentro);
    ui.txtF1.editingFinished.connect(recalcular);
    ui.txtF2.editingFinished.connect(recalcular);

    // o Candle nao avisa quando outro arquivo e aberto: confere de tempos em tempos
    var timer = new QTimer(raiz);
    timer.interval = 1000;
    timer.timeout.connect(function () { atualizarPrograma(false); });
    timer.start();

    atualizarCamera();
    atualizarPrograma(true);
    mostrarResultado();
    atualizarBotoes();
    return raiz;
}

function createWindowWidget() {
}

function createSettingsWidget() {
}
