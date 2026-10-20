-- ============================================================
-- PROJETO: Cadastro e Consulta de Dados
-- ARQUIVO : 01_criar_tabela_registros.sql
-- BANCO  : Supabase (PostgreSQL)
-- ------------------------------------------------------------
-- O QUE ESTE ARQUIVO FAZ
--   1) Cria a tabela "registros" (os 7 campos + id automático).
--   2) Liga a segurança RLS (Row Level Security).
--   3) Cria 2 "políticas": gravar exige um crachá; consultar
--      exige o mesmo crachá. Sem o crachá, o banco nega.
--
-- COMO USAR
--   No painel do Supabase: menu esquerdo -> SQL Editor ->
--   "New query" -> cole TODO este conteúdo -> clique em "Run".
--   Se aparecer "Success. No rows returned", funcionou.
--
-- ⚠️ ANTES DE RODAR: escolha a senha forte do crachá!
--   Troque as duas ocorrências de <SUA_SENHA_FORTE> abaixo pela
--   mesma senha que você escolher (ex.: Coelho#Azul2026!)
--   Essa senha é usada pelo aplicativo para gravar e consultar.
--   Ela NÃO vai para o navegador do visitante, fica guardada
--   nas configurações secretas do aplicativo.
-- ============================================================

-- ------------------------------------------------------------
-- 1) CRIAÇÃO DA TABELA
-- ------------------------------------------------------------
-- Regras aplicadas (padrão proposto e confirmado na Etapa 1):
--   * id          -> automático (identity), nunca digitado.
--   * tipo        -> obrigatório, no máximo 50 caracteres.
--   * periodo     -> obrigatório, data válida.
--   * posicao     -> OPCIONAL, número inteiro (negativos aceitos).
--   * empresa     -> obrigatório, no máximo 50 caracteres.
--   * quantidade  -> obrigatório, número inteiro (negativos aceitos).
--   * valor       -> obrigatório, NUMERIC(18,2) (precisão exata).
--   * participacao-> OPCIONAL, número inteiro (não tratado como %).
--
-- O tipo VARCHAR(50) já limita o tamanho no próprio banco:
-- se alguém tentar gravar 51 caracteres, o banco recusa com erro.
-- NUMERIC(18,2) guarda 18 algarismos no total, 2 após a vírgula,
-- SEM os erros de arredondamento do ponto flutuante.

create table if not exists public.registros (
    id            bigint          generated always as identity primary key,
    tipo          varchar(50)     not null,
    periodo       date            not null,
    posicao       integer,
    empresa       varchar(50)     not null,
    quantidade    integer         not null,
    valor         numeric(18,2)   not null,
    participacao  integer
);

-- ------------------------------------------------------------
-- 2) SEGURANÇA — RLS (Row Level Security)
-- ------------------------------------------------------------
-- Liga o RLS nesta tabela. A partir daqui, NENHUMA operação
-- via API acontece sem passar por uma política abaixo.
-- (O SQL Editor do painel é o "modo administrador" e ignora
--  o RLS — é por isso que você consegue rodar este script.)

alter table public.registros enable row level security;

-- ------------------------------------------------------------
-- POLÍTICA DE GRAVAÇÃO (INSERT)
-- ------------------------------------------------------------
-- Permite gravar SOMENTE em requisições que apresentem o
-- cabeçalho "x-app-key" com a senha forte escolhida.
-- Sem esse cabeçalho, a gravação é negada (proteção
-- contra robôs que atacam a API diretamente).

create policy "registros_inserir_com_cracha"
    on public.registros
    for insert
    to anon
    with check (
        replace(current_setting('request.headers', true), ' ', '')
        like '%x-app-key:<SUA_SENHA_FORTE>%'
    );

-- ------------------------------------------------------------
-- POLÍTICA DE CONSULTA (SELECT)
-- ------------------------------------------------------------
-- Permite consultar SOMENTE com o mesmo crachá.
-- Assim, os registros NÃO ficam expostos para qualquer pessoa:
-- sem a senha, a leitura devolve vazio (nenhuma linha).

create policy "registros_consultar_com_cracha"
    on public.registros
    for select
    to anon
    using (
        replace(current_setting('request.headers', true), ' ', '')
        like '%x-app-key:<SUA_SENHA_FORTE>%'
    );

-- ------------------------------------------------------------
-- NOTA SOBRE VALIDAÇÃO
-- ------------------------------------------------------------
-- O aplicativo também valida antes de enviar (limites, data,
-- inteiros, duas casas decimais...). O banco é a ÚLTIMA linha
-- de defesa: tipos e tamanhos são conferidos de novo aqui.
--
-- 🚫 NÃO existe política de UPDATE ou DELETE:
--    editar e excluir são operações PROIBIDAS na v1.
--    (Sem id visível, editar/apagar um registro específico
--     seria arriscado. Vamos conversar antes de implementar.)

-- ============================================================
-- COMO ALTERAR AS REGRAS NO FUTURO
-- (guarde estes exemplos — rode um por vez, só quando quiser)
-- ============================================================

-- Tornar "posicao" obrigatório:
-- alter table public.registros alter column posicao set not null;

-- Tornar "posicao" opcional de novo:
-- alter table public.registros alter column posicao drop not null;

-- Exigir que "quantidade" seja sempre >= 0:
-- alter table public.registros
--     add constraint chk_quantidade_nao_negativa check (quantidade >= 0);

-- Exigir que "participacao" fique entre 0 e 100 (se for percentual):
-- alter table public.registros
--     add constraint chk_participacao_percentual check (participacao between 0 and 100);

-- Adicionar uma nova coluna no futuro (ex.: "observacao"):
-- alter table public.registros add column observacao text;

-- ============================================================
-- FIM DO SCRIPT
-- ============================================================
