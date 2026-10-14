// Simulador do Candle para testar o script.js do plugin sem abrir o Candle nem mexer na CNC.
// Imita so o que o plugin usa: app.device, app.program, app.sender, app.storage, app.loadFile,
// QFile/QTextStream/QUiLoader/QTimer/QMessageBox. Roda um roteiro e imprime JSON.
//
//   node simulador.js <arquivo.nc> <roteiro.json>
//
// Roteiro: lista de passos, por exemplo
//   {"pos": [20.902, -11.2]}  posiciona a maquina (como se fosse o jog)
//   {"clicar": "cmdIr1"}      clica um botao do painel
//   {"estado": 2}             muda o estado do GRBL (1 = Idle, 2 = Alarm)
//   {"responder": "nao"}      a proxima pergunta sim/nao sera respondida com nao
var fs = require("fs");
var path = require("path");
var vm = require("vm");

var PLUGIN = path.join(__dirname, "..", "fresa");
var arquivo = process.argv[2];
var roteiro = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));

var log = { comandos: [], avisos: [], perguntas: [], carregados: [], gravados: {} };
var armazenamento = {};
var resposta = "sim";

function sinal() {
    var fns = [];
    return { connect: function (f) { fns.push(f); }, emitir: function () { for (var i = 0; i < fns.length; i++) fns[i](); } };
}
function widget() { return { text: "", enabled: true, clicked: sinal(), editingFinished: sinal() }; }

function linhasDoArquivo(p) {
    return fs.readFileSync(p, "utf8").split(/\r?\n/).map(function (l) { return l.trim(); })
        .filter(function (l) { return l.length; });
}

var app = {
    path: "C:/Program Files/Candle",
    window: {},
    device: {
        state: 1, work: { x: 0, y: 0 },
        sendCommands: function (c) { log.comandos.push(c); }
    },
    sender: { state: 4 },
    program: { lines: linhasDoArquivo(arquivo), fileName: arquivo },
    storage: { group: function (g) {
        return {
            value: function (k, d) { return (g + "/" + k) in armazenamento ? armazenamento[g + "/" + k] : d; },
            setValue: function (k, v) { armazenamento[g + "/" + k] = v; }
        };
    } },
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
QFile.prototype.open = function (modo) { this.modo = modo; return modo === 2 || fs.existsSync(this.p); };
QFile.prototype.close = function () {};
function QTextStream(f) { this.f = f; }
QTextStream.prototype.setCodec = function () {};
QTextStream.prototype.readAll = function () { return fs.readFileSync(this.f.p, "utf8"); };
QTextStream.prototype.writeString = function (t) { fs.writeFileSync(this.f.p, t); log.gravados[this.f.p] = true; };

// Le o widget.ui de verdade e monta a arvore como o QtScript mostra: cada widget so expoe
// pelo nome os filhos DIRETOS (layouts nao contam como pai). Assim um nome errado ou um
// acesso a neto quebra aqui como quebraria no Candle.
var ui = {};
function montarArvore(xml) {
    var pilha = [{}], raiz = null;
    var tags = xml.match(/<\/?widget\s[^>]*>|<\/widget>/g) || [];
    tags.forEach(function (t) {
        if (t.indexOf("</") === 0) { pilha.pop(); return; }
        var nome = (/name="([^"]+)"/.exec(t) || [])[1];
        var w = widget();
        if (nome) pilha[pilha.length - 1][nome] = w;
        ui[nome] = w;                       // indice plano so para o simulador mexer
        if (!raiz) raiz = w;
        if (!/\/>$/.test(t)) pilha.push(w);
    });
    return raiz;
}
var arvore = montarArvore(fs.readFileSync(path.join(PLUGIN, "widget.ui"), "utf8"));

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
        this.load = function () { return arvore; };
    },
    QTimer: function () { this.timeout = sinal(); this.start = function () {}; },
    QMessageBox: {
        Yes: 16384, No: 65536,
        question: function (w, t, texto) { log.perguntas.push(texto); return resposta === "sim" ? 16384 : 65536; },
        warning: function (w, t, texto) { log.avisos.push(texto); }
    },
    console: console
};
ctx.eval = function (codigo) { return vm.runInContext(codigo, ctx); };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(PLUGIN, "script.js"), "utf8"), ctx, { filename: "script.js" });
ctx.init();
ctx.createPanelWidget();

var fotos = [];
roteiro.forEach(function (p) {
    if (p.pos) { app.device.work = { x: p.pos[0], y: p.pos[1] }; }
    if (p.estado !== undefined) { app.device.state = p.estado; }
    if (p.remetente !== undefined) { app.sender.state = p.remetente; }
    if (p.responder) { resposta = p.responder; }
    if (p.texto) { ui[p.texto[0]].text = p.texto[1]; ui[p.texto[0]].editingFinished.emitir(); }
    if (p.clicar) { ui[p.clicar].clicked.emitir(); }
    if (p.foto) {
        var f = { nome: p.foto };
        Object.keys(ui).forEach(function (k) { f[k] = { text: ui[k].text, enabled: ui[k].enabled }; });
        fotos.push(f);
    }
});

process.stdout.write(JSON.stringify({ log: log, fotos: fotos, armazenamento: armazenamento,
    programa: app.program.fileName }));
