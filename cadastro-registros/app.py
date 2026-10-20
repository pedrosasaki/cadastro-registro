"""
app.py
======
Aplicação de Cadastro e Consulta de Dados.

Como rodar no seu computador:
    streamlit run app.py

O que tem aqui:
  Aba 1 - Cadastro: formulário de um registro por vez.
  Aba 2 - Colar do Excel: vários registros de uma vez.
  Aba 3 - Consulta: tabela com os registros gravados, com paginação.

Este arquivo cuida só da TELA. As regras ficam em validacoes.py
e a conversa com o banco fica em db.py.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
import streamlit as st

import db
import validacoes as v

# ------------------------------------------------------------------
# Configuração da página
# ------------------------------------------------------------------
st.set_page_config(
    page_title="Cadastro de Dados",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Um pouco de CSS para melhorar o espaçamento no celular e no computador
st.markdown(
    """
    <style>
      .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1150px; }
      div[data-testid="stForm"] { border: 1px solid #e6e6e6; border-radius: 12px; padding: 1.2rem; }
      .aviso { background: #fff8e1; border-left: 4px solid #f9a825;
               padding: .8rem 1rem; border-radius: 6px; font-size: .92rem; }
      @media (max-width: 640px) {
        .block-container { padding-left: .8rem; padding-right: .8rem; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------
# Limpeza do formulário (roda ANTES dos campos serem criados)
# ------------------------------------------------------------------
if st.session_state.get("_limpar_form"):
    st.session_state["_limpar_form"] = False
    for chave in [k for k in list(st.session_state.keys()) if k.startswith("f_")]:
        del st.session_state[chave]


def formatar_valor_br(valor) -> str:
    """Mostra 1234.56 como '1.234,56' (padrão brasileiro)."""
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return str(valor)
    texto = f"{numero:,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


# ------------------------------------------------------------------
# Cabeçalho
# ------------------------------------------------------------------
st.title("📋 Cadastro de Dados")
st.caption(
    "Preencha os campos e clique em **Salvar registro**. "
    "Os dados vão direto para o banco de dados."
)

# ------------------------------------------------------------------
# Diagnóstico das configurações (aparece só quando algo está faltando)
# ------------------------------------------------------------------
def mostrar_diagnostico():
    """Tabela com o estado de cada variável — nunca mostra os valores."""
    st.markdown("#### 🔎 Diagnóstico das configurações")
    linhas = []
    for item in db.diagnosticar():
        if item["encontrada"]:
            situacao = "✅ encontrada"
        elif item["obrigatoria"]:
            situacao = "❌ FALTANDO"
        else:
            situacao = "— opcional, não configurada"
        linhas.append(
            {
                "Variável": item["nome"],
                "Situação": situacao,
                "Lida de": item["origem"],
                "Caracteres": item["tamanho"] if item["encontrada"] else 0,
            }
        )
    st.dataframe(pd.DataFrame(linhas), width="stretch", hide_index=True)

    st.markdown(
        """
        **Como corrigir no Streamlit Community Cloud:**

        1. Abra **https://share.streamlit.io** e localize seu app.
        2. Clique nos **três pontinhos (⋮)** ao lado do app → **Settings**.
        3. Vá na aba **Secrets**.
        4. Cole o bloco abaixo, **trocando os valores** pelos seus:

        ```toml
        SUPABASE_URL = "https://pvwlmpavipnyjwkxflti.supabase.co"
        SUPABASE_ANON_KEY = "sua_chave_anon_public"
        APP_KEY = "a_senha_que_voce_colocou_no_SQL"
        CONSULTA_PASSWORD = "uma_senha_para_a_consulta"
        ```

        5. Clique em **Save**.
        6. Volte ao app e clique em **Reboot app** (no menu ⋮) para recarregar.

        **Erros mais comuns no formato:**
        - Usar `SUPABASE_URL=https://...` (estilo `.env`, **sem aspas**) →
          o Streamlit espera **TOML**, com **aspas duplas** e sinal de **igual**.
        - Deixar vírgula no fim da linha.
        - Colar o conteúdo do `.env` inteiro, com os comentários `#` no meio
          de um valor.
        - Salvar em **Settings → Secrets** de **outro** app.
        """
    )

    if st.button("🔌 Testar conexão com o banco agora", key="diag_testar"):
        try:
            total = db.contar_registros()
            st.success(
                f"✅ Conexão funcionando! O banco respondeu e tem **{total}** "
                "registro(s) acessível(is) com a chave atual."
            )
        except db.ErroBanco as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(db.mensagem_erro(exc))


# Aviso de configuração incompleta (sem revelar valores)
_ok, _problemas = db.configuracao_completa()
if not _ok:
    st.error(
        "⚙️ **O aplicativo ainda não está configurado.**\n\n"
        "Faltam estas configurações: " + ", ".join(f"`{p}`" for p in _problemas) + ".\n\n"
        "Isso significa que as **variáveis de ambiente** não foram encontradas. "
        "Abra o diagnóstico abaixo para ver exatamente o que fazer."
    )
    with st.expander("🔎 Abrir diagnóstico e instruções", expanded=True):
        mostrar_diagnostico()
    st.stop()

# Mensagem de sucesso vinda da gravação anterior
if st.session_state.get("_msg_sucesso"):
    st.success(st.session_state.pop("_msg_sucesso"))

aba_cadastro, aba_excel, aba_consulta = st.tabs(
    ["✏️ Cadastro", "📥 Colar do Excel", "🔎 Consulta"]
)


# ==================================================================
# ABA 1 — CADASTRO INDIVIDUAL
# ==================================================================
with aba_cadastro:
    st.subheader("Cadastro de Dados")

    st.markdown(
        '<div class="aviso">Os campos com <b>*</b> são obrigatórios. '
        "<b>Posição</b> e <b>Participação</b> podem ficar em branco.</div>",
        unsafe_allow_html=True,
    )
    st.write("")

    with st.form("form_cadastro", clear_on_submit=False):
        col_esq, col_dir = st.columns(2)

        tipo = col_esq.text_input(
            "Tipo *",
            key="f_tipo",
            placeholder="Ex.: Vendas",
            help="Texto de até 50 caracteres.",
        )
        periodo = col_dir.date_input(
            "Período *",
            value=date.today(),
            format="DD/MM/YYYY",
            key="f_periodo",
            help="Clique no ícone de calendário para escolher a data.",
        )

        posicao = col_esq.text_input(
            "Posição",
            key="f_posicao",
            placeholder="Ex.: 1",
            help="Número inteiro. Pode ficar em branco. Aceita valores negativos.",
        )
        empresa = col_dir.text_input(
            "Empresa *",
            key="f_empresa",
            placeholder="Ex.: Empresa Exemplo Ltda",
            help="Texto de até 50 caracteres.",
        )

        quantidade = col_esq.text_input(
            "Quantidade *",
            key="f_quantidade",
            placeholder="Ex.: 100",
            help="Número inteiro. Aceita valores negativos.",
        )
        valor = col_dir.text_input(
            "Valor *",
            key="f_valor",
            placeholder="Ex.: 1.234,56",
            help="Aceita o padrão brasileiro (1.234,56) ou 1234.56. Máximo 2 casas decimais.",
        )

        participacao = col_esq.text_input(
            "Participação",
            key="f_participacao",
            placeholder="Ex.: 25",
            help="Número inteiro. Pode ficar em branco.",
        )

        st.write("")
        enviado = st.form_submit_button(
            "💾 Salvar registro",
            type="primary",
            width="stretch",
            disabled=st.session_state.get("_gravando", False),
        )

    if enviado:
        st.session_state["_gravando"] = True
        try:
            dados, erros = v.validar_formulario(
                {
                    "tipo": tipo,
                    "periodo": periodo,
                    "posicao": posicao,
                    "empresa": empresa,
                    "quantidade": quantidade,
                    "valor": valor,
                    "participacao": participacao,
                }
            )

            if erros:
                st.error("**Confira os campos abaixo antes de salvar:**")
                for erro in erros:
                    st.markdown(f"- {erro}")
            else:
                novo_id = db.inserir_registro(dados)
                st.session_state["_msg_sucesso"] = (
                    f"✅ Registro **#{novo_id}** gravado com sucesso no banco de dados!"
                )
                st.session_state["_limpar_form"] = True
                st.rerun()

        except db.ErroBanco as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(db.mensagem_erro(exc))
        finally:
            st.session_state["_gravando"] = False


# ==================================================================
# ABA 2 — COLAR DO EXCEL
# ==================================================================
with aba_excel:
    st.subheader("Colar várias linhas do Excel")
    st.caption(
        "Selecione as células no Excel, copie (Ctrl+C) e cole abaixo. "
        "Cada linha vira um registro."
    )

    st.markdown(
        """
        **Ordem das colunas (a mesma do formulário):**

        `Tipo` → `Período` → `Posição` → `Empresa` → `Quantidade` → `Valor` → `Participação`

        - Separe as colunas com **Tabulação** (o Ctrl+C do Excel já faz isso).
        - Datas no formato **dd/mm/aaaa**.
        - Valores no padrão brasileiro (**1.234,56**).
        - Se você copiar também a linha de cabeçalho, ela é ignorada automaticamente.
        """
    )

    texto_colado = st.text_area(
        "Cole aqui as linhas",
        height=180,
        key="x_texto",
        placeholder=(
            "Vendas\t31/01/2026\t1\tEmpresa A\t100\t1.234,56\t25\n"
            "Compras\t28/02/2026\t2\tEmpresa B\t50\t987,65\t"
        ),
    )

    col_a, col_b = st.columns([1, 1])
    conferir = col_a.button("🔍 Conferir linhas", width="stretch", key="x_conferir")
    limpar_texto = col_b.button("🧹 Limpar", width="stretch", key="x_limpar")

    if limpar_texto:
        st.session_state["x_texto"] = ""
        st.session_state.pop("x_resultado", None)
        st.rerun()

    if conferir:
        linhas = [l for l in texto_colado.splitlines() if l.strip() != ""]
        if not linhas:
            st.warning("Cole pelo menos uma linha antes de conferir.")
            st.session_state.pop("x_resultado", None)
        else:
            # Ignora a linha de cabeçalho, se o usuário copiou junto
            primeira = v.dividir_linha_excel(linhas[0])
            if primeira and primeira[0].strip().lower() in ("tipo", "type"):
                linhas = linhas[1:]

            resultados = []
            for indice, linha in enumerate(linhas, start=1):
                celulas = v.dividir_linha_excel(linha)
                dados, erros = v.validar_linha_excel(celulas)
                resultados.append(
                    {
                        "linha": indice,
                        "celulas": celulas,
                        "dados": dados,
                        "erros": erros,
                    }
                )
            st.session_state["x_resultado"] = resultados

    resultado = st.session_state.get("x_resultado")
    if resultado:
        validos = [r for r in resultado if not r["erros"]]
        invalidos = [r for r in resultado if r["erros"]]

        st.divider()
        st.markdown(
            f"**Resumo:** {len(resultado)} linha(s) lida(s) — "
            f"✅ {len(validos)} válida(s) · ❌ {len(invalidos)} com problema(s)"
        )

        # Prévia em tabela
        previa = []
        for r in resultado:
            c = r["celulas"] + [""] * (7 - len(r["celulas"]))
            previa.append(
                {
                    "Linha": r["linha"],
                    "Tipo": c[0],
                    "Período": c[1],
                    "Posição": c[2],
                    "Empresa": c[3],
                    "Quantidade": c[4],
                    "Valor": c[5],
                    "Participação": c[6],
                    "Situação": "✅ OK" if not r["erros"] else "❌ " + " | ".join(r["erros"]),
                }
            )
        st.dataframe(
            pd.DataFrame(previa),
            width="stretch",
            hide_index=True,
            height=min(420, 60 + 35 * len(previa)),
        )

        if invalidos:
            st.warning(
                "As linhas com ❌ **não serão gravadas**. Corrija-as no Excel e cole de novo, "
                "ou grave apenas as válidas."
            )

        if validos:
            rotulo = (
                f"💾 Salvar {len(validos)} registro(s) válido(s)"
                if len(validos) > 1
                else "💾 Salvar 1 registro válido"
            )
            if st.button(rotulo, type="primary", width="stretch", key="x_salvar"):
                try:
                    ids = db.inserir_varios([r["dados"] for r in validos])
                    st.session_state["_msg_sucesso"] = (
                        f"✅ {len(ids)} registro(s) gravado(s) com sucesso! "
                        f"IDs: {', '.join('#' + str(i) for i in ids[:20])}"
                        + (" ..." if len(ids) > 20 else "")
                    )
                    st.session_state["x_texto"] = ""
                    st.session_state.pop("x_resultado", None)
                    st.rerun()
                except db.ErroBanco as exc:
                    st.error(str(exc))
                except Exception as exc:  # noqa: BLE001
                    st.error(db.mensagem_erro(exc))
        else:
            st.info("Nenhuma linha válida para gravar. Corrija os problemas indicados acima.")


# ==================================================================
# ABA 3 — CONSULTA
# ==================================================================
with aba_consulta:
    st.subheader("Registros gravados")

    senha_consulta = db.ler_config("CONSULTA_PASSWORD")
    autorizado = True

    if senha_consulta:
        autorizado = bool(st.session_state.get("_consulta_ok"))
        if not autorizado:
            st.info("🔒 Esta página é protegida por senha.")
            with st.form("form_senha_consulta"):
                tentativa = st.text_input("Senha de acesso", type="password", key="c_senha")
                entrar = st.form_submit_button("Entrar", type="primary")
            if entrar:
                if tentativa == senha_consulta:
                    st.session_state["_consulta_ok"] = True
                    st.rerun()
                else:
                    st.error("Senha incorreta. Tente novamente.")

    if autorizado:
        # ---------- Controles ----------
        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1, 1])
        ordenar_por = c1.selectbox(
            "Ordenar por",
            options=["id", "periodo", "tipo", "empresa", "valor"],
            format_func=lambda x: {
                "id": "ID",
                "periodo": "Período",
                "tipo": "Tipo",
                "empresa": "Empresa",
                "valor": "Valor",
            }[x],
            index=0,
            key="c_ordenar",
        )
        ordem = c2.selectbox(
            "Ordem",
            options=["decrescente", "crescente"],
            index=0,
            key="c_ordem",
        )
        por_pagina = c3.selectbox(
            "Por página", options=[10, 25, 50, 100], index=1, key="c_por_pagina"
        )
        if c4.button("🔄 Atualizar", width="stretch", key="c_atualizar"):
            st.rerun()

        # ---------- Busca no banco ----------
        try:
            total = db.contar_registros()
        except db.ErroBanco as exc:
            st.error(str(exc))
            total = 0
        except Exception as exc:  # noqa: BLE001
            st.error(db.mensagem_erro(exc))
            total = 0

        if total == 0:
            st.info(
                "Nenhum registro encontrado no banco. "
                "Use a aba **Cadastro** para gravar o primeiro."
            )
        else:
            total_paginas = max(1, -(-total // por_pagina))  # arredonda para cima

            # Garante que a página pedida existe
            if st.session_state.get("c_pagina", 1) > total_paginas:
                st.session_state["c_pagina"] = total_paginas

            pagina = st.number_input(
                f"Página (de {total_paginas})",
                min_value=1,
                max_value=total_paginas,
                value=min(st.session_state.get("c_pagina", 1), total_paginas),
                step=1,
                key="c_pagina",
            )

            try:
                registros, total_banco = db.consultar_registros(
                    pagina=int(pagina),
                    por_pagina=int(por_pagina),
                    ordenar_por=ordenar_por,
                    decrescente=(ordem == "decrescente"),
                )
            except db.ErroBanco as exc:
                st.error(str(exc))
                registros, total_banco = [], 0
            except Exception as exc:  # noqa: BLE001
                st.error(db.mensagem_erro(exc))
                registros, total_banco = [], 0

            if registros:
                df = pd.DataFrame(registros)

                # Ajustes de exibição (o banco guarda o valor exato como NUMERIC)
                if "periodo" in df.columns:
                    df["periodo"] = pd.to_datetime(df["periodo"], errors="coerce")
                if "valor" in df.columns:
                    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")

                colunas = [
                    "id", "tipo", "periodo", "posicao",
                    "empresa", "quantidade", "valor", "participacao",
                ]
                df = df[[c for c in colunas if c in df.columns]]

                st.dataframe(
                    df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "id": st.column_config.NumberColumn("ID", format="%d", width="small"),
                        "tipo": st.column_config.TextColumn("Tipo", width="medium"),
                        "periodo": st.column_config.DateColumn(
                            "Período", format="DD/MM/YYYY", width="small"
                        ),
                        "posicao": st.column_config.NumberColumn("Posição", format="%d", width="small"),
                        "empresa": st.column_config.TextColumn("Empresa", width="medium"),
                        "quantidade": st.column_config.NumberColumn(
                            "Quantidade", format="%d", width="small"
                        ),
                        "valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
                        "participacao": st.column_config.NumberColumn(
                            "Participação", format="%d", width="small"
                        ),
                    },
                )

                inicio = (int(pagina) - 1) * int(por_pagina) + 1
                fim = inicio + len(registros) - 1
                st.caption(
                    f"Mostrando **{inicio}–{fim}** de **{total_banco}** registro(s) · "
                    f"página **{pagina}** de **{total_paginas}**"
                )
            else:
                st.info("Esta página não tem registros. Volte para a página 1.")


# ------------------------------------------------------------------
# Rodapé
# ------------------------------------------------------------------
st.divider()
st.caption(
    "Dados gravados no Supabase (PostgreSQL) · "
    "Aplicação publicada no Streamlit Community Cloud · "
    "Edição e exclusão de registros não estão disponíveis nesta versão."
)
