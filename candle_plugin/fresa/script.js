// Fresa PCB: plugin do Candle. Faz uma coisa so: com o desenho aberto, voce marca os dois
// fiduciais pela camera e ele corrige o desenho (giro + deslocamento). Nao move a maquina.
// O deslocamento camera -> broca fica nas Configuracoes do Candle.

script.importExtension("qt.core");
script.importExtension("qt.gui");
script.importExtension("qt.widgets");
script.importExtension("qt.uitools");

var pluginPath = script.path;
var pluginName = script.name;
var loader = new QUiLoader();
var ui, uiSettings;

var VERMELHO = "#ff5a5a", AMARELO = "#ffd84a", VERDE = "#7dff6a", CINZA = "#9aa0a6";
var CAM_PADRAO = [35.065, -6.000];        // medido em 2026-10; mude nas Configuracoes

var medido = [null, null];                // posicao da maquina com cada fiducial na mira
var arquivoVisto = null;

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
        ui.lblResultado.text = cor(VERMELHO, texto);
    }
}

// O QtScript so enxerga pelo nome os filhos DIRETOS de um widget: por isso o .ui nao tem quadros.
function pegar(raiz, nomes) {
    var u = {};
    for (var i = 0; i < nomes.length; i++) {
        if (!raiz[nomes[i]]) throw "falta " + nomes[i] + " no .ui";
        u[nomes[i]] = raiz[nomes[i]];
    }
    return u;
}

function carregarUi(arquivo) {
    var f = new QFile(pluginPath + "/" + arquivo);
    if (!f.open(QIODevice.ReadOnly)) throw "nao consegui abrir " + arquivo;
    var w = loader.load(f);
    f.close();
    return w;
}

function cam() {
    var g = app.storage.group(pluginName);
    return [parseFloat(g.value("camX", CAM_PADRAO[0])), parseFloat(g.value("camY", CAM_PADRAO[1]))];
}

function programa() {
    var linhas = app.program.lines;
    return { linhas: linhas, cab: N.lerCabecalho(linhas), nome: app.program.fileName };
}

function rodando() {
    var s = app.sender.state;
    return s == 0 || s == 1 || s == 2 || s == 5;
}

// ---------- tela ----------

function transformacao() {
    var p = programa();
    if (!medido[0] || !medido[1] || !p.cab || !p.cab.fiduciais) return null;
    var c = cam();
    return N.transformacao(p.cab.fiduciais, [N.vistoPelaCamera(medido[0], c), N.vistoPelaCamera(medido[1], c)]);
}

function atualizar() {
    var p = programa();
    var nome = p.nome ? new QFileInfo(p.nome).fileName() : "programa sem arquivo";
    var pronto = false;
    if (!p.linhas.length) {
        ui.lblArquivo.text = "Nenhum programa carregado.";
    } else if (!p.cab || !p.cab.fiduciais) {
        ui.lblArquivo.text = nome + "<br>" + cor(CINZA, "Sem cabeçalho FRESA: só corrijo arquivos gerados pelo plugin do KiCad.");
    } else if (p.cab.corrigir === "feito") {
        ui.lblArquivo.text = nome + "<br>" + cor(VERDE, "Já corrigido.");
    } else {
        ui.lblArquivo.text = nome + "<br>" + cor(p.cab.corrigir === "sim" ? AMARELO : CINZA,
            p.cab.corrigir === "sim" ? "Precisa da correção antes de rodar." : "Pode corrigir se a placa saiu do lugar.");
        pronto = true;
    }
    ui.cmdMarcar1.enabled = pronto;
    ui.cmdMarcar2.enabled = pronto;
    ui.cmdMarcar1.text = "Marcar fiducial 1" + (medido[0] ? " ✓" : "");
    ui.cmdMarcar2.text = "Marcar fiducial 2" + (medido[1] ? " ✓" : "");

    var t = pronto ? transformacao() : null;
    ui.cmdCorrigir.enabled = !!(t && t.ok);
    if (!pronto) {
        ui.lblResultado.text = "";
    } else if (!t) {
        ui.lblResultado.text = cor(CINZA, "Leve a câmera até cada fiducial com o jog, centralize na mira e marque.");
    } else {
        ui.lblResultado.text = "Distância: projeto " + n3(t.distDesenho) + ", medida " + n3(t.distMedida)
            + ", diferença " + n3(t.diferenca) + " mm<br>Giro " + t.giroGraus.toFixed(2) + "°, deslocamento X "
            + n3(t.desloc[0]) + " Y " + n3(t.desloc[1]) + "<br>"
            + (t.ok ? cor(VERDE, "Medida confere.")
                    : cor(VERMELHO, "Diferença acima de " + N.TOL_DISTANCIA + " mm: marque os dois de novo."));
    }
}

// o Candle nao avisa quando outro arquivo e aberto: confere de tempos em tempos
function vigiar() {
    var nome = app.program.fileName;
    if (nome === arquivoVisto) return;
    arquivoVisto = nome;
    medido = [null, null];
    atualizar();
}

// ---------- botoes ----------

function onMarcar(i) {
    return function () {
        if (app.device.state != 1) {
            avisar("Espere a máquina parar (Idle) para marcar.");
            return;
        }
        medido[i] = [app.device.work.x, app.device.work.y];
        atualizar();
    };
}

function onCorrigir() {
    var t = transformacao();
    if (!t || !t.ok) return;
    if (rodando()) {
        avisar("Tem um programa rodando ou pausado. Pare antes de corrigir.");
        return;
    }
    var p = programa();
    var novo = N.aplicar(p.linhas, t.f, N.tituloCorrecao(t));
    var saida = p.nome ? p.nome.replace(/\.(nc|gcode|ngc|tap|txt)$/i, "") + "-CORRIGIDO.nc" : "";
    if (saida && gravarTexto(saida, novo.join("\n") + "\n")) {
        app.loadFile(saida);
    } else {
        app.loadFile(novo);
    }
    arquivoVisto = app.program.fileName;
    atualizar();
    ui.lblResultado.text = cor(VERDE, "Desenho corrigido: giro " + t.giroGraus.toFixed(2) + "°, centro da placa em X "
        + n3(t.centro[0]) + " Y " + n3(t.centro[1]) + ".");
}

// ---------- configuracoes (deslocamento da camera) ----------

function lerConfiguracoes() {
    var c = cam();
    uiSettings.txtCamX.text = n3(c[0]);
    uiSettings.txtCamY.text = n3(c[1]);
}

function gravarConfiguracoes() {
    var x = parseFloat(String(uiSettings.txtCamX.text).replace(",", "."));
    var y = parseFloat(String(uiSettings.txtCamY.text).replace(",", "."));
    var g = app.storage.group(pluginName);
    if (!isNaN(x)) g.setValue("camX", x);
    if (!isNaN(y)) g.setValue("camY", y);
    if (ui) atualizar();
}

// ---------- ciclo de vida do plugin ----------

function init() {
    loader.setWorkingDirectory(new QDir(pluginPath));
    app.settingsLoaded.connect(lerConfiguracoes);
    app.settingsSaved.connect(gravarConfiguracoes);
    app.settingsRejected.connect(lerConfiguracoes);
    app.settingsSetByDefault.connect(function () {
        uiSettings.txtCamX.text = n3(CAM_PADRAO[0]);
        uiSettings.txtCamY.text = n3(CAM_PADRAO[1]);
    });
}

function createPanelWidget() {
    var raiz = carregarUi("widget.ui");
    ui = pegar(raiz, ["lblArquivo", "cmdMarcar1", "cmdMarcar2", "lblResultado", "cmdCorrigir"]);
    ui.cmdMarcar1.clicked.connect(onMarcar(0));
    ui.cmdMarcar2.clicked.connect(onMarcar(1));
    ui.cmdCorrigir.clicked.connect(onCorrigir);
    var timer = new QTimer(raiz);
    timer.interval = 1000;
    timer.timeout.connect(vigiar);
    timer.start();
    vigiar();
    return raiz;
}

function createWindowWidget() {
}

function createSettingsWidget() {
    var raiz = carregarUi("settings.ui");
    uiSettings = pegar(raiz, ["txtCamX", "txtCamY"]);
    lerConfiguracoes();
    return raiz;
}
