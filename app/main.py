"""The workbench.

This server does three things and nothing else:
  1. takes a briefing and hands it to the squad;
  2. shows the squad working, and the artefacts it produced;
  3. hosts the applications the squad generated, and stores their data.

There is no client domain logic in this file. Every screen a user of a delivered
application touches lives in gerados/<projeto>/<tela>.html, written by the Dev Agent.
"""
import json
from pathlib import Path

import markdown as md
from fastapi import FastAPI, Form, Request
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse, StreamingResponse)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db, llm
from app.squad import bus, graph, prompts

BASE = Path(__file__).resolve().parent

app = FastAPI(title="Squad Forge")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

ARQUIVOS = {
    "backlog": ("backlog.md", "Backlog do PO Agent"),
    "decisoes": ("decision_log.md", "Log de decisões do Dev Agent"),
    "qa": ("qa_report.md", "Relatório de QA"),
}


@app.on_event("startup")
def _startup():
    db.init()


def ctx(request: Request, **kw):
    return {"request": request, "modo": llm.MODE, "modelo": llm.MODEL,
            "chave_ok": llm.available(), **kw}


# --- Projetos -------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def projetos(request: Request):
    lista = db.q("SELECT * FROM projetos ORDER BY id DESC")
    for p in lista:
        p["telas"] = db.telas_do_projeto(p["slug"])
        p["registros"] = db.q1(
            "SELECT COUNT(*) n FROM app_records WHERE projeto_slug = ?", (p["slug"],))["n"]
    return templates.TemplateResponse("projetos.html", ctx(request, projetos=lista))


@app.get("/briefing", response_class=HTMLResponse)
def briefing_form(request: Request, exemplo: str = ""):
    ex = prompts.EXEMPLOS.get(exemplo)
    return templates.TemplateResponse(
        "briefing.html",
        ctx(request, exemplos=prompts.EXEMPLOS, texto=ex["texto"] if ex else "",
            escolhido=exemplo),
    )


@app.post("/briefing")
def briefing_post(briefing: str = Form(...), nome: str = Form("")):
    if not briefing.strip():
        return RedirectResponse("/briefing", status_code=303)
    run_id = graph.iniciar(briefing, nome.strip())
    return RedirectResponse(f"/squad?run={run_id}", status_code=303)


@app.get("/projeto/{slug}", response_class=HTMLResponse)
def projeto(request: Request, slug: str):
    p = db.projeto(slug)
    if not p:
        return HTMLResponse("Projeto não encontrado", status_code=404)
    telas = db.telas_do_projeto(slug)
    for t in telas:
        t["existe"] = db.caminho_tela(slug, t["slug"]).exists()
        t["tamanho"] = db.caminho_tela(slug, t["slug"]).stat().st_size if t["existe"] else 0
    stories = db.q("SELECT * FROM stories WHERE projeto_slug = ?", (slug,))
    for s in stories:
        s["criterios"] = json.loads(s["criterios_json"] or "[]")
    testes = db.q("SELECT * FROM testes WHERE run_id = ?", (p["run_id"],))
    return templates.TemplateResponse(
        "projeto.html",
        ctx(request, p=p, telas=telas, stories=stories,
            registros=db.listar_registros(slug, limite=25),
            passou=sum(1 for t in testes if t["resultado"] == "PASSOU"),
            total_testes=len(testes),
            decisoes=db.q1("SELECT COUNT(*) n FROM decisoes WHERE run_id = ?",
                           (p["run_id"],))["n"]),
    )


# --- Aplicação gerada -----------------------------------------------------

@app.get("/app/{slug}", response_class=HTMLResponse)
@app.get("/app/{slug}/{tela_slug}", response_class=HTMLResponse)
def app_shell(request: Request, slug: str, tela_slug: str = ""):
    p = db.projeto(slug)
    telas = db.telas_do_projeto(slug)
    if not p or not telas:
        return HTMLResponse("Aplicação não encontrada", status_code=404)
    atual = next((t for t in telas if t["slug"] == tela_slug), telas[0])
    if not db.caminho_tela(slug, atual["slug"]).exists():
        return templates.TemplateResponse(
            "app_shell.html", ctx(request, p=p, telas=telas, atual=atual, pronta=False))
    return templates.TemplateResponse(
        "app_shell.html", ctx(request, p=p, telas=telas, atual=atual, pronta=True))


@app.get("/raw/{slug}/{tela_slug}", response_class=HTMLResponse)
def raw(slug: str, tela_slug: str):
    caminho = db.caminho_tela(slug, tela_slug)
    if not caminho.exists():
        return HTMLResponse("<p>Tela ainda não gerada.</p>", status_code=404)
    return HTMLResponse(caminho.read_text(encoding="utf-8"))


@app.get("/codigo/{slug}/{tela_slug}", response_class=PlainTextResponse)
def codigo(slug: str, tela_slug: str):
    caminho = db.caminho_tela(slug, tela_slug)
    if not caminho.exists():
        return PlainTextResponse("Tela ainda não gerada.", status_code=404)
    return PlainTextResponse(caminho.read_text(encoding="utf-8"))


# --- Storage API consumida pelas páginas geradas --------------------------

@app.get("/api/apps/{slug}/records")
def api_listar(slug: str, tipo: str = "", limite: int = 200):
    return {"registros": db.listar_registros(slug, tipo or None, limite)}


@app.post("/api/apps/{slug}/records")
async def api_gravar(slug: str, request: Request):
    try:
        corpo = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"erro": "Corpo da requisição não é JSON válido."}, status_code=400)
    tipo = (corpo.get("tipo") or "").strip()
    dados = corpo.get("dados")
    if not tipo or not isinstance(dados, dict):
        return JSONResponse(
            {"erro": "Envie {\"tipo\": \"nome_da_colecao\", \"dados\": {...}}."}, status_code=400)
    return db.gravar_registro(slug, tipo, dados)


# --- Squad console --------------------------------------------------------

@app.get("/squad", response_class=HTMLResponse)
def squad(request: Request, run: str = ""):
    runs = db.q("SELECT r.*, p.nome AS projeto_nome FROM squad_runs r "
                "LEFT JOIN projetos p ON p.slug = r.projeto_slug ORDER BY r.id DESC LIMIT 10")
    run_id = run or (runs[0]["run_id"] if runs else "")
    eventos = bus.events_after(run_id) if run_id else []
    for e in eventos:
        e["payload"] = json.loads(e["payload_json"]) if e["payload_json"] else None
    atual = db.q1("SELECT * FROM squad_runs WHERE run_id = ?", (run_id,)) if run_id else None
    p = db.projeto(atual["projeto_slug"]) if atual else None
    return templates.TemplateResponse(
        "squad.html",
        ctx(request, runs=runs, run_id=run_id, eventos=eventos, atual=atual, p=p),
    )


@app.get("/squad/stream/{run_id}")
async def squad_stream(run_id: str, desde: int = 0):
    """SSE fed by the audit table, so the trail is the source of truth."""
    import asyncio

    async def gen():
        last, vazio = desde, 0
        while vazio < 1200:
            eventos = bus.events_after(run_id, last)
            if eventos:
                vazio = 0
                for e in eventos:
                    last = e["id"]
                    e["payload"] = json.loads(e["payload_json"]) if e["payload_json"] else None
                    yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
                if eventos[-1]["tipo"] in ("fim", "erro"):
                    yield "event: fim\ndata: {}\n\n"
                    return
            else:
                vazio += 1
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- Artefatos ------------------------------------------------------------

@app.get("/artefatos/{slug}", response_class=HTMLResponse)
@app.get("/artefatos/{slug}/{qual}", response_class=HTMLResponse)
def artefatos(request: Request, slug: str, qual: str = "backlog"):
    nome, titulo = ARQUIVOS.get(qual, ARQUIVOS["backlog"])
    caminho = db.GERADOS / slug / "artefatos" / nome
    html = (md.markdown(caminho.read_text(encoding="utf-8"),
                        extensions=["tables", "fenced_code"])
            if caminho.exists() else None)
    return templates.TemplateResponse(
        "artefatos.html",
        ctx(request, conteudo=html, titulo=titulo, qual=qual, arquivos=ARQUIVOS,
            nome=nome, p=db.projeto(slug), slug=slug),
    )
