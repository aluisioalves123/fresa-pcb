// Fresa PCB: plugin do Candle. Faz uma coisa so: com o desenho aberto, voce olha a camera,
// centraliza cada fiducial na mira, marca os dois e ele corrige o desenho (giro + deslocamento).
// Nao move a maquina. A camera e a mira sao as mesmas configuradas no plugin Camera oficial;
// o deslocamento camera -> broca fica nas Configuracoes do Candle, secao Fresa PCB.
// O Windows so deixa um programa usar a camera por vez: feche a janela Camera oficial.

script.importExtension("qt.core");
script.importExtension("qt.gui");
script.importExtension("qt.widgets");
script.importExtension("qt.uitools");

var pluginPath = script.path;
var pluginName = script.name;
var designerPluginsPath = app.path + "/designerplugins";   // de onde vem o CameraWidget
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
    if (avisoCamera) {
        ui.lblResultado.text = cor(AMARELO, avisoCamera);
    } else if (!pronto) {
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

// ---------- camera: mesma camera e mesma mira do plugin Camera oficial ----------

function par(texto, conv) {
    var l = String(texto).split(",");
    return [conv(l[0]), conv(l[1])];
}

var CAMERA_PADRAO = "USB2.0 PC CAMERA";   // endoscopio da especificacao
var RESOLUCAO_PADRAO = "640x480";
var avisoCamera = "";
var miraTravada = [0.5, 0.5];

// Shift + arrastar no CameraWidget move a mira. A calibracao (deslocamento camera -> broca)
// vale para a mira no lugar configurado: mira fora do lugar = correcao errada sem aviso.
// Arrastar sem Shift so desloca a imagem e a rodinha da zoom; a mira vai junto, sem problema.
function travarMira(v) {
    if (Math.abs(v[0] - miraTravada[0]) > 1e-6 || Math.abs(v[1] - miraTravada[1]) > 1e-6) {
        ui.camMain.aimPos = miraTravada;
    }
}

// Camera que vale: a escolhida no plugin Camera oficial; se nenhuma foi escolhida, a da
// especificacao ou a unica ligada.
function escolherCamera(disponiveis) {
    var l = [];
    for (var i = 0; i < disponiveis.length; i++) l.push(String(disponiveis[i]));
    for (var k = 0; k < l.length; k++) if (l[k].indexOf(CAMERA_PADRAO) >= 0) return l[k];
    return l.length == 1 ? l[0] : "";
}

function configurarCamera() {
    var g = app.storage.group("CameraPlugin");
    var c = ui.camMain;
    var nome = String(g.value("name", ""));
    var configurada = nome !== "";
    if (!configurada) nome = escolherCamera(c.availableCameras || []);
    c.zoom = parseFloat(g.value("zoom", 1));
    c.pos = par(g.value("position", "0, 0"), parseInt);
    // a mira e relativa a imagem: 0,0 e o canto, 0.5,0.5 e o centro. Nunca configurada, vai ao centro.
    var mira = par(g.value("aimPosition", "0, 0"), parseFloat);
    if (!mira[0] && !mira[1]) mira = [0.5, 0.5];
    miraTravada = mira;
    c.aimPos = mira;
    c.aimSize = parseInt(g.value("aimSize", 20));
    c.aimLineWidth = parseInt(g.value("aimLineWidth", 1));
    c.aimColor = parseInt(g.value("aimColor", -65536));
    c.mirrorHorizontal = String(g.value("mirrorHorizontal", false)) === "true";
    c.mirrorVertical = String(g.value("mirrorVertical", false)) === "true";
    // O CameraWidget so aplica a resolucao quando a camera e escolhida (e nasce pedindo
    // 1280x720, que o endoscopio nao tem). Entao: escolhe a camera, ve as resolucoes que ELA
    // informa, fixa uma suportada e escolhe a camera de novo para ligar com ela.
    c.cameraName = nome;
    if (nome) {
        var suportadas = [];
        var rs = c.availableResolutions || [];
        for (var i = 0; i < rs.length; i++) suportadas.push(String(rs[i]));
        var quero = configurada ? String(g.value("resolution", RESOLUCAO_PADRAO)) : RESOLUCAO_PADRAO;
        var usar = suportadas.indexOf(quero) >= 0 ? quero
                 : suportadas.indexOf(RESOLUCAO_PADRAO) >= 0 ? RESOLUCAO_PADRAO
                 : suportadas.length ? suportadas[0] : quero;
        c.resolution = par(usar.replace("x", ","), parseInt);
        c.cameraName = nome;
    }
    if (!nome) {
        var l = c.availableCameras || [];
        avisoCamera = l.length ? "Mais de uma câmera ligada: escolha qual nas Configurações do Candle, seção Camera ("
                                 + l.join(", ") + ")."
                               : "Nenhuma câmera encontrada. O endoscópio tem que estar ligado direto no PC, não no hub.";
    } else {
        avisoCamera = "";
    }
    atualizar();
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
    loader.addPluginPath(designerPluginsPath);
    app.settingsLoaded.connect(lerConfiguracoes);
    app.settingsLoaded.connect(function () { if (ui) configurarCamera(); });
    app.settingsAccepted.connect(function () { if (ui) configurarCamera(); });
    app.settingsSaved.connect(gravarConfiguracoes);
    app.settingsRejected.connect(lerConfiguracoes);
    app.settingsSetByDefault.connect(function () {
        uiSettings.txtCamX.text = n3(CAM_PADRAO[0]);
        uiSettings.txtCamY.text = n3(CAM_PADRAO[1]);
    });
}

function createPanelWidget() {
}

// janela propria (como a Camera oficial): a camera em cima, os botoes embaixo
function createWindowWidget() {
    var raiz = carregarUi("widget.ui");
    ui = pegar(raiz, ["camMain", "lblArquivo", "cmdMarcar1", "cmdMarcar2", "lblResultado", "cmdCorrigir"]);
    ui.camMain.aimPosChanged.connect(travarMira);
    ui.cmdMarcar1.clicked.connect(onMarcar(0));
    ui.cmdMarcar2.clicked.connect(onMarcar(1));
    ui.cmdCorrigir.clicked.connect(onCorrigir);
    var timer = new QTimer(raiz);
    timer.interval = 1000;
    timer.timeout.connect(vigiar);
    timer.start();
    vigiar();
    configurarCamera();
    return raiz;
}

function createSettingsWidget() {
    var raiz = carregarUi("settings.ui");
    uiSettings = pegar(raiz, ["txtCamX", "txtCamY"]);
    lerConfiguracoes();
    return raiz;
}
