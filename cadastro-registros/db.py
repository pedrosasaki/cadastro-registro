"""
db.py
=====
Toda a comunicação com o Supabase fica AQUI — em nenhum outro lugar.

Como funciona a segurança:
  1. O aplicativo usa a chave PÚBLICA (anon key). Ela pode aparecer no
     código sem risco: sozinha, ela não tem permissão para nada.
  2. Junto com cada requisição, enviamos o cabeçalho "x-app-key" com a
     senha que você escolheu no script SQL.
  3. O banco (RLS) confere esse cabeçalho. Sem ele: gravação e consulta
     são NEGADAS.
  4. A chave "service_role" (chave-mestra) NUNCA é usada aqui.

Onde ficam as configurações:
  - Publicado (Streamlit Cloud): em "Settings -> Secrets"
  - No seu computador: no arquivo .env
"""

from __future__ import annotations

import os

import streamlit as st

# Carrega o .env quando rodando no computador (no Streamlit Cloud não existe)
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv é opcional
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


@st.cache_resource(show_spinner=False)
def _criar_cliente(url: str, chave_anon: str, app_key: str):
    """
    Cria o cliente Supabase uma única vez por sessão do servidor.
    O cabeçalho x-app-key é anexado a TODAS as requisições.
    """
    from supabase import ClientOptions, create_client

    opcoes = ClientOptions(headers={"x-app-key": app_key})
    return create_client(url, chave_anon, options=opcoes)


def get_cliente():
    """Devolve o cliente pronto ou levanta um erro amigável."""
    ok, problemas = configuracao_completa()
    if not ok:
        raise ConfiguracaoAusente(
            "Configuração incompleta: " + ", ".join(problemas) + "."
        )
    return _criar_cliente(
        _config("SUPABASE_URL"),
        _config("SUPABASE_ANON_KEY"),
        _config("APP_KEY"),
    )


# ------------------------------------------------------------------
# Erros
# ------------------------------------------------------------------
class ConfiguracaoAusente(Exception):
    """Falta alguma variável de ambiente/secrets."""


class ErroBanco(Exception):
    """Erro já traduzido para linguagem de gente."""


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

    texto = str(exc).lower()

    # RLS bloqueou a operação
    if "row-level security" in texto or "42501" in texto or "permission denied" in texto:
        return (
            "🔒 O banco recusou a operação. Isso normalmente acontece quando a "
            "chave de acesso do aplicativo (APP_KEY) não confere com a senha "
            "definida no banco. Avise o responsável pelo sistema."
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

    # Problemas de conexão
    if any(p in texto for p in ("timeout", "timed out", "connection", "network", "getaddrinfo", "ssl")):
        return (
            "📡 Não foi possível falar com o banco de dados agora. "
            "Verifique sua internet e tente novamente em alguns instantes."
        )

    # Projeto pausado no Supabase (plano gratuito)
    if "paused" in texto or "project is paused" in texto or "503" in texto:
        return (
            "😴 O banco de dados está pausado (isso acontece no plano gratuito "
            "após alguns dias sem uso). Entre no painel do Supabase e clique em "
            "'Resume project'. Depois tente novamente."
        )

    return "❌ Não foi possível concluir a operação. Tente novamente em instantes."


# ------------------------------------------------------------------
# Operações
# ------------------------------------------------------------------
def inserir_registro(dados: dict) -> int:
    """
    Grava UM registro e devolve o id gerado pelo banco.
    Só retorna se o banco confirmar a gravação.
    """
    cliente = get_cliente()
    try:
        resposta = cliente.table("registros").insert(dados).execute()
    except Exception as exc:  # noqa: BLE001
        raise ErroBanco(mensagem_erro(exc)) from exc

    if not getattr(resposta, "data", None):
        raise ErroBanco(
            "O banco não confirmou a gravação. O registro pode não ter sido salvo."
        )
    return int(resposta.data[0]["id"])


def inserir_varios(registros: list[dict]) -> list[int]:
    """
    Grava VÁRIOS registros de uma vez (usado na colagem do Excel).
    Devolve a lista de ids gravados.
    """
    if not registros:
        return []
    cliente = get_cliente()
    try:
        resposta = cliente.table("registros").insert(registros).execute()
    except Exception as exc:  # noqa: BLE001
        raise ErroBanco(mensagem_erro(exc)) from exc

    if not getattr(resposta, "data", None):
        raise ErroBanco("O banco não confirmou a gravação dos registros.")
    return [int(linha["id"]) for linha in resposta.data]


def consultar_registros(
    pagina: int = 1,
    por_pagina: int = 25,
    ordenar_por: str = "id",
    decrescente: bool = True,
) -> tuple[list[dict], int]:
    """
    Busca uma página de registros direto do banco.
    Devolve (lista_de_registros, total_de_registros_no_banco).

    A paginação usa "range": pedimos só as linhas daquela página,
    então funciona igual com 10 ou com 1.000.000 de registros.
    """
    colunas_permitidas = {"id", "periodo", "tipo", "empresa", "valor"}
    if ordenar_por not in colunas_permitidas:
        ordenar_por = "id"

    pagina = max(1, int(pagina))
    por_pagina = max(1, min(int(por_pagina), 200))
    inicio = (pagina - 1) * por_pagina
    fim = inicio + por_pagina - 1

    cliente = get_cliente()
    try:
        resposta = (
            cliente.table("registros")
            .select("*", count="exact")
            .order(ordenar_por, desc=decrescente)
            .range(inicio, fim)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise ErroBanco(mensagem_erro(exc)) from exc

    total = resposta.count if getattr(resposta, "count", None) is not None else 0
    return list(resposta.data or []), int(total)


def contar_registros() -> int:
    """Devolve apenas o total de registros (consulta leve)."""
    cliente = get_cliente()
    try:
        resposta = cliente.table("registros").select("id", count="exact").limit(1).execute()
    except Exception as exc:  # noqa: BLE001
        raise ErroBanco(mensagem_erro(exc)) from exc
    return int(resposta.count or 0)
