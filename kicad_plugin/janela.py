# -*- coding: utf-8 -*-
"""Janela do plugin: grava uma copia da placa, chama o nucleo e mostra o resultado.

O nucleo roda em outro processo:  <python do .venv-kicad> -m fresa kicad <copia> --json
O caminho desse python e da pasta do projeto ficam em config.json (escrito pelo instalador).

Teste sem o KiCad (precisa de wx):  python janela.py "placa.kicad_pcb"
"""
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading

import wx
import wx.html

FUNDO, PAINEL, TEXTO, CINZA = '#16181d', '#1f2228', '#e6e6e6', '#9aa0a6'
VERMELHO, AMARELO, VERDE, AZUL = '#ff5a5a', '#ffd84a', '#7dff6a', '#5ad1ff'
AQUI = os.path.dirname(os.path.abspath(__file__))


def _config():
    c = os.path.join(AQUI, 'config.json')
    if not os.path.exists(c):
        raise RuntimeError('config.json nao encontrado: rode instalar_plugin_kicad.py de novo')
    cfg = json.load(open(c, encoding='utf-8'))
    if not os.path.isfile(cfg['python']):
        raise RuntimeError(f"ambiente do nucleo nao encontrado em {cfg['python']}: "
                           f"rode instalar_plugin_kicad.py de novo")
    return cfg


def _kicad_cli():
    """kicad-cli ao lado do executavel do KiCad que esta rodando o plugin."""
    for base in (os.path.dirname(sys.executable), os.path.dirname(os.path.dirname(sys.executable))):
        for nome in ('kicad-cli.exe', 'kicad-cli'):
            c = os.path.join(base, nome)
            if os.path.isfile(c):
                return c
    return None


def _arquivo_pastas():
    base = os.environ.get('APPDATA') or os.path.expanduser('~/.config')
    return os.path.join(base, 'fresa-pcb', 'pastas.json')


def pasta_lembrada(placa, padrao):
    """Pasta de saida escolhida antes para esta placa, ou a padrao."""
    try:
        p = json.load(open(_arquivo_pastas(), encoding='utf-8')).get(os.path.normcase(placa))
        return p if p and os.path.isdir(p) else padrao   # pasta apagada: volta para a padrao
    except Exception:
        return padrao


def lembrar_pasta(placa, pasta):
    arq = _arquivo_pastas()
    try:
        d = json.load(open(arq, encoding='utf-8'))
    except Exception:
        d = {}
    d[os.path.normcase(placa)] = pasta
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    with open(arq, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def _abrir_pasta(p):
    if sys.platform == 'win32':
        os.startfile(p)
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', p])
    else:
        subprocess.Popen(['xdg-open', p])


class Janela(wx.Dialog):
    def __init__(self, parent, pcb, nome, saida, limpar=None, chave=None):
        super().__init__(parent, title='Fresa PCB', size=(860, 820),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.pcb, self.saida, self.limpar = pcb, saida, limpar
        self.chave = chave or pcb       # placa original, para lembrar a pasta escolhida
        self.ocupado = False
        self.cfg = _config()
        self.SetBackgroundColour(FUNDO)
        s = wx.BoxSizer(wx.VERTICAL)

        titulo = wx.StaticText(self, label=nome)
        titulo.SetForegroundColour(TEXTO)
        titulo.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.estado = wx.StaticText(self, label='Exportando pelo kicad-cli e validando...')
        self.estado.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.estado.SetForegroundColour(AZUL)
        s.Add(titulo, 0, wx.ALL, 12)
        s.Add(self.estado, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        linha = wx.BoxSizer(wx.HORIZONTAL)
        rot = wx.StaticText(self, label='Salvar em:')
        rot.SetForegroundColour(CINZA)
        self.t_pasta = wx.StaticText(self, label=saida, style=wx.ST_ELLIPSIZE_MIDDLE)
        self.t_pasta.SetForegroundColour(TEXTO)
        self.b_trocar = wx.Button(self, label='Trocar pasta...')
        self.b_trocar.Bind(wx.EVT_BUTTON, self._trocar_pasta)
        linha.Add(rot, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        linha.Add(self.t_pasta, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        linha.Add(self.b_trocar, 0)
        s.Add(linha, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.lista = wx.html.HtmlWindow(self, style=wx.html.HW_SCROLLBAR_AUTO)
        self.lista.SetMinSize((-1, 220))
        self.lista.SetBackgroundColour(PAINEL)
        s.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        self.previas = wx.BoxSizer(wx.HORIZONTAL)
        s.Add(self.previas, 0, wx.ALIGN_CENTER | wx.TOP, 8)

        self.botoes = wx.BoxSizer(wx.HORIZONTAL)
        self.b_gerar = self._botao('Gerar arquivos', lambda e: self._gerar())
        self.b_pasta = self._botao('Abrir pasta', lambda e: _abrir_pasta(self.saida))
        self._botao('Fechar', lambda e: self.EndModal(wx.ID_CLOSE))
        self.b_gerar.Hide()
        self.b_pasta.Hide()
        s.Add(self.botoes, 0, wx.ALIGN_RIGHT | wx.ALL, 12)
        self.SetSizer(s)
        self.Bind(wx.EVT_CLOSE, lambda e: self.EndModal(wx.ID_CLOSE))
        self.Centre()
        self._html([])
        self.rascunho = tempfile.mkdtemp(prefix='fresa-pcb-val-')
        self.validado = None          # relatorio da validacao, se nao teve erro
        self._validar()

    def _botao(self, rotulo, acao):
        b = wx.Button(self, label=rotulo)
        b.Bind(wx.EVT_BUTTON, acao)
        self.botoes.Add(b, 0, wx.LEFT, 8)
        return b

    def _html(self, linhas):
        corpo = ''.join(f'<p><font color="{cor}">{html.escape(t)}</font></p>' for cor, t in linhas)
        self.lista.SetPage(f'<html><body bgcolor="{PAINEL}" text="{TEXTO}">'
                           f'<font face="Segoe UI" size="3">{corpo}</font></body></html>')

    def _estado(self, texto, cor):
        self.estado.SetLabel(texto)
        self.estado.SetForegroundColour(cor)
        self.Layout()

    def _trocar_pasta(self, evento):
        if self.ocupado:
            return
        dlg = wx.DirDialog(self, 'Onde salvar os arquivos da fresa', self.saida, wx.DD_DEFAULT_STYLE)
        if dlg.ShowModal() == wx.ID_OK and dlg.GetPath() != self.saida:
            self.usar_pasta(dlg.GetPath())
        dlg.Destroy()

    def usar_pasta(self, pasta):
        """Troca a pasta de saida e lembra para esta placa. Nada e gravado ate clicar em Gerar."""
        self.saida = pasta
        self.t_pasta.SetLabel(pasta)
        try:
            lembrar_pasta(self.chave, pasta)
        except Exception:
            pass
        if self.b_pasta.IsShown():        # ja tinha gerado na pasta antiga
            self.previas.Clear(delete_windows=True)
            self.b_pasta.Hide()
            self._mostrar_validacao(self.validado, 'Pasta trocada. Clique em Gerar arquivos para gravar nela.')

    def _linhas(self, d):
        L = [(VERMELHO, 'ERRO: ' + m) for m in d['erros']]
        L += [(AMARELO, 'AVISO: ' + m) for m in d['avisos']]
        return L + [(CINZA, m) for m in d['info']]

    # 1o passo: exporta numa pasta de rascunho e valida, sem gravar nada na pasta de saida
    def _validar(self):
        self._rodar([self.pcb, '--saida', self.saida, '--pasta-gerber', os.path.join(self.rascunho, 'gerber'),
                     '--so-validar', '--json'], self._validou)

    def _validou(self, codigo, d):
        if codigo == 1:
            self._estado(f"{len(d['erros'])} erro(s): nada foi exportado. Corrija no KiCad e rode de novo.",
                         VERMELHO)
            self._html(self._linhas(d))
            return
        self.validado = d
        self._mostrar_validacao(d)

    def _mostrar_validacao(self, d, texto=None):
        if d['avisos']:
            self._estado(texto or f"{len(d['avisos'])} aviso(s). Confira, escolha a pasta e gere.", AMARELO)
            self.b_gerar.SetLabel('Gerar mesmo assim')
        else:
            self._estado(texto or 'Tudo certo. Escolha a pasta e gere os arquivos.', VERDE)
            self.b_gerar.SetLabel('Gerar arquivos')
        self._html(self._linhas(d))
        self.b_gerar.Show()
        self.Layout()

    # 2o passo: gera de verdade na pasta escolhida
    def _gerar(self):
        self.b_gerar.Hide()
        self._estado('Gerando os arquivos...', AZUL)
        self._rodar([self.pcb, '--saida', self.saida, '--aceitar-avisos', '--json'], self._gerou)

    def _gerou(self, codigo, d):
        if codigo != 0:
            self._estado('A placa mudou de estado e não passou mais na validação.', VERMELHO)
            self._html(self._linhas(d))
            return
        self._estado('Pronto: 3 arquivos gerados para o Candle.', VERDE)
        gerados = [(VERDE, 'gerado: ' + os.path.basename(c)) for c in d['arquivos']]
        self._html(gerados + [(CINZA, 'na pasta ' + self.saida)] + self._linhas(d))
        for p in d.get('previas', []):
            img = wx.Image(p)
            lado = 280
            img = img.Scale(lado, int(img.GetHeight() * lado / img.GetWidth()), wx.IMAGE_QUALITY_HIGH)
            self.previas.Add(wx.StaticBitmap(self, bitmap=wx.Bitmap(img)), 0, wx.LEFT | wx.RIGHT, 6)
        self.b_pasta.Show()
        self.Layout()

    def _rodar(self, args, depois):
        self.ocupado = True
        self.b_trocar.Disable()
        cmd = [self.cfg['python'], '-m', 'fresa', 'kicad'] + args
        threading.Thread(target=self._trabalho, args=(cmd, depois), daemon=True).start()

    # fora da tela, para o KiCad nao congelar
    def _trabalho(self, cmd, depois):
        env = dict(os.environ)
        cli = _kicad_cli()
        if cli:
            env['FRESA_KICAD_CLI'] = cli
        env.pop('PYTHONHOME', None)
        env.pop('PYTHONPATH', None)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        try:
            r = subprocess.run(cmd, cwd=self.cfg['raiz'], capture_output=True, text=True, encoding='utf-8',
                               errors='replace', stdin=subprocess.DEVNULL, env=env, creationflags=flags)
            wx.CallAfter(self._resposta, r.returncode, r.stdout, r.stderr, depois)
        except Exception as e:
            wx.CallAfter(self._resposta, -1, '', str(e), depois)

    def _resposta(self, codigo, out, err, depois):
        self.ocupado = False
        self.b_trocar.Enable()
        try:
            d = json.loads(out)
        except ValueError:
            self._estado('Não foi possível exportar', VERMELHO)
            self._html([(VERMELHO, l) for l in (err or out or 'sem resposta do nucleo').strip().splitlines()[-12:]])
            return
        depois(codigo, d)

    def Destroy(self):
        for p in (self.limpar, self.rascunho):
            if p:
                shutil.rmtree(p, ignore_errors=True)
        return super().Destroy()


def abrir_no_kicad(board):
    """Grava a placa como esta na tela numa pasta temporaria (sem mexer no arquivo do
    usuario) e abre a janela. A pasta gcode fica ao lado do projeto."""
    import pcbnew
    original = board.GetFileName()
    if not original:
        wx.MessageBox('Salve a placa uma vez antes de exportar: preciso saber a pasta do projeto.',
                      'Fresa PCB', wx.OK | wx.ICON_WARNING)
        return
    tmp = tempfile.mkdtemp(prefix='fresa-pcb-')
    copia = os.path.join(tmp, os.path.basename(original))
    pcbnew.SaveBoard(copia, board)
    saida = pasta_lembrada(original, os.path.join(os.path.dirname(original), 'gcode'))
    pai = wx.FindWindowByName('PcbFrame')
    dlg = Janela(pai, copia, os.path.basename(original), saida, limpar=tmp, chave=original)
    dlg.ShowModal()
    dlg.Destroy()


if __name__ == '__main__':
    app = wx.App(False)
    pcb = os.path.abspath(sys.argv[1])
    dlg = Janela(None, pcb, os.path.basename(pcb), os.path.join(os.path.dirname(pcb), 'gcode'))
    dlg.ShowModal()
    dlg.Destroy()
