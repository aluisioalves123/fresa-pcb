# -*- coding: utf-8 -*-
"""Registra o plugin Fresa PCB no KiCad (ActionPlugin, mesmo jeito do Roteador CNC).

O botao aparece em Ferramentas -> Plugins externos e na barra de ferramentas.
A janela roda dentro do KiCad, mas o calculo (shapely, matplotlib) roda num
processo separado, com o ambiente .venv-kicad criado pelo instalador: assim
nenhuma biblioteca nossa briga com o numpy e o wx que o KiCad ja carregou.

A janela e importada dentro do Run, e nao no topo, de proposito: erro num modulo
nosso nao derruba os outros plugins, vira uma janela com o traceback.
"""
import os

import pcbnew


class FresaPCB(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Exportar para a fresa"
        self.category = "Fabricacao"
        self.description = ("Valida a placa e gera os 3 arquivos do Candle para a TTC3018: "
                            "cobre de cima, furos e cobre de baixo.")
        self.show_toolbar_button = True
        pasta = os.path.dirname(__file__)
        icone = os.path.join(pasta, "icone.png")
        if os.path.exists(icone):
            self.icon_file_name = icone
        escuro = os.path.join(pasta, "icone_escuro.png")
        if os.path.exists(escuro):
            self.dark_icon_file_name = escuro

    def Run(self):
        try:
            from .janela import abrir_no_kicad
        except Exception:
            import traceback
            _erro("Nao consegui carregar o plugin Fresa PCB", traceback.format_exc())
            return
        try:
            abrir_no_kicad(pcbnew.GetBoard())
        except Exception:
            import traceback
            _erro("O plugin Fresa PCB quebrou", traceback.format_exc())


def _erro(titulo, detalhe):
    try:
        import wx
        dlg = wx.MessageDialog(None, detalhe, titulo, wx.OK | wx.ICON_ERROR)
        dlg.ShowModal()
        dlg.Destroy()
    except Exception:
        print(titulo + "\n" + detalhe)


# Registrar fora do KiCad dispara um assert do wx; com a guarda o modulo pode ser
# importado em teste. So existe aplicacao wx rodando com o programa aberto.
def _dentro_do_kicad():
    try:
        import wx
        return wx.GetApp() is not None
    except Exception:
        return False


if _dentro_do_kicad():
    FresaPCB().register()
