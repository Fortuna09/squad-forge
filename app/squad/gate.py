"""Automated checks run against the generated file before the QA Agent sees it.

These are real assertions on the artefact, executed in Python. They exist so the
QA Agent's verdict is not the only thing standing between a hallucinated page and
the client — and so "REPROVADO" can be triggered by a fact, not only by an opinion.
"""
import re
from html.parser import HTMLParser

EXTERNO = re.compile(r'(?:src|href)\s*=\s*["\'](?:https?:)?//', re.I)
BLOQUEIO = re.compile(r'\b(?:alert|confirm|prompt)\s*\(|window\.(?:top|parent)', re.I)
IMPORTA = re.compile(r'@import|<link[^>]+stylesheet', re.I)

PRECISA_DADOS = {"formulario", "consulta", "painel"}


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pilha, self.erros = [], []
        self.vazias = {"br", "hr", "img", "input", "meta", "link", "source", "area", "col"}

    def handle_starttag(self, tag, attrs):
        if tag not in self.vazias:
            self.pilha.append(tag)

    def handle_endtag(self, tag):
        if tag in self.vazias:
            return
        if tag in self.pilha:
            while self.pilha and self.pilha.pop() != tag:
                pass
        else:
            self.erros.append(f"</{tag}> sem abertura")


def _check(nome, ok, detalhe):
    return {"nome": nome, "ok": bool(ok), "detalhe": detalhe}


def verificar(html: str, tela: dict, slug: str) -> list[dict]:
    h = (html or "").strip()
    baixo = h.lower()
    checagens = []

    checagens.append(_check(
        "documento completo",
        baixo.startswith("<!doctype") or baixo.startswith("<html"),
        "arquivo começa com <!doctype html>" if baixo.startswith("<!doctype")
        else "arquivo não começa com <!doctype html>"))

    checagens.append(_check(
        "fechamento do html", "</html>" in baixo,
        "</html> presente" if "</html>" in baixo else "</html> ausente — arquivo truncado"))

    checagens.append(_check(
        "tamanho plausível", len(h) > 800,
        f"{len(h)} caracteres"))

    externos = EXTERNO.findall(h)
    checagens.append(_check(
        "sem recursos externos", not externos and not IMPORTA.search(h),
        "nenhum recurso remoto — a página abre sem internet" if not externos
        else f"{len(externos)} referência(s) externa(s) encontrada(s)"))

    bloq = BLOQUEIO.findall(h)
    checagens.append(_check(
        "compatível com iframe", not bloq,
        "sem alert/confirm/prompt/window.parent" if not bloq
        else f"usa {', '.join(sorted(set(b.strip() for b in bloq)))[:60]}"))

    checagens.append(_check(
        "meta viewport", 'name="viewport"' in baixo or "name='viewport'" in baixo,
        "viewport declarada" if "viewport" in baixo else "sem meta viewport — não responsivo"))

    tem_media = "@media" in baixo
    checagens.append(_check(
        "regra responsiva", tem_media,
        "possui @media query" if tem_media else "nenhuma @media query"))

    checagens.append(_check(
        "estilo embutido", "<style" in baixo, "CSS embutido no arquivo"
        if "<style" in baixo else "sem bloco <style>"))

    checagens.append(_check(
        "comportamento embutido", "<script" in baixo, "JavaScript embutido no arquivo"
        if "<script" in baixo else "sem bloco <script>"))

    tipo = (tela.get("tipo") or "").lower()
    if tipo in PRECISA_DADOS:
        rota = f"/api/apps/{slug}/records"
        checagens.append(_check(
            "integração com armazenamento", rota in h,
            f"usa {rota}" if rota in h else f"não chama {rota} — os dados não persistem"))

    if tipo in ("formulario", "calculadora"):
        campos = len(re.findall(r"<(?:input|select|textarea)\b", baixo))
        checagens.append(_check("campos de entrada", campos >= 2, f"{campos} campo(s)"))

    if tipo == "calculadora":
        checagens.append(_check(
            "cálculo no cliente",
            bool(re.search(r"addEventListener\s*\(\s*['\"](?:input|change|click)", h)),
            "recalcula por evento de interface" if re.search(
                r"addEventListener\s*\(\s*['\"](?:input|change|click)", h)
            else "nenhum listener de input/change/click"))

    p = _Parser()
    try:
        p.feed(h)
        abertas = [t for t in p.pilha if t not in ("html", "body", "head")]
        checagens.append(_check(
            "marcação balanceada", not p.erros and not abertas,
            "todas as tags fecham" if not p.erros and not abertas
            else f"{len(p.erros) + len(abertas)} problema(s) de marcação"))
    except Exception as exc:  # noqa: BLE001
        checagens.append(_check("marcação balanceada", False, f"falha ao analisar: {exc}"))

    return checagens


def resumo(checagens: list[dict]) -> tuple[int, int]:
    ok = sum(1 for c in checagens if c["ok"])
    return ok, len(checagens)
