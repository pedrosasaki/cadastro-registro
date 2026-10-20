-- ============================================================
-- 03 — SOLUÇÃO DEFINITIVA: funções seguras no banco
-- ============================================================
-- Execute este script no SQL Editor do Supabase (clique em Run).
--
-- POR QUE ESTE SCRIPT EXISTE
-- As duas tentativas anteriores dependiam do cabeçalho
-- "x-app-key" chegar até a checagem de segurança. Testei
-- diretamente na API do seu projeto e o banco NÃO enxerga esse
-- cabeçalho: a gravação é recusada mesmo com a senha correta.
--
-- A solução abaixo NÃO usa cabeçalho. A senha vai como
-- parâmetro para uma função do banco, que confere a senha e
-- grava/consulta em nome do aplicativo.
--
-- Vantagem extra: a tabela fica TOTALMENTE fechada para acesso
-- direto. Ninguém consegue ler nem gravar indo direto na API —
-- só através das funções, e só com a senha certa.
--
-- ANTES DE EXECUTAR
-- Troque APENAS a ocorrência abaixo (na gravação da app_config)
-- pela mesma senha do APP_KEY
-- no Streamlit. Sem espaços, sem aspas, sem #.
-- ============================================================


-- ------------------------------------------------------------
-- 1) TABELA QUE GUARDA A SENHA DO APLICATIVO
-- ------------------------------------------------------------
-- Fica com RLS ligado e SEM nenhuma política: nem leitura nem
-- gravação direta. Só as funções abaixo (que rodam como dono)
-- conseguem consultá-la.
create table if not exists public.app_config (
    chave text primary key,
    valor text not null
);

alter table public.app_config enable row level security;

-- Guarda a senha (se já existir, atualiza)
-- IMPORTANTE: este é o ÚNICO lugar do script onde você define a senha.
insert into public.app_config (chave, valor)
values ('app_key', '<SUA_SENHA_FORTE>')
on conflict (chave) do update set valor = excluded.valor;

-- Conferência segura: mostra só o tamanho da senha gravada.
-- Não exibe o valor da senha.
select
    chave,
    length(valor) as tamanho_da_senha
from public.app_config
where chave = 'app_key';


-- ------------------------------------------------------------
-- 2) TABELA DE REGISTROS: FECHADA PARA ACESSO DIRETO
-- ------------------------------------------------------------
alter table public.registros enable row level security;

-- Remove as políticas antigas (baseadas em cabeçalho)
drop policy if exists "registros_inserir_com_cracha"   on public.registros;
drop policy if exists "registros_consultar_com_cracha" on public.registros;

-- Nenhuma política criada de propósito:
--   sem política = acesso direto negado para o papel anon.
-- O acesso passa a ser SÓ pelas funções abaixo.


-- ------------------------------------------------------------
-- 3) CONFERÊNCIA DA SENHA (uso interno)
-- ------------------------------------------------------------
create or replace function public._checar_chave(p_app_key text)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    v_chave_esperada text;
begin
    -- Se a linha não existir em app_config, tratamos como senha vazia.
    -- Isso evita o "buraco" de segurança do NULL (que poderia aprovar indevidamente).
    select coalesce(valor, '')
      into v_chave_esperada
      from public.app_config
     where chave = 'app_key';

    v_chave_esperada := coalesce(v_chave_esperada, '');

    -- Regras de bloqueio (qualquer uma delas reprova):
    -- 1) senha enviada vazia/nula
    -- 2) senha armazenada vazia/nula (configuração inválida)
    -- 3) senha enviada diferente da armazenada
    if coalesce(p_app_key, '') = ''
       or v_chave_esperada = ''
       or p_app_key <> v_chave_esperada
    then
        raise exception 'Chave de acesso invalida'
            using errcode = '42501';
    end if;
end;
$$;

revoke all on function public._checar_chave(text) from public, anon, authenticated;


-- ------------------------------------------------------------
-- 4) GRAVAR UM REGISTRO
-- ------------------------------------------------------------
create or replace function public.inserir_registro(
    p_app_key      text,
    p_tipo         text,
    p_periodo      date,
    p_posicao      integer,
    p_empresa      text,
    p_quantidade   integer,
    p_valor        numeric,
    p_participacao integer
)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
    v_id bigint;
begin
    perform public._checar_chave(p_app_key);

    insert into public.registros
        (tipo, periodo, posicao, empresa, quantidade, valor, participacao)
    values
        (p_tipo, p_periodo, p_posicao, p_empresa, p_quantidade, p_valor, p_participacao)
    returning id into v_id;

    return v_id;
end;
$$;

revoke all on function public.inserir_registro(text, text, date, integer, text, integer, numeric, integer) from public;
grant execute on function public.inserir_registro(text, text, date, integer, text, integer, numeric, integer) to anon;


-- ------------------------------------------------------------
-- 5) GRAVAR VÁRIOS REGISTROS (colagem do Excel)
-- ------------------------------------------------------------
-- Recebe uma lista em JSON. Devolve os ids gravados.
create or replace function public.inserir_varios(
    p_app_key   text,
    p_registros jsonb
)
returns setof bigint
language plpgsql
security definer
set search_path = public
as $$
declare
    v_id bigint;
begin
    perform public._checar_chave(p_app_key);

    if p_registros is null or jsonb_typeof(p_registros) <> 'array' then
        raise exception 'A lista de registros deve ser um array JSON'
            using errcode = '22023';
    end if;

    for v_id in
        insert into public.registros
            (tipo, periodo, posicao, empresa, quantidade, valor, participacao)
        select
            (item ->> 'tipo'),
            (item ->> 'periodo')::date,
            (item ->> 'posicao')::integer,
            (item ->> 'empresa'),
            (item ->> 'quantidade')::integer,
            (item ->> 'valor')::numeric,
            (item ->> 'participacao')::integer
        from jsonb_array_elements(p_registros) as item
        returning id
    loop
        return next v_id;
    end loop;

    return;
end;
$$;

revoke all on function public.inserir_varios(text, jsonb) from public;
grant execute on function public.inserir_varios(text, jsonb) to anon;


-- ------------------------------------------------------------
-- 6) CONSULTAR (com paginação e ordenação)
-- ------------------------------------------------------------
create or replace function public.consultar_registros(
    p_app_key      text,
    p_pagina       integer default 1,
    p_por_pagina   integer default 25,
    p_ordenar_por  text    default 'id',
    p_decrescente  boolean default true
)
returns setof public.registros
language plpgsql
security definer
set search_path = public
as $$
declare
    v_coluna text;
    v_limite integer;
    v_salto  integer;
begin
    perform public._checar_chave(p_app_key);

    v_coluna := case
        when p_ordenar_por in ('id', 'periodo', 'tipo', 'empresa', 'valor')
            then p_ordenar_por
        else 'id'
    end;

    v_limite := greatest(1, least(coalesce(p_por_pagina, 25), 200));
    v_salto  := (greatest(1, coalesce(p_pagina, 1)) - 1) * v_limite;

    return query execute format(
        'select * from public.registros order by %I %s limit %s offset %s',
        v_coluna,
        case when p_decrescente then 'desc' else 'asc' end,
        v_limite,
        v_salto
    );
end;
$$;

revoke all on function public.consultar_registros(text, integer, integer, text, boolean) from public;
grant execute on function public.consultar_registros(text, integer, integer, text, boolean) to anon;


-- ------------------------------------------------------------
-- 7) CONTAR REGISTROS
-- ------------------------------------------------------------
create or replace function public.contar_registros(p_app_key text)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
    v_total bigint;
begin
    perform public._checar_chave(p_app_key);
    select count(*) into v_total from public.registros;
    return v_total;
end;
$$;

revoke all on function public.contar_registros(text) from public;
grant execute on function public.contar_registros(text) to anon;


-- ============================================================
-- 8) TESTE AUTOMÁTICO (sem repetir senha no script)
-- ============================================================
-- Aqui a senha é lida da tabela public.app_config.
-- Se aparecer um número em id_gravado, a gravação funcionou.
select public.inserir_registro(
    (select valor from public.app_config where chave = 'app_key'),
    'TESTE-SQL',
    current_date,
    null,
    'TESTE',
    0,
    0,
    null
) as id_gravado;

-- Confere o total (deve incluir o registro de teste acima)
select public.contar_registros(
    (select valor from public.app_config where chave = 'app_key')
) as total_de_registros;


-- ============================================================
-- 9) CORRIGIR A SENHA SEM RODAR TUDO DE NOVO
-- ============================================================
-- Use somente este bloco quando o script já foi aplicado e você
-- só precisa ajustar a senha que ficou diferente do APP_KEY.
--
-- Passo 1) Atualize a senha da app_config (troque o texto entre aspas):
-- update public.app_config
--    set valor = 'COLOQUE_A_SENHA_CORRETA_AQUI'
--  where chave = 'app_key';
--
-- Passo 2) Teste imediatamente (sem repetir senha no teste):
-- select public.contar_registros(
--     (select valor from public.app_config where chave = 'app_key')
-- ) as total_apos_correcao;


-- ============================================================
-- 10) LIMPEZA DOS REGISTROS DE TESTE (opcional)
-- ============================================================
-- Descomente as linhas abaixo (tire o "--") e rode para apagar
-- os registros criados pelos testes:
--
-- delete from public.registros where tipo in ('TESTE-SQL', 'TESTE-DIAGNOSTICO', 'TESTE-AGENTE');
