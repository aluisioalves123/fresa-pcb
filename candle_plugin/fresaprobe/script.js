// Fresa PCB: trava do probe. Plugin sem janela.
// Ao mandar rodar um arquivo FRESA, confere se houve um probe do Z que encostou de verdade
// ([PRB:...:1]) DEPOIS que esse arquivo foi aberto. Se nao houve, segura a maquina (feed hold)
// na hora, enquanto ela ainda esta subindo ao topo, e pergunta. "Nao" para o programa sem
// perder a posicao; "Sim" continua.

script.importExtension("qt.core");
script.importExtension("qt.gui");
script.importExtension("qt.widgets");

var ENVIANDO = 0, PAUSANDO = 1, PAUSADO = 2, TROCA_FERRAMENTA = 5;
var FEED_HOLD = "!", CONTINUAR = "~", RESET = String.fromCharCode(24);

var arquivoAtual = null;     // arquivo aberto quando conferimos pela ultima vez
var probeDepois = false;     // houve probe bem-sucedido desde que esse arquivo foi aberto
var estadoAnterior = -1;
var perguntando = false;

function arquivoFresa() {
    var l = app.program.lines;
    for (var i = 0; i < Math.min(l.length, 10); i++) {
        if (String(l[i]).indexOf("( FRESA fase=") === 0) return true;
    }
    return false;
}

function conferirArquivo() {
    var nome = app.program.fileName;
    if (nome !== arquivoAtual) {
        arquivoAtual = nome;
        probeDepois = false;
    }
}

function onResposta(comando, indice, resposta) {
    if (/G38\.[2-5]/i.test(String(comando)) && /PRB:[^\]]*:1/.test(String(resposta))) {
        conferirArquivo();   // probe feito com este arquivo aberto
        probeDepois = true;
    }
}

function perguntar() {
    var texto = "Você não fez o probe do Z desde que abriu este arquivo.\n\n"
        + "A máquina está segura, parada enquanto subia ao topo.\n\n"
        + "Já fez o probe no centro da placa?\n\n"
        + "Não: para o programa. Faça o probe e rode de novo.\n"
        + "Sim: continua.";
    try {
        return QMessageBox.question(app.window, "Probe do Z", texto) == QMessageBox.Yes;
    } catch (e) {
        return false;        // sem como perguntar: na duvida, para
    }
}

function onRemetente(estado) {
    var anterior = estadoAnterior;
    estadoAnterior = estado;
    // so no comeco de um envio, nao ao voltar de uma pausa ou de uma troca de ferramenta
    if (estado != ENVIANDO || anterior == PAUSANDO || anterior == PAUSADO || anterior == TROCA_FERRAMENTA) return;
    if (perguntando || !arquivoFresa()) return;
    conferirArquivo();
    if (probeDepois) return;

    app.device.sendRuntimeCommand(FEED_HOLD);
    perguntando = true;
    var continuar = perguntar();
    perguntando = false;
    if (continuar) {
        probeDepois = true;  // nao pergunta de novo para este arquivo
        app.device.sendRuntimeCommand(CONTINUAR);
    } else {
        app.device.sendRuntimeCommand(RESET);   // reset durante o hold nao perde a posicao
    }
}

function init() {
    app.device.responseReceived.connect(onResposta);
    app.sender.stateChanged.connect(onRemetente);
    var t = new QTimer();
    t.interval = 1000;
    t.timeout.connect(conferirArquivo);
    t.start();
}

function createPanelWidget() {
}

function createWindowWidget() {
}

function createSettingsWidget() {
}
