"""Single choke point for every model call.

Everything the squad says to the model goes through here, so swapping providers
or dropping into offline mock mode is a one-line change on demo day.
"""
import json
import os
import re

from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
MODE = os.getenv("SQUAD_MODE", "live").lower()  # live | mock
MAX_TOKENS = int(os.getenv("SQUAD_MAX_TOKENS", "8000"))
MAX_TOKENS_CODIGO = int(os.getenv("SQUAD_MAX_TOKENS_CODIGO", "16000"))

_client = None


class LLMError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    # O .env.example traz "sk-ant-..." — copiado sem editar, não é uma chave.
    return "" if key.endswith("...") else key


def available() -> bool:
    return MODE == "mock" or bool(_api_key())


def _get_client():
    global _client
    if _client is None:
        import anthropic

        key = _api_key()
        if not key:
            raise LLMError(
                "ANTHROPIC_API_KEY não configurada (ou ainda é o exemplo sk-ant-...). "
                "Defina no .env ou rode com SQUAD_MODE=mock."
            )
        _client = anthropic.Anthropic(api_key=key)
    return _client


def _create(**kwargs):
    """Chama a API. O SDK já refaz sozinho 429, 5xx e falhas de rede; aqui só
    traduzimos o erro final para uma mensagem que diga o que fazer."""
    import anthropic

    client = _get_client()
    try:
        return client.messages.create(model=MODEL, **kwargs)
    except anthropic.AuthenticationError as exc:
        raise LLMError("Chave da Anthropic recusada (401). Confira ANTHROPIC_API_KEY no .env.") from exc
    except anthropic.NotFoundError as exc:
        raise LLMError(f"Modelo '{MODEL}' não encontrado (404). Confira ANTHROPIC_MODEL no .env.") from exc
    except anthropic.APIStatusError as exc:
        raise LLMError(f"A API respondeu {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError("Sem conexão com a API da Anthropic. Sem internet, use SQUAD_MODE=mock.") from exc


def _text_of(resp) -> str:
    return "".join(b.text for b in resp.content if b.type == "text")


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json|html)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json(text: str):
    text = _strip_fences(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Model prefaced the JSON with prose — grab the outermost object/array.
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError(f"Resposta não é JSON válido:\n{text[:400]}")


def _extract_html(text: str) -> str:
    """Corta qualquer comentário ou cerca de código antes de <!doctype> e depois de </html>."""
    text = _strip_fences(text)
    inicio = re.search(r"<!doctype html|<html", text, re.IGNORECASE)
    if inicio:
        text = text[inicio.start():]
    fim = text.lower().rfind("</html>")
    if fim != -1:
        text = text[: fim + len("</html>")]
    return text


def _usage(resp) -> dict:
    return {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "stop_reason": resp.stop_reason,
    }


# Os modelos atuais (Claude 4.6 em diante) recusam prefill de assistente com 400,
# então o formato é garantido pelo prompt e pelos extratores acima.

def call_json(system: str, user: str, *, retries: int = 2) -> tuple[dict, dict]:
    """Returns (parsed_json, usage)."""
    if MODE == "mock":
        from app.squad import mock

        return mock.respond(system, user), {"input_tokens": 0, "output_tokens": 0}

    last_error = None
    for _ in range(retries + 1):
        resp = _create(max_tokens=MAX_TOKENS, system=system,
                       messages=[{"role": "user", "content": user}])
        try:
            return _extract_json(_text_of(resp)), _usage(resp)
        except LLMError as exc:
            last_error = exc
            user += (
                "\n\nSua resposta anterior não era JSON válido. "
                "Responda APENAS com o objeto JSON, sem texto ao redor."
            )
    raise LLMError(f"Falha após {retries + 1} tentativas: {last_error}")


def call_text(system: str, user: str) -> tuple[str, dict]:
    """Raw text out. Used for the Dev Agent's file-writing call: asking a model to
    embed a whole HTML document inside a JSON string is the most reliable way to
    get malformed JSON, so we simply don't."""
    if MODE == "mock":
        from app.squad import mock

        return mock.respond_text(system, user), {"input_tokens": 0, "output_tokens": 0}

    resp = _create(max_tokens=MAX_TOKENS_CODIGO, system=system,
                   messages=[{"role": "user", "content": user}])
    return _extract_html(_text_of(resp)), _usage(resp)
