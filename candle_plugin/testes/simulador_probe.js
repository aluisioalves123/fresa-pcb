// Simulador do Candle para a trava do probe (candle_plugin/fresaprobe).
//   node simulador_probe.js <roteiro.json>
// Passos: {"abrir": "arq.nc"} | {"probe": true} (encostou) | {"probe": false} (falhou)
//         {"remetente": 0} muda o estado do envio (0 enviando, 2 pausado, 4 parado)
//         {"responder": "sim"|"nao"} resposta da proxima pergunta | {"tick": 1} roda os timers
var fs = require("fs"), path = require("path"), vm = require("vm");
var PLUGIN = path.join(__dirname, "..", "fresaprobe");
var roteiro = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
var log = { tempoReal: [], perguntas: 0 };
var resposta = "sim", timers = [];
function sinal() {
    var fns = [];
    return { connect: function (f) { fns.push(f); },
             emitir: function () { var a = arguments; fns.forEach(function (f) { f.apply(null, a); }); } };
}
function linhas(p) { return fs.readFileSync(p, "utf8").split(/\r?\n/).map(function (l) { return l.trim(); }).filter(Boolean); }
var app = {
    window: {},
    program: { lines: [], fileName: "" },
    device: { responseReceived: sinal(), sendRuntimeCommand: function (c) { log.tempoReal.push(c === String.fromCharCode(24) ? "RESET" : c); } },
    sender: { stateChanged: sinal() }
};
var ctx = {
    script: { path: PLUGIN, name: "FresaProbe", importExtension: function () {} }, app: app,
    QTimer: function () { var t = this; t.timeout = sinal(); t.start = function () { timers.push(t); }; },
    QMessageBox: { Yes: 16384, No: 65536,
        question: function () { log.perguntas++; return resposta === "sim" ? 16384 : 65536; } }
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(PLUGIN, "script.js"), "utf8"), ctx);
ctx.init();
roteiro.forEach(function (p) {
    if (p.abrir !== undefined) app.program = { lines: linhas(p.abrir), fileName: p.abrir };
    if (p.tick) timers.forEach(function (t) { t.timeout.emitir(); });
    if (p.responder) resposta = p.responder;
    if (p.probe !== undefined)
        app.device.responseReceived.emitir("G38.2Z-30F100", -1, "[PRB:1.000,2.000,-3.210:" + (p.probe ? 1 : 0) + "]\nok");
    if (p.remetente !== undefined) app.sender.stateChanged.emitir(p.remetente);
});
process.stdout.write(JSON.stringify(log));
