# 📋 Cadastro de Dados — Aplicação web gratuita

Aplicação web (Streamlit + Python) para **cadastro e consulta de registros**, com banco de dados **Supabase (PostgreSQL)** e publicação gratuita no **Streamlit Community Cloud**.

> 🔒 **Importante:** este repositório é **público** e contém apenas o código do aplicativo. **Nenhuma credencial real está aqui** — todas as chaves e senhas ficam guardadas nas variáveis de ambiente (secretas), fora do repositório.

## 🧱 Estrutura do projeto

```
cadastro-registros/
├── app.py                  # Aplicativo principal (formulário + consulta)
├── db.py                   # Comunicação com o Supabase
├── validacoes.py           # Validações dos campos
├── requirements.txt        # Dependências do projeto
├── .env.example            # Modelo das variáveis de ambiente (sem segredos)
├── .gitignore              # Arquivos que não vão para o GitHub
├── sql/
│   └── 01_criar_tabela_registros.sql   # Script SQL da tabela e segurança
└── README.md               # Este arquivo
```

## 🚀 Como rodar no seu computador (teste local)

1. Instale o Python 3.10+ em https://python.org
2. Abra o terminal na pasta do projeto e crie um ambiente virtual:

   ```bash
   python -m venv .venv
   ```

3. Ative o ambiente:
   - **Windows:** `.venv\Scripts\activate`
   - **Mac/Linux:** `source .venv/bin/activate`

4. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```

5. Copie `.env.example` para `.env` e preencha os valores reais:

   ```bash
   cp .env.example .env   # depois edite o .env com seus dados
   ```

6. Rode o aplicativo:

   ```bash
   streamlit run app.py
   ```

## 🌐 Como publicar (Streamlit Community Cloud)

1. Suba este código para o seu repositório no GitHub.
2. Acesse https://share.streamlit.io e faça login com o GitHub.
3. Clique em **New app**, selecione o repositório, a branch e o arquivo `app.py`.
4. Em **Settings → Secrets**, informe as mesmas variáveis do `.env`:

   ```toml
   SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
   SUPABASE_ANON_KEY = "eyJ...SUA-CHAVE-ANONIMA..."
   APP_KEY = "SUA-SENHA-ESCOLHIDA-NO-SQL"
   CONSULTA_PASSWORD = ""
   ```

5. Clique em **Deploy** e aguarde — seu link público estará pronto.

## 🗄️ Banco de dados

- Tabela `registros` criada pelo script `sql/01_criar_tabela_registros.sql`
- Segurança **RLS (Row Level Security)** ativada com política de gravação e consulta via crachá (`x-app-key`)
- **Edição e exclusão**: não implementadas na v1 (e sem política SQL para elas)

## ⚠️ Limitações conhecidas (planos gratuitos)

- O **Supabase Free** pausa o projeto após ~7 dias sem uso — basta entrar no painel e clicar em **Resume** (os dados ficam preservados por até 1 ano).
- O **Streamlit Community Cloud** põe o app "para dormir" após inatividade; o primeiro acesso demora 30–60 s para "acordá-lo".
- Gravação **anônima**: qualquer pessoa com o link pode gravar. Não use dados pessoais ou sensíveis reais nos testes.
