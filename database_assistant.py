"""
database_assistant.py — Database Architect & SQL Assistant (J.A.R.V.I.S.)

Suporte a conexões SQLite (stdlib), PostgreSQL (psycopg2, opcional) e MySQL
(pymysql, opcional). Oferece inspeção de schema, execução de queries somente
leitura e geração de SQL a partir de linguagem natural (via LLM local).

Comandos (integrados no chat):
  - /db-schema <spec>            — lista tabelas e colunas
  - /db-query  <spec> <sql>      — executa uma query SELECT (somente leitura)
  - /db-ask    <spec> <pergunta> — gera SQL a partir de linguagem natural

Formatos de `spec`:
  - SQLite:      caminho/para/arquivo.db
  - PostgreSQL:  postgresql://usuario:senha@host:porta/banco
  - MySQL:       mysql://usuario:senha@host:porta/banco
"""

import sqlite3
from pathlib import Path
from typing import Tuple
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _log(mensagem: str, nivel: str = "INFO") -> None:
    print(f"[DB {nivel:<5}] {mensagem}", flush=True)


def _detectar_dialeto(spec: str) -> str:
    s = (spec or "").strip()
    if s.startswith("postgresql://") or s.startswith("postgres://"):
        return "postgresql"
    if s.startswith("mysql://"):
        return "mysql"
    return "sqlite"


def _conectar(spec: str):
    """Abre uma conexão conforme o dialeto. Levanta ImportError se faltar driver."""
    dialeto = _detectar_dialeto(spec)
    if dialeto == "postgresql":
        import psycopg2  # type: ignore
        return psycopg2.connect(spec)
    if dialeto == "mysql":
        import pymysql  # type: ignore
        u = urlparse(spec)
        return pymysql.connect(
            host=u.hostname, port=u.port or 3306, user=u.username,
            password=u.password, database=u.path.lstrip("/"),
        )
    # SQLite (arquivo). Usa URI read-only para não alterar o banco.
    caminho = spec
    if caminho.startswith("sqlite:"):
        caminho = caminho[len("sqlite:"):]
    if not Path(caminho).is_file():
        raise FileNotFoundError(f"Banco SQLite não encontrado: {caminho}")
    return sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)


def _tabelas_e_colunas(spec: str) -> list[dict]:
    """Devolve [{"tabela": nome, "colunas": [col, ...]}, ...]."""
    dialeto = _detectar_dialeto(spec)
    conn = _conectar(spec)
    try:
        cur = conn.cursor()
        if dialeto == "sqlite":
            cur.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            tabelas = [r[0] for r in cur.fetchall()]
            resultado = []
            for t in tabelas:
                cur.execute(f"PRAGMA table_info('{t}')")
                colunas = [r[1] for r in cur.fetchall()]
                resultado.append({"tabela": t, "colunas": colunas})
            return resultado
        if dialeto == "postgresql":
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name"
            )
            tabelas = [r[0] for r in cur.fetchall()]
            resultado = []
            for t in tabelas:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
                    (t,),
                )
                resultado.append({"tabela": t, "colunas": [r[0] for r in cur.fetchall()]})
            return resultado
        # MySQL
        cur.execute("SHOW TABLES")
        tabelas = [r[0] for r in cur.fetchall()]
        resultado = []
        for t in tabelas:
            cur.execute(f"DESCRIBE `{t}`")
            resultado.append({"tabela": t, "colunas": [r[0] for r in cur.fetchall()]})
        return resultado
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def inspecionar_schema(spec: str) -> Tuple[bool, str]:
    """Lista tabelas e colunas de um banco de dados."""
    if not spec:
        return False, "Informe o banco. Ex.: /db-schema caminho/arquivo.db"
    try:
        dados = _tabelas_e_colunas(spec)
    except ImportError as exc:
        return False, f"Driver ausente: {exc}. Instale psycopg2-binary ou pymysql."
    except Exception as exc:
        return False, f"Falha ao inspecionar schema: {exc}"

    if not dados:
        return True, "Banco conectado, mas nenhuma tabela encontrada."

    linhas = [f"SCHEMA — {spec}", "─" * 40]
    for t in dados:
        linhas.append(f"• {t['tabela']} ({len(t['colunas'])} colunas)")
        for c in t["colunas"]:
            linhas.append(f"    - {c}")
    return True, "\n".join(linhas)


def executar_query(spec: str, sql: str, limite: int = 50) -> Tuple[bool, str]:
    """
    Executa uma query SOMENTE LEITURA e formata o resultado.

    Bloqueia comandos de escrita (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE).
    """
    if not spec:
        return False, "Informe o banco. Ex.: /db-query caminho/arquivo.db SELECT * FROM tabela"
    if not sql:
        return False, "Informe a query SQL."

    prefixo = sql.lstrip().lower()
    permitidos = ("select", "pragma", "explain", "show", "with", "describe")
    if not prefixo.startswith(permitidos):
        return False, (
            "Apenas queries de leitura são permitidas "
            "(SELECT, PRAGMA, EXPLAIN, SHOW, WITH, DESCRIBE)."
        )

    try:
        conn = _conectar(spec)
    except ImportError as exc:
        return False, f"Driver ausente: {exc}. Instale psycopg2-binary ou pymysql."
    except Exception as exc:
        return False, f"Falha ao conectar: {exc}"

    try:
        cur = conn.cursor()
        cur.execute(sql)
        if cur.description is None:
            return True, f"Query executada ({cur.rowcount} linha(s) afetada(s))."
        colunas = [d[0] for d in cur.description]
        linhas = cur.fetchmany(limite)
        cabecalho = " | ".join(colunas)
        corpo = "\n".join(" | ".join(str(v) for v in linha) for linha in linhas)
        resultado = f"RESULTADO ({len(linhas)} linha(s))\n{'─' * 40}\n{cabecalho}\n{corpo or '(sem dados)'}"
        return True, resultado
    except Exception as exc:
        return False, f"Erro na query: {exc}"
    finally:
        conn.close()


def gerar_sql_natural(pergunta: str, spec: str) -> Tuple[bool, str]:
    """
    Gera uma query SQL a partir de linguagem natural, usando o schema do banco
    como contexto e o LLM local para gerar o SQL.
    """
    if not pergunta:
        return False, "Informe a pergunta. Ex.: /db-ask banco.db 'quantos clientes ativos?'"
    if not spec:
        return False, "Informe o banco como contexto."

    # Obtém o schema (best-effort) para dar contexto ao LLM.
    contexto_schema = ""
    try:
        dados = _tabelas_e_colunas(spec)
        contexto_schema = "\n".join(
            f"- {t['tabela']}: {', '.join(t['colunas'])}" for t in dados
        )
    except Exception as exc:
        contexto_schema = f"(schema indisponível: {exc})"

    try:
        import brain
    except ImportError:
        return False, "Módulo brain indisponível para gerar SQL."

    if not hasattr(brain, "consultar_texto_livre"):
        return False, "Função consultar_texto_livre indisponível no brain."

    sql = brain.consultar_texto_livre(
        "Você é um arquiteto de banco de dados. Gere uma query SQL válida e "
        "segura (somente leitura) a partir da pergunta em linguagem natural, "
        "considerando o schema fornecido. Responda apenas a query SQL.",
        f"SCHEMA:\n{contexto_schema}\n\nPERGUNTA:\n{pergunta}",
    )

    if not sql:
        return False, "Não foi possível gerar o SQL (LLM offline?)."

    sql = sql.strip().strip("`")
    return True, (
        f"SQL GERADO\n{'─' * 40}\n{sql}\n\n"
        f"Para executar: /db-query {spec} {sql}"
    )


# ---------------------------------------------------------------------------
# Teste direto
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Database Assistant (teste)")
    print("=" * 60)
    # Cria um SQLite temporário para demonstração de schema.
    import tempfile
    import os
    tmp = os.path.join(tempfile.gettempdir(), "jarvis_demo.db")
    c = sqlite3.connect(tmp)
    c.execute("CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY, nome TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS pedidos (id INTEGER PRIMARY KEY, cliente_id INTEGER)")
    c.commit()
    c.close()
    print(inspecionar_schema(tmp)[1])
    print(executar_query(tmp, "SELECT name FROM sqlite_master WHERE type='table'")[1])
