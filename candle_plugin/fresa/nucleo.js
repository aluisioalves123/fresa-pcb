// Fresa PCB: matematica do plugin do Candle, sem nada de interface.
// Porte de fresa/corrigir.py. JavaScript ES5 puro: roda no QtScript do Candle e no Node (testes).

var FresaNucleo = (function () {
    var TOL_DISTANCIA = 0.1;
    var RX_COORD = /^(G[01]) X(-?\d+\.\d{3}) Y(-?\d+\.\d{3})(.*)$/;

    function f3(v) {
        var s = v.toFixed(3);
        return s === "-0.000" ? "0.000" : s;
    }

    // Le o cabecalho "( FRESA ... )" das primeiras linhas do programa.
    function lerCabecalho(linhas) {
        var cab = null, fid = null;
        for (var i = 0; i < Math.min(linhas.length, 10); i++) {
            var l = String(linhas[i]);
            var m = /^\( FRESA fase=(\d)(.*)\)$/.exec(l);
            if (m) {
                cab = { fase: parseInt(m[1], 10) };
                var pares = m[2].replace(/^\s+|\s+$/g, "").split(/\s+/);
                for (var k = 0; k < pares.length; k++) {
                    var kv = pares[k].split("=");
                    if (kv.length === 2) cab[kv[0]] = kv[1];
                }
            }
            m = /^\( FRESA fiduciais=(-?[\d.]+),(-?[\d.]+);(-?[\d.]+),(-?[\d.]+) \)$/.exec(l);
            if (m) fid = [[parseFloat(m[1]), parseFloat(m[2])], [parseFloat(m[3]), parseFloat(m[4])]];
        }
        if (!cab) return null;
        cab.fiduciais = fid;
        return cab;
    }

    // Ponto que a camera ve com a maquina em (X, Y). cam = posicao com a cruz 0,0 na mira.
    function vistoPelaCamera(maquina, cam) {
        return [maquina[0] - cam[0], maquina[1] - cam[1]];
    }

    // Onde mandar a maquina para a camera olhar o ponto p.
    function posicaoParaVer(p, cam) {
        return [p[0] + cam[0], p[1] + cam[1]];
    }

    // Giro + deslocamento (sem escala) que leva os 2 pontos de desenho aos 2 reais.
    // Usa o ponto medio para dividir o erro entre os dois (igual a corrigir.py).
    function transformacao(desenho, real) {
        var a = desenho[0], b = desenho[1], A = real[0], B = real[1];
        var th = Math.atan2(B[1] - A[1], B[0] - A[0]) - Math.atan2(b[1] - a[1], b[0] - a[0]);
        var c = Math.cos(th), s = Math.sin(th);
        var cd = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
        var cr = [(A[0] + B[0]) / 2, (A[1] + B[1]) / 2];
        var f = function (x, y) {
            var x0 = x - cd[0], y0 = y - cd[1];
            return [cr[0] + c * x0 - s * y0, cr[1] + s * x0 + c * y0];
        };
        var dd = Math.sqrt(Math.pow(b[0] - a[0], 2) + Math.pow(b[1] - a[1], 2));
        var dm = Math.sqrt(Math.pow(B[0] - A[0], 2) + Math.pow(B[1] - A[1], 2));
        return {
            f: f,
            giroGraus: th * 180 / Math.PI,
            distDesenho: dd,
            distMedida: dm,
            diferenca: Math.abs(dm - dd),
            ok: Math.abs(dm - dd) <= TOL_DISTANCIA,
            desloc: [cr[0] - cd[0], cr[1] - cd[1]],
            centro: f(0, 0)
        };
    }

    // Aplica f em toda coordenada de placa (3 casas), tira a trava M0 do arquivo 3
    // e marca corrigir=feito. Devolve a lista de linhas nova.
    function aplicar(linhas, f, titulo) {
        var out = [], trava = false;
        for (var i = 0; i < linhas.length; i++) {
            var l = String(linhas[i]);
            if (l.indexOf("( ATENCAO: arquivo SEM correcao") === 0) { trava = true; continue; }
            if (trava && l === "M0") { trava = false; continue; }
            if (l.indexOf("( FRESA fase=") === 0) l = l.replace("corrigir=sim", "corrigir=feito");
            var m = RX_COORD.exec(l);
            if (m) {
                var p = f(parseFloat(m[2]), parseFloat(m[3]));
                l = m[1] + " X" + f3(p[0]) + " Y" + f3(p[1]) + m[4];
            }
            out.push(l);
        }
        out.splice(2, 0, "( " + titulo + " )");
        return out;
    }

    function tituloCorrecao(t) {
        return "CORRIGIDO pelos fiduciais: giro " + t.giroGraus.toFixed(2) + " graus, centro da placa em X"
            + t.centro[0].toFixed(2) + " Y" + t.centro[1].toFixed(2);
    }

    return {
        TOL_DISTANCIA: TOL_DISTANCIA,
        f3: f3,
        lerCabecalho: lerCabecalho,
        vistoPelaCamera: vistoPelaCamera,
        posicaoParaVer: posicaoParaVer,
        transformacao: transformacao,
        aplicar: aplicar,
        tituloCorrecao: tituloCorrecao
    };
})();

if (typeof module !== "undefined") module.exports = FresaNucleo;
