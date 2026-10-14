// Usado pelos testes em Python: corrige um .nc com o nucleo.js e imprime o resultado.
//   node corrigir_cli.js arquivo.nc camX camY m1x m1y m2x m2y
var fs = require("fs");
var path = require("path");
var N = require(path.join(__dirname, "..", "fresa", "nucleo.js"));
var a = process.argv.slice(2);
var linhas = fs.readFileSync(a[0], "utf8").split("\n");
var cam = [parseFloat(a[1]), parseFloat(a[2])];
var cab = N.lerCabecalho(linhas);
var real = [N.vistoPelaCamera([parseFloat(a[3]), parseFloat(a[4])], cam),
            N.vistoPelaCamera([parseFloat(a[5]), parseFloat(a[6])], cam)];
var t = N.transformacao(cab.fiduciais, real);
process.stdout.write(JSON.stringify({
    cabecalho: cab, giro: t.giroGraus, centro: t.centro, diferenca: t.diferenca, ok: t.ok,
    texto: N.aplicar(linhas, t.f, N.tituloCorrecao(t)).join("\n")
}));
