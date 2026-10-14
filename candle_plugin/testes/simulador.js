// Simulador do Candle para testar o script.js do plugin sem abrir o Candle nem mexer na CNC.
// Imita so o que o plugin usa: app.device, app.program, app.sender, app.storage, app.loadFile,
// os sinais de configuracao, QFile/QTextStream/QUiLoader/QTimer/QMessageBox. Roda um roteiro
// e imprime JSON.
//
//   node simulador.js <arquivo.nc> <roteiro.json>
//
// Passos do roteiro:
//   {"pos": [20.902, -11.2]}  posiciona a maquina (como se fosse o jog)
//   {"clicar": "cmdMarcar1"}  clica um botao do painel
//   {"estado": 2}             estado do GRBL (1 = Idle, 2 = Alarm); {"remetente": 0} = enviando
//   {"config": [35.1, -6.05]} digita o deslocamento da camera nas Configuracoes e salva
//   {"abrir": "outro.nc"}     abre outro arquivo no Candle; {"tick": 1} roda os timers
//   {"foto": "nome"}          guarda o texto e o estado de todos os widgets
var fs = require("fs");
var path = require("path");
var vm = require("vm");

var PLUGIN = path.join(__dirname, "..", "fresa");
var arquivo = process.argv[2];
var roteiro = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));

var log = { avisos: [], carregados: [], gravados: [] };
var armazenamento = {};
var timers = [];

function sinal() {
    var fns = [];
    return { connect: function (f) { fns.push(f); }, emitir: function () { for (var i = 0; i < fns.length; i++) fns[i](); } };
}
function widget() { return { text: "", enabled: true, clicked: sinal() }; }

function linhasDoArquivo(p) {
    return fs.readFileSync(p, "utf8").split(/\r?\n/).map(function (l) { return l.trim(); })
        .filter(function (l) { return l.length; });
}

var app = {
    path: "C:/Program Files/Candle",
    window: {},
    device: { state: 1, work: { x: 0, y: 0 }, sendCommands: function (c) { log.avisos.push("MOVEU A MAQUINA: " + c); } },
    sender: { state: 4 },
    program: { lines: linhasDoArquivo(arquivo), fileName: arquivo },
    storage: { group: function (g) {
        return {
            value: function (k, d) { return (g + "/" + k) in armazenamento ? armazenamento[g + "/" + k] : d; },
            setValue: function (k, v) { armazenamento[g + "/" + k] = v; }
        };
    } },
    settingsLoaded: sinal(), settingsSaved: sinal(), settingsRejected: sinal(), settingsSetByDefault: sinal(),
    settingsAccepted: sinal(),
    loadFile: function (x) {
        if (typeof x === "string") {
            log.carregados.push(x);
            app.program = { lines: linhasDoArquivo(x), fileName: x };
        } else {
            log.carregados.push("(lista)");
            app.program = { lines: x, fileName: "" };
        }
    }
};

function QFile(p) { this.p = p; }
QFile.prototype.open = function (modo) { return modo === 2 || fs.existsSync(this.p); };
QFile.prototype.close = function () {};
function QTextStream(f) { this.f = f; }
QTextStream.prototype.setCodec = function () {};
QTextStream.prototype.readAll = function () { return fs.readFileSync(this.f.p, "utf8"); };
QTextStream.prototype.writeString = function (t) { fs.writeFileSync(this.f.p, t); log.gravados.push(this.f.p); };

// Monta a arvore de um .ui como o QtScript mostra: cada widget so expoe pelo nome os filhos
// DIRETOS (layouts nao contam como pai). Um acesso a neto quebra aqui como quebraria no Candle.
var todos = {};
function montarArvore(xml) {
    var pilha = [{}], raiz = null;
    var tags = xml.match(/<\/?widget\s[^>]*>|<\/widget>/g) || [];
    tags.forEach(function (t) {
        if (t.indexOf("</") === 0) { pilha.pop(); return; }
        var nome = (/name="([^"]+)"/.exec(t) || [])[1];
        var w = widget();
        if (/class="CameraWidget"/.test(t)) {   // imita o CameraWidget do Candle
            w.availableCameras = JSON.parse(process.env.CAMERAS || '["USB2.0 PC CAMERA"]');
            var suportadas = JSON.parse(process.env.RESOLUCOES || '["640x480", "320x240"]');
            var res = [1280, 720], nomeCam = "", aberta = null;
            // availableResolutions so existe com a camera escolhida; a resolucao so vale
            // no momento em que a camera e escolhida (initCamera)
            Object.defineProperty(w, "availableResolutions", { get: function () { return nomeCam ? suportadas : []; } });
            Object.defineProperty(w, "resolution", { get: function () { return res; },
                                                     set: function (v) { res = v; } });
            Object.defineProperty(w, "cameraName", { get: function () { return nomeCam; },
                set: function (v) { nomeCam = v; aberta = v ? res.join("x") : null; } });
            Object.defineProperty(w, "abertaCom", { get: function () { return aberta; } });
        }
        if (nome) pilha[pilha.length - 1][nome] = w;
        todos[nome] = w;                    // indice plano so para o simulador mexer
        if (!raiz) raiz = w;
        if (!/\/>$/.test(t)) pilha.push(w);
    });
    return raiz;
}

var ctx = {
    script: { path: PLUGIN, name: "FresaPCB", importExtension: function () {} },
    app: app,
    QFile: QFile, QTextStream: QTextStream,
    QIODevice: { ReadOnly: 1, WriteOnly: 2 },
    QDir: function () {},
    QFileInfo: function (n) { this.fileName = function () { return path.basename(n); }; },
    QUiLoader: function () {
        this.setWorkingDirectory = function () {};
        this.addPluginPath = function () {};
        this.load = function (f) { return montarArvore(fs.readFileSync(f.p, "utf8")); };
    },
    QTimer: function () { var t = this; t.timeout = sinal(); t.start = function () { timers.push(t); }; },
    QMessageBox: { warning: function (w, t, texto) { log.avisos.push(texto); } },
    console: console
};
ctx.eval = function (codigo) { return vm.runInContext(codigo, ctx); };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(PLUGIN, "script.js"), "utf8"), ctx, { filename: "script.js" });
// configuracao do plugin Camera oficial, como ela fica guardada no Candle
var camConfig = JSON.parse(process.env.CAMERA_CONFIG || "null") || {
    name: "USB2.0 PC CAMERA", resolution: "640x480", zoom: "1.5", position: "10, 20",
    aimPosition: "0.5, 0.48", aimSize: "30", aimLineWidth: "2", aimColor: "-65536",
    mirrorHorizontal: "false", mirrorVertical: "true"
};
Object.keys(camConfig).forEach(function (k) { armazenamento["CameraPlugin/" + k] = camConfig[k]; });

ctx.init();
if (ctx.createPanelWidget()) throw "o plugin nao deve mais criar painel";
var janela = ctx.createWindowWidget();
if (!janela) throw "createWindowWidget nao devolveu a janela";
ctx.createSettingsWidget();
app.settingsLoaded.emitir();

var fotos = [];
roteiro.forEach(function (p) {
    if (p.pos) app.device.work = { x: p.pos[0], y: p.pos[1] };
    if (p.estado !== undefined) app.device.state = p.estado;
    if (p.remetente !== undefined) app.sender.state = p.remetente;
    if (p.config) {
        todos.txtCamX.text = String(p.config[0]);
        todos.txtCamY.text = String(p.config[1]);
        app.settingsSaved.emitir();
    }
    if (p.abrir) app.program = { lines: linhasDoArquivo(p.abrir), fileName: p.abrir };
    if (p.tick) timers.forEach(function (t) { t.timeout.emitir(); });
    if (p.clicar) todos[p.clicar].clicked.emitir();
    if (p.foto) {
        var f = { nome: p.foto };
        Object.keys(todos).forEach(function (k) { if (k) f[k] = { text: todos[k].text, enabled: todos[k].enabled }; });
        fotos.push(f);
    }
});

var cam = todos.camMain;
var camera = { abertaCom: cam.abertaCom, cameraName: cam.cameraName, resolution: cam.resolution, zoom: cam.zoom, pos: cam.pos,
    aimPos: cam.aimPos, aimSize: cam.aimSize, aimLineWidth: cam.aimLineWidth, aimColor: cam.aimColor,
    mirrorHorizontal: cam.mirrorHorizontal, mirrorVertical: cam.mirrorVertical };
Object.keys(armazenamento).forEach(function (k) { if (k.indexOf("CameraPlugin/") === 0) delete armazenamento[k]; });
process.stdout.write(JSON.stringify({ log: log, fotos: fotos, armazenamento: armazenamento,
    programa: app.program.fileName, camera: camera }));
