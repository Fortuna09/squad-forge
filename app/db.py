"""Persistence.

Two halves that must not be confused:

  * The WORKBENCH tables (projetos, telas, squad_events, stories, decisoes,
    testes) are mine. They exist so a human can audit what the squad did.
  * `app_records` belongs to the GENERATED applications. It is deliberately
    schemaless — a briefing about pipes and a briefing about injection moulding
    produce different records, and neither gets to reshape the other.
"""
import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DB_PATH = RAIZ / "forge.db"
GERADOS = RAIZ / "gerados"

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS projetos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE, nome TEXT, cliente TEXT, resumo TEXT,
    briefing TEXT, dominio_json TEXT, run_id TEXT, status TEXT, criado_em TEXT
);

CREATE TABLE IF NOT EXISTS telas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projeto_slug TEXT, run_id TEXT, slug TEXT, nome TEXT, tipo TEXT,
    objetivo TEXT, status TEXT, rework INTEGER DEFAULT 0, ordem INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, projeto_slug TEXT, story_id TEXT, tela TEXT, titulo TEXT,
    narrativa TEXT, prioridade TEXT, criterios_json TEXT, status TEXT
);

CREATE TABLE IF NOT EXISTS decisoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, tela TEXT, decisao TEXT, justificativa TEXT,
    alternativas TEXT, impacto TEXT, ts TEXT
);

CREATE TABLE IF NOT EXISTS testes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, tela TEXT, caso_id TEXT, criterio TEXT, passos TEXT,
    esperado TEXT, obtido TEXT, resultado TEXT, evidencia TEXT,
    origem TEXT, ts TEXT
);

CREATE TABLE IF NOT EXISTS squad_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE, projeto_slug TEXT, briefing TEXT, modo TEXT,
    status TEXT, iniciado_em TEXT, finalizado_em TEXT
);

CREATE TABLE IF NOT EXISTS squad_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, ts TEXT, agente TEXT, tipo TEXT, titulo TEXT, mensagem TEXT,
    payload_json TEXT, tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0
);

-- Storage for the generated applications. Schemaless on purpose.
CREATE TABLE IF NOT EXISTS app_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projeto_slug TEXT, tipo TEXT, dados_json TEXT, criado_em TEXT, hash TEXT
);
CREATE INDEX IF NOT EXISTS ix_records ON app_records (projeto_slug, tipo);
"""


def connect():
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init():
    GERADOS.mkdir(exist_ok=True)
    with connect() as con:
        con.executescript(SCHEMA)


def q(sql, args=()):
    with connect() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def execute(sql, args=()):
    with connect() as con:
        cur = con.execute(sql, args)
        con.commit()
        return cur.lastrowid


def now():
    return datetime.now().isoformat(timespec="seconds")


def hash_registro(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16].upper()


def slugify(texto: str, padrao: str = "projeto") -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (texto or "").lower().strip()).strip("-")
    return s[:48] or padrao


def slug_livre(base: str) -> str:
    slug, n = base, 2
    while q1("SELECT id FROM projetos WHERE slug = ?", (slug,)):
        slug, n = f"{base}-{n}", n + 1
    return slug


# --- Storage API used by the generated apps -------------------------------

def gravar_registro(slug: str, tipo: str, dados: dict) -> dict:
    criado = now()
    h = hash_registro({"slug": slug, "tipo": tipo, "dados": dados, "criado_em": criado})
    rid = execute(
        "INSERT INTO app_records (projeto_slug, tipo, dados_json, criado_em, hash) "
        "VALUES (?,?,?,?,?)",
        (slug, tipo, json.dumps(dados, ensure_ascii=False), criado, h),
    )
    return {"id": rid, "tipo": tipo, "dados": dados, "criado_em": criado, "hash": h}


def listar_registros(slug: str, tipo: str | None = None, limite: int = 200) -> list[dict]:
    if tipo:
        rows = q("SELECT * FROM app_records WHERE projeto_slug = ? AND tipo = ? "
                 "ORDER BY id DESC LIMIT ?", (slug, tipo, limite))
    else:
        rows = q("SELECT * FROM app_records WHERE projeto_slug = ? ORDER BY id DESC LIMIT ?",
                 (slug, limite))
    for r in rows:
        r["dados"] = json.loads(r.pop("dados_json"))
    return rows


# --- Workbench queries ----------------------------------------------------

def projeto(slug: str) -> dict | None:
    p = q1("SELECT * FROM projetos WHERE slug = ?", (slug,))
    if p and p.get("dominio_json"):
        p["dominio"] = json.loads(p["dominio_json"])
    return p


def telas_do_projeto(slug: str) -> list[dict]:
    return q("SELECT * FROM telas WHERE projeto_slug = ? ORDER BY ordem, id", (slug,))


def caminho_tela(projeto_slug: str, tela_slug: str) -> Path:
    return GERADOS / projeto_slug / f"{tela_slug}.html"
