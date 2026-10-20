-- ============================================================
-- 02 — CORREÇÃO DAS POLÍTICAS DE SEGURANÇA (RLS)
-- ============================================================
-- Execute este script no SQL Editor do Supabase.
--
-- POR QUE ESTE SCRIPT EXISTE
-- A primeira versão das políticas procurava o texto
--     x-app-key:SENHA
-- dentro dos cabeçalhos da requisição. Mas o banco entrega os
-- cabeçalhos em formato JSON, assim:
--     {"x-app-key":"SENHA", ...}
-- Repare nas ASPAS em volta do valor. Por isso a comparação
-- anterior NUNCA encontrava a senha e o banco recusava TODAS
-- as gravações (erro 42501 — "row-level security policy").
--
-- A correção abaixo lê o cabeçalho como JSON de verdade, o que
-- é seguro e imune a esse problema.
--
-- ANTES DE EXECUTAR
-- Troque as DUAS ocorrências de <SUA_SENHA_FORTE> pela MESMA
-- senha que você vai colocar em APP_KEY nos Secrets do app.
-- Use uma senha sem espaços, sem aspas e sem # (ex.: MinhaChave2026Forte).
-- ============================================================


-- 1) Remove as políticas antigas (se existirem)
drop policy if exists "registros_inserir_com_cracha"   on public.registros;
drop policy if exists "registros_consultar_com_cracha" on public.registros;


-- 2) Garante que o RLS está ligado
alter table public.registros enable row level security;


-- 3) POLÍTICA DE GRAVAÇÃO (INSERT)
--    Só grava quem enviar o cabeçalho x-app-key com a senha exata.
create policy "registros_inserir_com_cracha"
    on public.registros
    for insert
    to anon
    with check (
        coalesce(
            current_setting('request.headers', true)::json ->> 'x-app-key',
            ''
        ) = '<SUA_SENHA_FORTE>'
    );


-- 4) POLÍTICA DE CONSULTA (SELECT)
--    Só lê quem enviar o mesmo cabeçalho. Sem ele, a consulta
--    devolve zero linhas (não dá erro, apenas não mostra nada).
create policy "registros_consultar_com_cracha"
    on public.registros
    for select
    to anon
    using (
        coalesce(
            current_setting('request.headers', true)::json ->> 'x-app-key',
            ''
        ) = '<SUA_SENHA_FORTE>'
    );


-- 5) CONTINUA PROIBIDO EDITAR E EXCLUIR (v1)
--    Não crie políticas de UPDATE ou DELETE. Sem política,
--    a operação é negada automaticamente.


-- ============================================================
-- CONFERÊNCIA (opcional)
-- Mostra as políticas que ficaram ativas na tabela:
-- ============================================================
select policyname, cmd, qual, with_check
from pg_policies
where schemaname = 'public' and tablename = 'registros'
order by policyname;
