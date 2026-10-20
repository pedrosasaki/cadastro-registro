"""
validacoes.py
=============
Regras de validação dos campos do formulário.

Este arquivo NÃO conversa com o banco: ele só confere se os dados
fazem sentido e devolve uma versão "limpa" (pronta para gravar).

Por que validar aqui E no banco?
  - Aqui: mensagens claras em português, antes de qualquer envio.
  - No banco: última linha de defesa (tipo, tamanho, precisão).
  Se alguém burlar a tela, o banco ainda recusa.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# ------------------------------------------------------------------
# Constantes — mudar aqui muda a regra em todo o aplicativo
# ------------------------------------------------------------------
MAX_TEXTO = 50          # limite de "tipo" e "empresa" (igual ao VARCHAR(50))
MAX_DIGITOS_VALOR = 18  # total de algarismos do NUMERIC(18,2)
CASAS_DECIMAIS = 2      # casas após a vírgula
MAX_INTEIRO = 2_147_483_647  # limite do tipo INTEGER do PostgreSQL


# ------------------------------------------------------------------
# Utilidades internas
# ------------------------------------------------------------------
def _limpar(valor) -> str:
    """Transforma qualquer entrada em texto sem espaços nas pontas."""
    if valor is None:
        return ""
    return str(valor).replace("\u00a0", " ").strip()


def _erro_inteiro_grande(valor: int) -> str | None:
    """O PostgreSQL usa INTEGER de 32 bits: +/- 2.147.483.647."""
    if valor > MAX_INTEIRO or valor < -MAX_INTEIRO:
        return (
            "número grande demais para este campo "
            f"(limite: {MAX_INTEIRO:,} a -{MAX_INTEIRO:,})".replace(",", ".")
        )
    return None


# ------------------------------------------------------------------
# Conversores — devolvem sempre (valor, mensagem_de_erro)
# Quando o campo está vazio, devolvem (None, None): quem decide se
# o vazio é permitido é a função validar_formulario().
# ------------------------------------------------------------------
def parse_inteiro(texto) -> tuple[int | None, str | None]:
    """
    Converte texto em número inteiro.
    Aceita: "10", "-3", "+7", "1.234" (ponto como separador de milhar).
    Recusa: "10,5", "abc", "1.2" (ponto decimal).
    """
    t = _limpar(texto).replace(" ", "")
    if t == "":
        return None, None

    # "1.234" e "12.345.678" -> remove os pontos de milhar
    if re.fullmatch(r"[+-]?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")

    if not re.fullmatch(r"[+-]?\d+", t):
        return None, "informe apenas números inteiros (sem vírgula nem ponto decimal)"

    try:
        numero = int(t)
    except ValueError:
        return None, "número inteiro inválido"

    erro = _erro_inteiro_grande(numero)
    if erro:
        return None, erro
    return numero, None


def parse_valor(texto) -> tuple[Decimal | None, str | None]:
    """
    Converte texto em Decimal com 2 casas (nunca float, para não perder precisão).
    Aceita: "1.234,56", "1234,56", "1234.56", "1234", "R$ 1.234,56", "-50,00".
    Recusa: "1.234,567" (3 casas), "abc", "1,2,3".
    """
    t = _limpar(texto).replace(" ", "")
    t = t.replace("R$", "").replace("r$", "")
    if t == "":
        return None, None

    negativo = t.startswith("-")
    if negativo:
        t = t[1:]
    t = t.lstrip("+")

    if "," in t:
        # Padrão brasileiro: ponto = milhar, vírgula = decimal
        if t.count(",") > 1:
            return None, "use apenas uma vírgula decimal (ex.: 1.234,56)"
        t = t.replace(".", "").replace(",", ".")
    else:
        # Sem vírgula: "1.234" é milhar; "1234.56" é decimal
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
            t = t.replace(".", "")

    if not re.fullmatch(r"\d+(\.\d+)?", t):
        return None, "valor inválido (exemplos aceitos: 1.234,56 ou 1234.56)"

    try:
        numero = Decimal(t)
    except InvalidOperation:
        return None, "valor inválido"

    if negativo:
        numero = -numero

    # Casas decimais: "1234.567" tem 3 -> recusa
    expoente = -numero.as_tuple().exponent
    if expoente > CASAS_DECIMAIS:
        return None, f"use no máximo {CASAS_DECIMAIS} casas decimais"

    parte_inteira = str(abs(numero)).split(".")[0]
    limite = MAX_DIGITOS_VALOR - CASAS_DECIMAIS
    if len(parte_inteira) > limite:
        return None, f"valor grande demais (máximo {limite} algarismos antes da vírgula)"

    try:
        return numero.quantize(Decimal("0.01")), None
    except InvalidOperation:
        return None, "valor inválido"


def parse_data(texto) -> tuple[date | None, str | None]:
    """
    Converte texto em data.
    Aceita: "31/12/2026", "2026-12-31", "31-12-2026", "31/12/26".
    Também aceita um objeto date já pronto (vindo do seletor de data).
    """
    if isinstance(texto, datetime):
        return texto.date(), None
    if isinstance(texto, date):
        return texto, None

    t = _limpar(texto)
    if t == "":
        return None, None

    # Descarta a parte de hora, se vier do Excel ("31/12/2026 00:00:00")
    t = t.split(" ")[0]

    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(t, formato).date(), None
        except ValueError:
            continue

    return None, "data inválida — use o formato dia/mês/ano (ex.: 31/12/2026)"


# ------------------------------------------------------------------
# Validação principal
# ------------------------------------------------------------------
def validar_formulario(campos: dict) -> tuple[dict, list[str]]:
    """
    Recebe o dicionário com os 7 campos (como texto ou tipos nativos)
    e devolve (dados_prontos_para_o_banco, lista_de_erros).

    Regras aplicadas (as mesmas do script SQL):
      tipo          obrigatório, até 50 caracteres
      periodo       obrigatório, data válida
      posicao       OPCIONAL, inteiro (aceita negativos)
      empresa       obrigatório, até 50 caracteres
      quantidade    obrigatório, inteiro (aceita negativos)
      valor         obrigatório, decimal com 2 casas
      participacao  OPCIONAL, inteiro (aceita negativos)
    """
    erros: list[str] = []
    dados: dict = {}

    # ---------- tipo ----------
    tipo = _limpar(campos.get("tipo"))
    if tipo == "":
        erros.append("**Tipo** é obrigatório.")
    elif len(tipo) > MAX_TEXTO:
        erros.append(
            f"**Tipo** deve ter no máximo {MAX_TEXTO} caracteres "
            f"(você informou {len(tipo)})."
        )
    else:
        dados["tipo"] = tipo

    # ---------- periodo ----------
    periodo, erro = parse_data(campos.get("periodo"))
    if erro:
        erros.append(f"**Período**: {erro}")
    elif periodo is None:
        erros.append("**Período** é obrigatório.")
    else:
        dados["periodo"] = periodo.isoformat()

    # ---------- posicao (opcional) ----------
    posicao, erro = parse_inteiro(campos.get("posicao"))
    if erro:
        erros.append(f"**Posição**: {erro}")
    else:
        dados["posicao"] = posicao  # None é aceito pelo banco

    # ---------- empresa ----------
    empresa = _limpar(campos.get("empresa"))
    if empresa == "":
        erros.append("**Empresa** é obrigatória.")
    elif len(empresa) > MAX_TEXTO:
        erros.append(
            f"**Empresa** deve ter no máximo {MAX_TEXTO} caracteres "
            f"(você informou {len(empresa)})."
        )
    else:
        dados["empresa"] = empresa

    # ---------- quantidade (obrigatório) ----------
    quantidade, erro = parse_inteiro(campos.get("quantidade"))
    if erro:
        erros.append(f"**Quantidade**: {erro}")
    elif quantidade is None:
        erros.append("**Quantidade** é obrigatória.")
    else:
        dados["quantidade"] = quantidade

    # ---------- valor (obrigatório) ----------
    valor, erro = parse_valor(campos.get("valor"))
    if erro:
        erros.append(f"**Valor**: {erro}")
    elif valor is None:
        erros.append("**Valor** é obrigatório.")
    else:
        dados["valor"] = str(valor)  # texto com 2 casas: "1234.56"

    # ---------- participacao (opcional) ----------
    participacao, erro = parse_inteiro(campos.get("participacao"))
    if erro:
        erros.append(f"**Participação**: {erro}")
    else:
        dados["participacao"] = participacao

    return dados, erros


# ------------------------------------------------------------------
# Leitura de dados colados do Excel
# ------------------------------------------------------------------
def dividir_linha_excel(linha: str) -> list[str]:
    """
    Separa uma linha colada do Excel em células.
    O Excel copia as colunas separadas por TABULAÇÃO (\\t).
    Se não houver tabulação, tentamos ponto e vírgula (comum no Excel
    em português quando se salva como CSV).
    """
    if "\t" in linha:
        return [c.strip() for c in linha.split("\t")]
    if ";" in linha:
        return [c.strip() for c in linha.split(";")]
    return [linha.strip()]


def validar_linha_excel(celulas: list[str]) -> tuple[dict, list[str]]:
    """
    Valida uma linha colada do Excel.
    Ordem esperada das colunas (a mesma do formulário):
      1 Tipo | 2 Período | 3 Posição | 4 Empresa | 5 Quantidade | 6 Valor | 7 Participação
    """
    if len(celulas) < 7:
        return {}, [
            f"a linha tem {len(celulas)} coluna(s), mas são necessárias 7 "
            "(Tipo, Período, Posição, Empresa, Quantidade, Valor, Participação)."
        ]
    if len(celulas) > 7:
        return {}, [
            f"a linha tem {len(celulas)} colunas, mas o esperado são 7. "
            "Verifique se algum texto contém tabulação."
        ]

    return validar_formulario(
        {
            "tipo": celulas[0],
            "periodo": celulas[1],
            "posicao": celulas[2],
            "empresa": celulas[3],
            "quantidade": celulas[4],
            "valor": celulas[5],
            "participacao": celulas[6],
        }
    )
