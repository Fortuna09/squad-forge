"""The squad.

    START -> po -> dispatch -> dev -> qa -+-> dispatch   (aprovado / esgotou retrabalho)
                    |                     +-> dev        (reprovado)
                    +-> fechamento -> END

`po` reads a briefing it has never seen before. `dev` writes an actual HTML file
to disk. `qa` reads that file back and tests it. Nothing about the client is
hardcoded anywhere below this line.
"""
import json
import threading
import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app import db, llm
from app.squad import bus, gate, prompts

MAX_RETRABALHO = 2


class SquadState(TypedDict, total=False):
    run_id: str
    projeto_slug: str
    briefing: str
    dominio: dict
    fila: list
    tela_atual: dict
    stories_tela: list
    plano: dict
    html: str
    checagens: list
    qa_output: dict
    retrabalho: int
    pendencias: list
    resultados: list


# --- PO -------------------------------------------------------------------

def po_node(state: SquadState) -> SquadState:
    run_id, slug = state["run_id"], state["projeto_slug"]
    bus.emit(run_id, "po", "recebimento", "Briefing do cliente recebido",
             "Único agente do squad com acesso ao texto do cliente. "
             f"{len(state['briefing'])} caracteres para interpretar.")

    data, usage = llm.call_json(prompts.PO_SYSTEM, prompts.po_user(state["briefing"]))

    proj = data.get("projeto", {})
    dominio = data.get("dominio", {})
    telas = data.get("telas", [])
    stories = data.get("stories", [])

    db.execute(
        "UPDATE projetos SET nome = ?, cliente = ?, resumo = ?, dominio_json = ? WHERE slug = ?",
        (proj.get("nome") or "Aplicação", proj.get("cliente") or "Cliente",
         proj.get("resumo") or "", json.dumps(dominio, ensure_ascii=False), slug),
    )

    bus.emit(run_id, "po", "analise", f"Entendimento — {proj.get('cliente', '—')}",
             data.get("entendimento", ""), usage=usage,
             payload={"vocabulario": dominio.get("vocabulario", [])})

    if dominio.get("entidades"):
        bus.emit(run_id, "po", "dominio", f"Modelo de domínio ({len(dominio['entidades'])} entidades)",
                 "Vocabulário e entidades extraídos do briefing, nas palavras do cliente.",
                 payload={"entidades": [
                     f"{e.get('nome')} → coleção '{e.get('colecao')}' "
                     f"({', '.join(e.get('campos', []))})" for e in dominio["entidades"]],
                     "regras": dominio.get("regras", [])})

    for i, t in enumerate(telas):
        t["slug"] = db.slugify(t.get("slug") or t.get("nome"), f"tela-{i+1}")
        db.execute(
            "INSERT INTO telas (projeto_slug, run_id, slug, nome, tipo, objetivo, status, ordem) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (slug, run_id, t["slug"], t.get("nome", t["slug"]), t.get("tipo", "formulario"),
             t.get("objetivo", ""), "Planejada", i),
        )
        bus.emit(run_id, "po", "tela", f"Tela definida: {t.get('nome')} [{t.get('tipo')}]",
                 t.get("objetivo", ""))

    for s in stories:
        s["tela"] = db.slugify(s.get("tela", ""), "")
        db.execute(
            "INSERT INTO stories (run_id, projeto_slug, story_id, tela, titulo, narrativa, "
            "prioridade, criterios_json, status) VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, slug, s.get("id", ""), s.get("tela", ""), s.get("titulo", ""),
             s.get("narrativa", ""), s.get("prioridade", "Média"),
             json.dumps(s.get("criterios_aceite", []), ensure_ascii=False), "Pendente"),
        )
        bus.emit(run_id, "po", "story", f"{s.get('id')} — {s.get('titulo')}",
                 s.get("narrativa", ""),
                 payload={"criterios_aceite": s.get("criterios_aceite", []),
                          "tela": s.get("tela"), "prioridade": s.get("prioridade")})

    bus.emit(run_id, "po", "handoff",
             f"Backlog entregue ao Dev Agent — {len(telas)} telas, {len(stories)} stories",
             "A partir daqui o briefing não é mais compartilhado. O Dev recebe apenas "
             "a tela e os critérios de aceite.")

    fila = [{"tela": t, "stories": [s for s in stories if s.get("tela") == t["slug"]]}
            for t in telas]
    return {"dominio": dominio, "fila": fila, "resultados": []}


# --- Dispatch -------------------------------------------------------------

def dispatch_node(state: SquadState) -> SquadState:
    fila = state.get("fila", [])
    if not fila:
        return {"tela_atual": None}
    item = fila[0]
    bus.emit(state["run_id"], "sistema", "dispatch",
             f"Construindo: {item['tela']['nome']}",
             f"{len(item['stories'])} story(ies) nesta tela · restam {len(fila) - 1} na fila.")
    return {"tela_atual": item["tela"], "stories_tela": item["stories"],
            "fila": fila[1:], "retrabalho": 0, "pendencias": []}


# --- Dev ------------------------------------------------------------------

def dev_node(state: SquadState) -> SquadState:
    run_id, slug = state["run_id"], state["projeto_slug"]
    tela, stories = state["tela_atual"], state.get("stories_tela") or []
    pendencias = state.get("pendencias") or []
    retrabalho = state.get("retrabalho", 0)
    tentativa = retrabalho + 1 if pendencias else retrabalho

    if pendencias:
        bus.emit(run_id, "dev", "retrabalho", f"Retrabalho #{tentativa} — {tela['nome']}",
                 "Reescrevendo a página com as pendências do QA Agent.",
                 payload={"pendencias": pendencias})
        plano = state.get("plano", {})
    else:
        bus.emit(run_id, "dev", "recebimento", f"Tela {tela['nome']} recebida do PO Agent",
                 f"{sum(len(s.get('criterios_aceite', [])) for s in stories)} critérios de "
                 "aceite para atender. Sem acesso ao briefing original.")
        plano, usage = llm.call_json(
            prompts.DEV_PLAN_SYSTEM,
            prompts.dev_plan_user(tela, stories, state["dominio"].get("vocabulario", [])),
        )
        bus.emit(run_id, "dev", "abordagem", f"Abordagem técnica — {tela['nome']}",
                 plano.get("abordagem", ""), usage=usage)
        for d in plano.get("decisoes", []):
            db.execute(
                "INSERT INTO decisoes (run_id, tela, decisao, justificativa, alternativas, "
                "impacto, ts) VALUES (?,?,?,?,?,?,?)",
                (run_id, tela["slug"], d.get("decisao", ""), d.get("justificativa", ""),
                 d.get("alternativas_descartadas", ""), d.get("impacto", ""), db.now()),
            )
            bus.emit(run_id, "dev", "decisao", d.get("decisao", ""), d.get("justificativa", ""),
                     payload={"alternativas_descartadas": d.get("alternativas_descartadas"),
                              "impacto": d.get("impacto")})

    bus.emit(run_id, "dev", "escrevendo", f"Escrevendo {tela['slug']}.html",
             "Página autossuficiente: HTML, CSS e JavaScript em um arquivo, sem dependência externa.")

    html, usage = llm.call_text(
        prompts.DEV_CODE_SYSTEM,
        prompts.dev_code_user(tela, stories, plano, slug, state["dominio"], pendencias),
    )

    destino = db.caminho_tela(slug, tela["slug"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")

    checagens = gate.verificar(html, tela, slug)
    ok, total = gate.resumo(checagens)
    truncado = usage.get("stop_reason") == "max_tokens"

    bus.emit(run_id, "dev", "codigo",
             f"{tela['slug']}.html gravado — {len(html)} caracteres",
             ("ATENÇÃO: resposta atingiu o limite de tokens e pode estar truncada. "
              if truncado else "") + f"Verificações automáticas: {ok}/{total} aprovadas.",
             usage=usage,
             payload={"verificacoes": [
                 f"{'✓' if c['ok'] else '✗'} {c['nome']}: {c['detalhe']}" for c in checagens]})

    bus.emit(run_id, "dev", "handoff", f"Entrega de {tela['nome']} enviada ao QA Agent",
             "O QA recebe o código-fonte e os critérios de aceite — nada mais.")

    return {"plano": plano, "html": html, "checagens": checagens, "retrabalho": tentativa}


# --- QA -------------------------------------------------------------------

def qa_node(state: SquadState) -> SquadState:
    run_id = state["run_id"]
    tela, stories = state["tela_atual"], state.get("stories_tela") or []
    html, checagens = state["html"], state["checagens"]

    ok, total = gate.resumo(checagens)
    bus.emit(run_id, "qa", "recebimento", f"Entrega de {tela['nome']} interceptada",
             f"Verificações automáticas: {ok}/{total}. Agora a revisão do código contra "
             "os critérios de aceite.")

    for c in checagens:
        if not c["ok"]:
            db.execute(
                "INSERT INTO testes (run_id, tela, caso_id, criterio, passos, esperado, "
                "obtido, resultado, evidencia, origem, ts) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, tela["slug"], "AUTO", c["nome"], "Verificação automática do arquivo",
                 c["nome"], c["detalhe"], "FALHOU", c["detalhe"], "automática", db.now()),
            )
            bus.emit(run_id, "qa", "teste", f"AUTO — {c['nome']}: FALHOU", c["detalhe"])

    data, usage = llm.call_json(prompts.QA_SYSTEM,
                                prompts.qa_user(tela, stories, html, checagens))
    casos = data.get("casos", [])

    for c in casos:
        db.execute(
            "INSERT INTO testes (run_id, tela, caso_id, criterio, passos, esperado, obtido, "
            "resultado, evidencia, origem, ts) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, tela["slug"], c.get("id", ""), c.get("criterio", ""), c.get("passos", ""),
             c.get("esperado", ""), c.get("obtido", ""), c.get("resultado", ""),
             c.get("evidencia", ""), "revisão", db.now()),
        )
        bus.emit(run_id, "qa", "teste", f"{c.get('id')} — {c.get('resultado')}",
                 c.get("criterio", ""), payload=c)

    veredito = data.get("veredito", "APROVADO").upper()
    if any(not c["ok"] for c in checagens):
        veredito = "REPROVADO"  # a failed machine check is not negotiable

    pendencias = list(data.get("pendencias", []))
    pendencias += [f"Corrigir: {c['nome']} — {c['detalhe']}" for c in checagens if not c["ok"]]

    bus.emit(run_id, "qa", "veredito", f"{tela['nome']}: {veredito}",
             data.get("justificativa", ""), usage=usage,
             payload={"pendencias": pendencias})

    passou = sum(1 for c in casos if c.get("resultado") == "PASSOU")
    resultado = {
        "tela": tela, "stories": stories, "plano": state.get("plano", {}),
        "qa": data, "veredito": veredito, "checagens": checagens,
        "casos_passou": passou, "casos_total": len(casos),
        "retrabalhos": state.get("retrabalho", 0),
        "tamanho": len(state.get("html") or ""),
    }
    anteriores = [r for r in state.get("resultados", [])
                  if r["tela"]["slug"] != tela["slug"]]
    return {"qa_output": data, "pendencias": pendencias,
            "resultados": anteriores + [resultado]}


# --- Fechamento -----------------------------------------------------------

def fechamento_node(state: SquadState) -> SquadState:
    run_id, slug = state["run_id"], state["projeto_slug"]
    escrever_artefatos(state)
    resultados = state.get("resultados", [])
    aprovadas = sum(1 for r in resultados if r["veredito"] == "APROVADO")
    bus.emit(run_id, "sistema", "fim",
             f"Aplicação entregue — {aprovadas}/{len(resultados)} telas aprovadas",
             "Backlog, log de decisões e relatório de QA gravados. "
             f"A aplicação do cliente está em /app/{slug}.")
    db.execute("UPDATE squad_runs SET status = ?, finalizado_em = ? WHERE run_id = ?",
               ("Concluído", db.now(), run_id))
    db.execute("UPDATE projetos SET status = ? WHERE slug = ?", ("Entregue", slug))
    return {}


# --- Routers --------------------------------------------------------------

def rota_dispatch(state: SquadState) -> str:
    return "dev" if state.get("tela_atual") else "fechamento"


def rota_qa(state: SquadState) -> str:
    tela = state["tela_atual"]
    aprovado = state["qa_output"].get("veredito", "APROVADO").upper() == "APROVADO"
    aprovado = aprovado and all(c["ok"] for c in state.get("checagens", []))
    retrabalho = state.get("retrabalho", 0)

    if aprovado:
        db.execute("UPDATE telas SET status = ?, rework = ? WHERE run_id = ? AND slug = ?",
                   ("Aprovada", retrabalho, state["run_id"], tela["slug"]))
        return "dispatch"
    if retrabalho < MAX_RETRABALHO:
        bus.emit(state["run_id"], "sistema", "loop",
                 f"QA devolveu {tela['nome']} ao Dev Agent",
                 f"Retrabalho {retrabalho + 1}/{MAX_RETRABALHO}.")
        return "dev"
    db.execute("UPDATE telas SET status = ?, rework = ? WHERE run_id = ? AND slug = ?",
               ("Bloqueada", retrabalho, state["run_id"], tela["slug"]))
    bus.emit(state["run_id"], "sistema", "bloqueio", f"{tela['nome']} bloqueada",
             f"Limite de {MAX_RETRABALHO} retrabalhos atingido. A tela vai para o cliente "
             "marcada como não liberada pelo QA.")
    return "dispatch"


def build_graph():
    g = StateGraph(SquadState)
    g.add_node("po", po_node)
    g.add_node("dispatch", dispatch_node)
    g.add_node("dev", dev_node)
    g.add_node("qa", qa_node)
    g.add_node("fechamento", fechamento_node)
    g.add_edge(START, "po")
    g.add_edge("po", "dispatch")
    g.add_conditional_edges("dispatch", rota_dispatch,
                            {"dev": "dev", "fechamento": "fechamento"})
    g.add_edge("dev", "qa")
    g.add_conditional_edges("qa", rota_qa, {"dev": "dev", "dispatch": "dispatch"})
    g.add_edge("fechamento", END)
    return g.compile()


GRAPH = build_graph()


# --- Artefatos ------------------------------------------------------------

def _dir_artefatos(slug: str):
    d = db.GERADOS / slug / "artefatos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cel(v) -> str:
    return (v or "").replace("|", "\\|").replace("\n", " ")


def escrever_artefatos(state: SquadState):
    slug = state["projeto_slug"]
    proj = db.projeto(slug) or {}
    resultados = state.get("resultados", [])
    d = _dir_artefatos(slug)

    linhas = [f"# Backlog — {proj.get('nome', slug)}",
              f"\n`run {state['run_id']}` · **PO Agent** · cliente: {proj.get('cliente','—')}\n",
              f"> {proj.get('resumo','')}\n"]
    dom = state.get("dominio", {})
    if dom.get("vocabulario"):
        linhas.append("\n**Vocabulário do cliente:** " + ", ".join(dom["vocabulario"]) + "\n")
    if dom.get("regras"):
        linhas.append("\n**Regras de negócio extraídas do briefing**\n")
        linhas += [f"- {r}" for r in dom["regras"]]
    for r in resultados:
        linhas.append(f"\n## Tela: {r['tela']['nome']} (`{r['tela']['slug']}`, {r['tela']['tipo']})")
        linhas.append(f"\n{r['tela'].get('objetivo','')}\n")
        for s in r["stories"]:
            linhas.append(f"\n### {s.get('id')} — {s.get('titulo')}")
            linhas.append(f"\n**Prioridade:** {s.get('prioridade','—')}\n")
            linhas.append(f"{s.get('narrativa','')}\n")
            linhas.append("**Critérios de aceite**\n")
            linhas += [f"- [ ] {c}" for c in s.get("criterios_aceite", [])]
            if s.get("restricoes_briefing"):
                linhas.append("\n**Restrições do briefing atendidas**\n")
                linhas += [f"- {x}" for x in s["restricoes_briefing"]]
    _escrever(d / "backlog.md", linhas)

    linhas = [f"# Log de decisões técnicas — {proj.get('nome', slug)}",
              f"\n`run {state['run_id']}` · **Dev Agent**\n"]
    for r in resultados:
        linhas.append(f"\n## {r['tela']['nome']} — `{r['tela']['slug']}.html`")
        linhas.append(f"\n{r['plano'].get('abordagem','')}\n")
        linhas.append(f"*Arquivo gerado: {r['tamanho']} caracteres · "
                      f"retrabalhos: {r['retrabalhos']}*\n")
        for dd in r["plano"].get("decisoes", []):
            linhas.append(f"\n### {dd.get('decisao','')}")
            linhas.append(f"\n- **Justificativa:** {dd.get('justificativa','')}")
            linhas.append(f"- **Alternativas descartadas:** {dd.get('alternativas_descartadas','')}")
            linhas.append(f"- **Impacto:** {dd.get('impacto','')}")
    _escrever(d / "decision_log.md", linhas)

    total = sum(r["casos_total"] for r in resultados)
    passou = sum(r["casos_passou"] for r in resultados)
    linhas = [f"# Relatório de QA — {proj.get('nome', slug)}",
              f"\n`run {state['run_id']}` · **QA Agent**\n",
              f"**Casos executados:** {total} · **Passou:** {passou} · "
              f"**Falhou:** {total - passou} · **Retrabalhos solicitados:** "
              f"{sum(r['retrabalhos'] for r in resultados)}\n"]
    for r in resultados:
        linhas.append(f"\n## {r['tela']['nome']} — {r['veredito']}")
        linhas.append(f"\n{r['qa'].get('justificativa','')}\n")
        linhas.append("\n**Verificações automáticas sobre o arquivo**\n")
        linhas.append("| Verificação | Resultado | Detalhe |")
        linhas.append("|---|---|---|")
        for c in r["checagens"]:
            linhas.append(f"| {_cel(c['nome'])} | {'PASSOU' if c['ok'] else 'FALHOU'} "
                          f"| {_cel(c['detalhe'])} |")
        linhas.append("\n**Casos de teste contra os critérios de aceite**\n")
        linhas.append("| Caso | Critério | Esperado | Obtido | Resultado | Evidência |")
        linhas.append("|---|---|---|---|---|---|")
        for c in r["qa"].get("casos", []):
            linhas.append(
                f"| {c.get('id','')} | {_cel(c.get('criterio'))} | {_cel(c.get('esperado'))} "
                f"| {_cel(c.get('obtido'))} | **{c.get('resultado','')}** "
                f"| {_cel(c.get('evidencia'))} |")
        if r["qa"].get("pendencias"):
            linhas.append("\n**Pendências**\n")
            linhas += [f"- {p}" for p in r["qa"]["pendencias"]]
    _escrever(d / "qa_report.md", linhas)


def _escrever(caminho, linhas):
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")


# --- Runner ---------------------------------------------------------------

def iniciar(briefing: str, nome_sugerido: str = "") -> str:
    slug = db.slug_livre(db.slugify(nome_sugerido or briefing[:40], "projeto"))
    run_id = f"{slug}-{uuid.uuid4().hex[:6]}"

    db.execute(
        "INSERT INTO projetos (slug, nome, cliente, resumo, briefing, run_id, status, criado_em) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (slug, nome_sugerido or "Interpretando briefing…", "—", "", briefing,
         run_id, "Em construção", db.now()),
    )
    db.execute(
        "INSERT INTO squad_runs (run_id, projeto_slug, briefing, modo, status, iniciado_em) "
        "VALUES (?,?,?,?,?,?)",
        (run_id, slug, briefing, llm.MODE, "Executando", db.now()),
    )
    bus.emit(run_id, "sistema", "inicio", "Squad acionado",
             f"Modo: {llm.MODE} · modelo: {llm.MODEL}. O time humano entrega o briefing e sai.")

    def _run():
        try:
            GRAPH.invoke(
                {"run_id": run_id, "projeto_slug": slug, "briefing": briefing, "retrabalho": 0},
                config={"recursion_limit": 120},
            )
        except Exception as exc:  # noqa: BLE001
            bus.emit(run_id, "sistema", "erro", "Execução interrompida", str(exc))
            db.execute("UPDATE squad_runs SET status = ?, finalizado_em = ? WHERE run_id = ?",
                       ("Falhou", db.now(), run_id))
            db.execute("UPDATE projetos SET status = ? WHERE slug = ?", ("Falhou", slug))

    threading.Thread(target=_run, daemon=True).start()
    return run_id
