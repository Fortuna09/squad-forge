"""Every message between agents lands in SQLite before it lands anywhere else.

The console reads back from the table, so the trail survives a crash, a restart
and a closed browser tab — which is the difference between "auditável" and "eu
juro que funcionou".
"""
import json

from app import db

AGENTES = {
    "sistema": "Sistema",
    "po": "PO Agent",
    "dev": "Dev Agent",
    "qa": "QA Agent",
}


def emit(run_id: str, agente: str, tipo: str, titulo: str, mensagem: str = "",
         payload: dict | None = None, usage: dict | None = None) -> int:
    usage = usage or {}
    event_id = db.execute(
        """INSERT INTO squad_events
           (run_id, ts, agente, tipo, titulo, mensagem, payload_json, tokens_in, tokens_out)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            run_id,
            db.now(),
            agente,
            tipo,
            titulo,
            mensagem,
            json.dumps(payload, ensure_ascii=False) if payload else None,
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
        ),
    )
    prefix = AGENTES.get(agente, agente)
    print(f"[{prefix:>9}] {tipo:<10} {titulo}")
    return event_id


def events_after(run_id: str, last_id: int = 0) -> list[dict]:
    return db.q(
        "SELECT * FROM squad_events WHERE run_id = ? AND id > ? ORDER BY id",
        (run_id, last_id),
    )


def run_status(run_id: str) -> dict | None:
    return db.q1("SELECT * FROM squad_runs WHERE run_id = ?", (run_id,))
