"""
db.py
=====
Toda a comunicação com o Supabase fica AQUI — em nenhum outro lugar.

IMPORTANTE (mudança importante nesta versão):
    Este arquivo NÃO usa mais a biblioteca "supabase". Ele conversa com o
    banco usando apenas recursos que já vêm no Python (biblioteca "urllib").

    Por quê? A biblioteca "supabase" arrasta várias outras bibliotecas
    (httpx, gotrue, postgrest, storage3...). No Streamlit Community Cloud
    essas versões às vezes entram em conflito com as que já estão
    instaladas, e o app falha de um jeito difícil de descobrir.

    Usando urllib: zero dependências, zero conflito de versão, e o mesmo
    resultado. O banco é acessado pela API REST do Supabase, que é o mesmo
    caminho que a biblioteca usava por baixo dos panos.

Como funciona a segurança:
  1. O aplicativo usa a chave PÚBLICA (anon key). Ela pode aparecer no
     código sem risco: sozinha, ela não tem permissão para nada.
  2. A tabela "registros" está FECHADA para acesso direto (RLS ligado,
     sem políticas). Ninguém lê nem grava indo direto na API.
  3. Todo acesso passa pelas FUNÇÕES do banco (inserir_registro,
     consultar_registros, ...). Elas recebem a senha do aplicativo
     (APP_KEY) como parâmetro, conferem e só então executam.
  4. A chave "service_role" (chave-mestra) NUNCA é usada aqui.

Onde ficam as configurações:
  - Publicado (Streamlit Cloud): em "Settings -> Secrets"
  - No seu computador: no arquivo .env
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime
from decimal import Decimal

import streamlit as st

# Carrega o .env quando rodando no computador (no Streamlit Cloud não existe).
# É opcional: se a biblioteca não existir, o app segue normalmente.
try:  # pragma: no cover
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


# ------------------------------------------------------------------
# Configuração
# ------------------------------------------------------------------
def _config(nome: str, padrao: str = "") -> str:
    """Lê uma configuração: primeiro dos Secrets do Streamlit, depois do ambiente."""
    try:
        if nome in st.secrets:  # type: ignore[operator]
            return str(st.secrets[nome]).strip()
    except Exception:
        # st.secrets levanta erro quando não existe arquivo de secrets
        pass
    return str(os.environ.get(nome, padrao)).strip()


def ler_config(nome: str, padrao: str = "") -> str:
    """
    Versão pública de _config(), para uso na tela.
    Serve, por exemplo, para saber se a consulta exige senha.
    """
    return _config(nome, padrao)


def diagnosticar() -> list[dict]:
    """
    Diagnóstico das configurações — SEM revelar nenhum valor.
    Devolve, para cada variável: nome, se foi encontrada e de onde veio.
    Usado na tela para o usuário descobrir o que está faltando.
    """
    resultado = []
    for nome, obrigatoria in (
        ("SUPABASE_URL", True),
        ("SUPABASE_ANON_KEY", True),
        ("APP_KEY", True),
        ("CONSULTA_PASSWORD", False),
    ):
        origem = "ausente"
        valor = ""

        # 1) Tenta os Secrets do Streamlit (é onde o Streamlit Cloud guarda)
        try:
            if nome in st.secrets:  # type: ignore[operator]
                valor = str(st.secrets[nome]).strip()
                origem = "Secrets do Streamlit"
        except Exception:
            pass

        # 2) Se não achou, tenta variável de ambiente / arquivo .env
        if not valor:
            valor = str(os.environ.get(nome, "")).strip()
            if valor:
                origem = "variável de ambiente (.env)"

        resultado.append(
            {
                "nome": nome,
                "encontrada": bool(valor),
                "origem": origem,
                "obrigatoria": obrigatoria,
                "tamanho": len(valor),
            }
        )
    return resultado


def configuracao_completa() -> tuple[bool, list[str]]:
    """
    Confere se as configurações obrigatórias existem.
    Devolve (esta_ok, lista_de_problemas) — sem revelar nenhum valor.
    """
    problemas = []
    if not _config("SUPABASE_URL"):
        problemas.append("SUPABASE_URL não configurada")
    if not _config("SUPABASE_ANON_KEY"):
        problemas.append("SUPABASE_ANON_KEY não configurada")
    if not _config("APP_KEY"):
        problemas.append("APP_KEY não configurada")
    return (len(problemas) == 0), problemas


# ------------------------------------------------------------------
# Erros
# ------------------------------------------------------------------
class ConfiguracaoAusente(Exception):
    """Falta alguma variável de ambiente/secrets."""


class ErroBanco(Exception):
    """
    Erro já traduzido para linguagem de gente.

    Guarda também o detalhe técnico (código + mensagem do banco). A tela mostra
    esse detalhe apenas em um bloco recolhido, para o responsável pelo sistema
    descobrir a causa exata sem precisar de adivinhação.
    """

    def __init__(self, mensagem: str, detalhe: str = "") -> None:
        super().__init__(mensagem)
        self.detalhe = detalhe


class _ErroHTTP(Exception):
    """
    Erro vindo da API do Supabase, já separado em pedaços.
    É interno: nunca chega até a tela — sempre vira um ErroBanco.
    """

    def __init__(self, status: int, codigo: str, mensagem: str, corpo: str = "") -> None:
        super().__init__(mensagem)
        self.status = status
        self.code = codigo
        self.message = mensagem
        self.corpo = corpo


def detalhe_tecnico(exc: Exception) -> str:
    """
    Resumo técnico curto do erro, para diagnóstico.
    NUNCA inclui a chave anon nem o APP_KEY (são removidos do texto).
    """
    alvo = exc
    causa = getattr(exc, "__cause__", None)
    if causa is not None:
        alvo = causa

    pedacos = []
    status = getattr(alvo, "status", None)
    if status:
        pedacos.append(f"HTTP {status}")
    codigo = getattr(alvo, "code", None)
    if codigo:
        pedacos.append(f"código: {codigo}")
    mensagem = getattr(alvo, "message", None) or str(alvo) or "(sem mensagem)"
    pedacos.append(f"{type(alvo).__name__}: {mensagem}")
    detalhes = getattr(alvo, "details", None)
    if detalhes:
        pedacos.append(f"detalhes: {detalhes}")
    corpo = getattr(alvo, "corpo", "")
    if corpo and corpo not in mensagem:
        pedacos.append(f"resposta: {corpo[:180]}")
    texto = " | ".join(pedacos)

    # Remove qualquer chave/senha que possa ter vazado dentro da mensagem
    for segredo in (_config("SUPABASE_ANON_KEY"), _config("APP_KEY")):
        if segredo and len(segredo) >= 6:
            texto = texto.replace(segredo, "***")
    return texto[:700]


def mensagem_erro(exc: Exception) -> str:
    """
    Traduz o erro técnico em uma mensagem compreensível.
    NUNCA devolve chaves, URLs internas ou detalhes de infraestrutura.
    """
    if isinstance(exc, ConfiguracaoAusente):
        return (
            f"⚙️ {exc} Avise o responsável pelo sistema para conferir as "
            "configurações (Secrets) do aplicativo."
        )

    causa = getattr(exc, "__cause__", None)
    # O texto de busca junta: a mensagem, o código do banco e o status HTTP.
    # Sem isso, o código 42501 (que vem em um campo separado) não seria visto.
    texto = " ".join(
        str(parte)
        for parte in (
            str(exc),
            getattr(exc, "code", ""),
            getattr(exc, "message", ""),
            getattr(exc, "corpo", ""),
            getattr(causa, "code", ""),
        )
        if parte
    ).lower()
    tipo = type(exc).__name__.lower()
    status = getattr(exc, "status", None) or getattr(causa, "status", None)

    # URL configurada errada (sem https, com barra sobrando, etc.)
    if "unknown url type" in texto or "no host given" in texto or "invalid url" in texto:
        return (
            "🔗 A **SUPABASE_URL** está em formato inválido. Ela deve começar com "
            "**https://** e terminar em **.supabase.co**, sem barra no final. "
            "Exemplo: `https://abcdefgh.supabase.co`"
        )

    # Chave anon inválida, incompleta ou de outro projeto
    if (
        "invalid api key" in texto
        or "invalid jwt" in texto
        or "no api key found" in texto
        or "json could not be generated" in texto
    ):
        return (
            "🔑 A chave de acesso ao banco (SUPABASE_ANON_KEY) foi recusada. "
            "Normalmente acontece quando ela foi colada pela metade, com quebra "
            "de linha, ou pertence a outro projeto. Copie novamente em "
            "Supabase → Settings → API Keys → **anon public** e cole inteira, "
            "entre aspas duplas, nos Secrets do app."
        )

    # Função do banco ainda não criada
    if "pgrst202" in texto or "could not find the function" in texto or "42883" in texto:
        return (
            "🧩 Falta rodar o script SQL mais recente no banco. Abra o Supabase → "
            "SQL Editor → New query, cole o conteúdo de "
            "**sql/03_funcoes_seguras.sql** (trocando a senha) e clique em **Run**."
        )

    # Tabela não encontrada
    if "pgrst205" in texto or "could not find the table" in texto or "42p01" in texto:
        return (
            "🗂️ A tabela **registros** não foi encontrada no banco. Rode o "
            "script SQL (sql/01_criar_tabela_registros.sql) no SQL Editor do "
            "Supabase e confira se ele foi executado no projeto certo."
        )

    # Coluna não encontrada (estrutura da tabela diferente do esperado)
    if "pgrst204" in texto or "could not find the '" in texto:
        return (
            "🧱 A tabela existe, mas a estrutura dela está diferente do "
            "esperado (falta alguma coluna). Rode novamente o script SQL para "
            "recriar a tabela com as 8 colunas."
        )

    # RLS / senha do aplicativo
    if "row-level security" in texto or "42501" in texto or "permission denied" in texto:
        return (
            "🔒 O banco recusou a operação porque a senha do aplicativo "
            "(APP_KEY) não confere com a que está gravada no banco. Confira se "
            "o APP_KEY nos Secrets é **exatamente** igual ao valor gravado em "
            "public.app_config (sem espaços, sem aspas)."
        )

    # Problemas de conexão (checado depois dos erros do banco)
    padroes_rede = (
        "timeout", "timed out", "connection", "network", "getaddrinfo", "ssl",
        "name or service", "nodename", "errno -2", "errno -3", "unreachable",
        "connection refused", "connection reset", "certificate",
        "temporary failure", "urlopen error", "eof occurred",
    )
    tipos_rede = (
        "urlerror", "httperror", "connecterror", "connecttimeout", "readtimeout",
        "remoteprotocol", "networkerror", "gaierror", "timeouterror", "sslerror",
    )
    if any(p in texto for p in padroes_rede) or any(t in tipo for t in tipos_rede):
        return (
            "📡 Não foi possível falar com o banco de dados. Verifique: (1) se a "
            "SUPABASE_URL está correta nas configurações; (2) se o projeto do Supabase "
            "não está pausado; (3) sua conexão com a internet. Depois tente novamente."
        )

    # Valor grande demais para o campo
    if "22003" in texto or "out of range" in texto:
        return "⚠️ Um dos números informados é grande demais para este campo."

    # Texto maior que o permitido
    if "22001" in texto or "too long" in texto:
        return "⚠️ Um dos textos ultrapassa o limite de 50 caracteres."

    # Formato inválido (data, número)
    if "22p02" in texto or "invalid input syntax" in texto:
        return "⚠️ Algum dado está em formato inválido. Confira a data e os números."

    # Campo obrigatório vazio
    if "23502" in texto or "not-null" in texto or "null value" in texto:
        return "⚠️ Um campo obrigatório ficou vazio."

    # Regra de validação do banco
    if "23514" in texto or "check constraint" in texto:
        return "⚠️ O banco recusou o valor por não atender a uma regra de validação."

    # Projeto pausado no Supabase (plano gratuito)
    if "paused" in texto or "project is paused" in texto or status == 503:
        return (
            "😴 O banco de dados está pausado (isso acontece no plano gratuito "
            "após alguns dias sem uso). Entre no painel do Supabase e clique em "
            "'Resume project'. Depois tente novamente."
        )

    # Chave de acesso inválida (formato JWT quebrado)
    if status in (401, 403):
        return (
            "🔑 O banco recusou a chave de acesso. Confira a **SUPABASE_ANON_KEY** "
            "nos Secrets: copie de novo em Supabase → Settings → API Keys e cole "
            "inteira, entre aspas duplas."
        )

    return "❌ Não foi possível concluir a operação. Tente novamente em instantes."


# ------------------------------------------------------------------
# Comunicação com o banco (API REST do Supabase)
# ------------------------------------------------------------------
def _converter(valor):
    """Converte tipos do Python para algo que o JSON entenda."""
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    return valor


def _corpo_json(dados) -> bytes:
    return json.dumps(dados, default=_converter, ensure_ascii=False).encode("utf-8")


def _chamar_rpc(nome_funcao: str, parametros: dict):
    """
    Chama uma FUNÇÃO do banco e devolve o resultado já em Python.

    É o único ponto do sistema que fala com o banco. Qualquer erro
    (rede, permissão, SQL) vira um ErroBanco com mensagem em português.
    """
    ok, problemas = configuracao_completa()
    if not ok:
        raise ConfiguracaoAusente(
            "Configuração incompleta: " + ", ".join(problemas) + "."
        )

    url = _config("SUPABASE_URL").rstrip("/")
    chave = _config("SUPABASE_ANON_KEY")

    if not url.startswith("http"):
        raise ErroBanco(
            "🔗 A **SUPABASE_URL** está em formato inválido. Ela deve começar "
            "com **https://**. Corrija nos Secrets e clique em Reboot app."
        )

    pedido = urllib.request.Request(
        f"{url}/rest/v1/rpc/{nome_funcao}",
        data=_corpo_json(parametros),
        method="POST",
        headers={
            "apikey": chave,
            "Authorization": f"Bearer {chave}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:
            bruto = resposta.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        bruto = ""
        try:
            bruto = exc.read().decode("utf-8", "replace")
        except Exception:
            pass
        codigo, mensagem = "", bruto
        try:
            corpo = json.loads(bruto)
            codigo = str(corpo.get("code") or "")
            mensagem = str(corpo.get("message") or bruto)
        except Exception:
            pass
        erro = _ErroHTTP(exc.code, codigo, mensagem, bruto)
        raise ErroBanco(mensagem_erro(erro), detalhe_tecnico(erro)) from exc
    except Exception as exc:  # noqa: BLE001  (rede, DNS, SSL, timeout...)
        raise ErroBanco(mensagem_erro(exc), detalhe_tecnico(exc)) from exc

    if not bruto.strip():
        return None
    try:
        return json.loads(bruto)
    except Exception as exc:  # noqa: BLE001
        erro = _ErroHTTP(200, "JSON inválido", f"resposta inesperada: {bruto[:120]}", bruto)
        raise ErroBanco(mensagem_erro(erro), detalhe_tecnico(erro)) from exc


# ------------------------------------------------------------------
# Operações
# ------------------------------------------------------------------
def inserir_registro(dados: dict) -> int:
    """
    Grava UM registro e devolve o id gerado pelo banco.
    Só retorna se o banco confirmar a gravação.
    """
    resultado = _chamar_rpc(
        "inserir_registro",
        {
            "p_app_key": _config("APP_KEY"),
            "p_tipo": dados.get("tipo"),
            "p_periodo": dados.get("periodo"),
            "p_posicao": dados.get("posicao"),
            "p_empresa": dados.get("empresa"),
            "p_quantidade": dados.get("quantidade"),
            "p_valor": dados.get("valor"),
            "p_participacao": dados.get("participacao"),
        },
    )

    if resultado is None:
        raise ErroBanco(
            "O banco não confirmou a gravação. O registro pode não ter sido salvo."
        )
    if isinstance(resultado, list):
        resultado = resultado[0] if resultado else None
    if isinstance(resultado, dict):
        resultado = resultado.get("inserir_registro", next(iter(resultado.values())))
    if resultado is None:
        raise ErroBanco(
            "O banco não confirmou a gravação. O registro pode não ter sido salvo."
        )
    return int(resultado)


def inserir_varios(registros: list[dict]) -> list[int]:
    """
    Grava VÁRIOS registros de uma vez (usado na colagem do Excel).
    Devolve a lista de ids gravados.
    """
    if not registros:
        return []

    resultado = _chamar_rpc(
        "inserir_varios",
        {"p_app_key": _config("APP_KEY"), "p_registros": registros},
    )

    if not resultado:
        raise ErroBanco("O banco não confirmou a gravação dos registros.")

    ids = []
    for linha in resultado:
        if isinstance(linha, dict):
            linha = linha.get("inserir_varios", next(iter(linha.values())))
        ids.append(int(linha))
    return ids


def consultar_registros(
    pagina: int = 1,
    por_pagina: int = 25,
    ordenar_por: str = "id",
    decrescente: bool = True,
) -> tuple[list[dict], int]:
    """
    Busca uma página de registros direto do banco.
    Devolve (lista_de_registros, total_de_registros_no_banco).

    A paginação acontece dentro do banco: pedimos só as linhas
    daquela página, então funciona igual com 10 ou 1.000.000.
    """
    colunas_permitidas = {"id", "periodo", "tipo", "empresa", "valor"}
    if ordenar_por not in colunas_permitidas:
        ordenar_por = "id"

    pagina = max(1, int(pagina))
    por_pagina = max(1, min(int(por_pagina), 200))

    linhas = _chamar_rpc(
        "consultar_registros",
        {
            "p_app_key": _config("APP_KEY"),
            "p_pagina": pagina,
            "p_por_pagina": por_pagina,
            "p_ordenar_por": ordenar_por,
            "p_decrescente": bool(decrescente),
        },
    )
    total = contar_registros()
    return list(linhas or []), total


def contar_registros() -> int:
    """Devolve apenas o total de registros (consulta leve)."""
    resultado = _chamar_rpc("contar_registros", {"p_app_key": _config("APP_KEY")})
    if resultado is None:
        return 0
    if isinstance(resultado, list):
        resultado = resultado[0] if resultado else 0
    if isinstance(resultado, dict):
        resultado = resultado.get("contar_registros", next(iter(resultado.values())))
    return int(resultado or 0)
