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
    """
    Erro já traduzido para linguagem de gente.

    Guarda também o detalhe técnico (código + mensagem do banco). A tela mostra
    esse detalhe apenas em um bloco recolhido, para o responsável pelo sistema
    descobrir a causa exata sem precisar de adivinhação.
    """

    def __init__(self, mensagem: str, detalhe: str = "") -> None:
        super().__init__(mensagem)
        self.detalhe = detalhe


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
    codigo = getattr(alvo, "code", None)
    if codigo:
        pedacos.append(f"código: {codigo}")
    mensagem = getattr(alvo, "message", None) or str(alvo)
    pedacos.append(f"{type(alvo).__name__}: {mensagem}")
    detalhes = getattr(alvo, "details", None)
    if detalhes:
        pedacos.append(f"detalhes: {detalhes}")
    texto = " | ".join(pedacos)

    # Remove qualquer chave/senha que possa ter vazado dentro da mensagem
    for segredo in (_config("SUPABASE_ANON_KEY"), _config("APP_KEY")):
        if segredo and len(segredo) >= 6:
            texto = texto.replace(segredo, "***")
    return texto[:600]


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
    tipo = type(exc).__name__.lower()

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

    # Problemas de conexão (checado primeiro: é o mais comum)
    padroes_rede = (
        "timeout", "timed out", "connection", "network", "getaddrinfo", "ssl",
        "name or service", "nodename", "errno -2", "errno -3", "unreachable",
        "connection refused", "connection reset", "certificate", "temporary failure",
    )
    tipos_rede = ("connecterror", "connecttimeout", "readtimeout", "remoteprotocol",
                  "networkerror", "gaierror", "timeouterror")
    if any(p in texto for p in padroes_rede) or any(t in tipo for t in tipos_rede):
        return (
            "📡 Não foi possível falar com o banco de dados. Verifique: (1) se a "
            "SUPABASE_URL está correta nas configurações; (2) se o projeto do Supabase "
            "não está pausado; (3) sua conexão com a internet. Depois tente novamente."
        )

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
        raise ErroBanco(mensagem_erro(exc), detalhe_tecnico(exc)) from exc

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
        raise ErroBanco(mensagem_erro(exc), detalhe_tecnico(exc)) from exc

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
        raise ErroBanco(mensagem_erro(exc), detalhe_tecnico(exc)) from exc

    total = resposta.count if getattr(resposta, "count", None) is not None else 0
    return list(resposta.data or []), int(total)


def contar_registros() -> int:
    """Devolve apenas o total de registros (consulta leve)."""
    cliente = get_cliente()
    try:
        resposta = cliente.table("registros").select("id", count="exact").limit(1).execute()
    except Exception as exc:  # noqa: BLE001
        raise ErroBanco(mensagem_erro(exc), detalhe_tecnico(exc)) from exc
    return int(resposta.count or 0)
