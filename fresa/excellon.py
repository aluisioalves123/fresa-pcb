"""Leitor de furacao Excellon (formato decimal do KiCad)."""
import re
from dataclasses import dataclass


class ErroExcellon(Exception):
    pass


@dataclass
class Furo:
    x: float
    y: float
    diametro: float
    funcao: str        # 'via', 'componente' ou 'npth'


def ler(caminho, npth=False):
    """Le um .drl. Devolve (furos, avisos). Rasgos (slots) sao ignorados com aviso."""
    ferramentas, funcoes = {}, {}
    escala, cur, func_pendente = 1.0, None, None
    furos, avisos = [], []
    for linha in open(caminho, encoding='utf-8', errors='replace'):
        s = linha.strip()
        if not s:
            continue
        m = re.search(r'TA\.AperFunction,([^,]+),([^,]+),(\w+)', s)
        if m:
            func_pendente = m.group(3)
            continue
        if s.startswith(';'):
            continue
        if s.startswith('INCH'):
            escala = 25.4
            continue
        if s.startswith('METRIC'):
            escala = 1.0
            continue
        m = re.match(r'^T(\d+)C([\d.]+)', s)
        if m:
            t = int(m.group(1))
            ferramentas[t] = float(m.group(2)) * escala
            if npth:
                funcoes[t] = 'npth'
            elif func_pendente == 'ViaDrill':
                funcoes[t] = 'via'
            else:
                funcoes[t] = 'componente'
            func_pendente = None
            continue
        m = re.match(r'^T(\d+)$', s)
        if m:
            cur = int(m.group(1))
            if cur == 0:
                cur = None
            continue
        if 'G85' in s or s.startswith(('G00', 'M15', 'M16', 'G01')):
            avisos.append(f'rasgo (furo oblongo) ignorado: {s}')
            continue
        m = re.match(r'^X(-?[\d.]+)Y(-?[\d.]+)$', s)
        if m:
            if '.' not in m.group(1) + m.group(2):
                raise ErroExcellon('furacao sem ponto decimal: exporte em formato decimal')
            if cur is None:
                raise ErroExcellon('coordenada de furo sem ferramenta selecionada')
            furos.append(Furo(float(m.group(1)) * escala, float(m.group(2)) * escala,
                              ferramentas[cur], funcoes[cur]))
    return furos, avisos
