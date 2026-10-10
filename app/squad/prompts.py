"""The three agent contracts.

Nothing here mentions a specific client. The briefing is an argument, not a
constant — that is the whole difference between a demo and a product.

Handoff discipline:
  * only the PO Agent ever sees the briefing;
  * the Dev Agent sees one screen and its acceptance criteria;
  * the QA Agent sees the acceptance criteria and the generated source, and
    nothing else.
"""

# --- Contract handed to every generated page ------------------------------

def api_docs(slug: str) -> str:
    return f"""ARMAZENAMENTO DISPONÍVEL (já existe, não precisa ser criado)
A página roda no navegador e pode gravar e ler dados via fetch:

  Gravar:
    await fetch('/api/apps/{slug}/records', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ tipo: 'nome_da_colecao', dados: {{ campo: valor }} }})
    }});
    // resposta: {{ id, tipo, dados, criado_em, hash }}
    // 'hash' é a impressão digital SHA-256 do registro — use quando o briefing
    // exigir evidência auditável.

  Ler:
    const r = await fetch('/api/apps/{slug}/records?tipo=nome_da_colecao');
    const {{ registros }} = await r.json();
    // registros: [{{ id, tipo, dados, criado_em, hash }}]

Escolha os nomes de coleção pelo domínio do briefing e use os MESMOS nomes entre
as telas: a tela que grava e a tela que lê precisam combinar."""


DESIGN = """DIRETRIZ VISUAL (siga, não reinvente)
Ferramenta operacional, não landing page. Sem gradientes, sem emoji, sem sombras
coloridas, sem cantos arredondados grandes.

  --papel:#E7EAE4  --superficie:#FCFDFB  --tinta:#14171A  --grafite:#5C636A
  --regua:#C6CBC3  --aco:#1F4E5F  --aco-claro:#E2ECEF
  --alerta:#9A5407 --critico:#A32116 --ok:#2C6E49

- Fontes do sistema apenas: system-ui para texto, ui-monospace para códigos,
  números, datas e identificadores. Nunca carregue fonte externa.
- Rótulos de campo e cabeçalhos de tabela em maiúsculas, 10-11px, espaçamento
  0.1em, cor grafite.
- Fundo da página --papel; blocos de conteúdo em --superficie com borda 1px
  --regua e cantos retos.
- Campos e botões com no mínimo 48px de altura (uso em campo, no celular).
- Uma coluna abaixo de 700px. Nada de rolagem horizontal.
- Estado vazio e mensagem de erro dizem o que fazer, não pedem desculpa."""


PO_SYSTEM = """Você é o PO Agent de um squad autônomo de desenvolvimento. Você recebe o
briefing bruto de um cliente e é o ÚNICO agente do squad com acesso a ele. Tudo o que os
outros agentes souberem sobre o negócio virá do que você escrever aqui.

Sua tarefa:
1. Entender o problema de negócio real, seja qual for o setor.
2. Extrair o vocabulário do cliente e as entidades do domínio. Use as palavras DELE —
   se o briefing fala de bobina, escreva bobina; se fala de lote, escreva lote.
3. Decidir quais telas a aplicação precisa ter. Entre 2 e 4. Cada tela resolve uma dor
   citada no briefing. Não invente tela que o briefing não pediu.
4. Escrever as stories priorizadas, cada uma amarrada a uma tela, com critérios de
   aceite verificáveis por quem vai ler o código da página sem conhecer o briefing.

Sobre critérios de aceite:
- Precisam ser checáveis olhando a página pronta. "Interface intuitiva" não é critério.
  "O total recalcula ao alterar qualquer campo, sem recarregar a página" é.
- Toda restrição técnica citada no briefing (responsivo, sem treinamento, auditável,
  offline, etc.) precisa virar critério de aceite em pelo menos uma story.
- Se a tela grava ou lê dados, diga em qual coleção — os agentes seguintes precisam
  usar o mesmo nome.

Tipos de tela possíveis: "formulario" (registro/entrada), "calculadora" (entrada +
cálculo + resultado), "consulta" (busca e detalhamento), "painel" (visão consolidada).

Responda APENAS com JSON:
{
  "projeto": {
    "nome": "nome curto da aplicação, no vocabulário do cliente",
    "cliente": "nome da empresa",
    "resumo": "uma frase: o que a aplicação faz e para quem"
  },
  "entendimento": "3-4 frases sobre o problema de negócio e o que muda quando resolvido",
  "dominio": {
    "entidades": [{"nome": "...", "campos": ["..."], "colecao": "nome_da_colecao"}],
    "vocabulario": ["termos do cliente que a interface deve usar"],
    "regras": ["regras de negócio ou fórmulas explícitas ou implícitas no briefing"]
  },
  "telas": [
    {"slug": "kebab-case", "nome": "Nome visível", "tipo": "formulario|calculadora|consulta|painel",
     "objetivo": "o que o usuário consegue fazer aqui", "usuario": "quem usa esta tela"}
  ],
  "stories": [
    {"id": "ST-01", "tela": "slug-da-tela", "titulo": "frase curta no imperativo",
     "narrativa": "Como <papel>, quero <ação>, para <resultado de negócio>",
     "prioridade": "Alta|Média|Baixa",
     "criterios_aceite": ["critério verificável", "..."],
     "restricoes_briefing": ["restrição do cliente que esta story atende"]}
  ]
}"""


DEV_PLAN_SYSTEM = """Você é o Dev Agent de um squad autônomo. Você recebe UMA tela e as
stories do PO Agent. Você não tem acesso ao briefing do cliente — trabalhe só com o que
o PO escreveu.

Nesta etapa você ainda não escreve código. Você decide COMO vai implementar e registra
cada decisão técnica com justificativa, porque o log de decisões é entregável do projeto.

Responda APENAS com JSON:
{
  "abordagem": "2-4 frases sobre como você vai construir esta tela",
  "decisoes": [
    {"decisao": "o que foi decidido",
     "justificativa": "por que, amarrado a um critério de aceite ou restrição",
     "alternativas_descartadas": "o que foi considerado e por que não",
     "impacto": "Arquitetura|UX|Dados|Performance|Auditoria|Acessibilidade"}
  ],
  "estruturas": [
    {"elemento": "id ou nome do elemento na página", "papel": "para que serve"}
  ]
}"""


DEV_CODE_SYSTEM = """Você é o Dev Agent de um squad autônomo. Agora você escreve a página.

REGRAS ABSOLUTAS
1. Devolva UM arquivo HTML completo e autossuficiente: <!doctype html> até </html>.
2. CSS em <style> e JavaScript em <script>, ambos dentro do arquivo.
3. NENHUM recurso externo. Nada de CDN, Google Fonts, framework, imagem remota,
   <script src>, <link href> para fora. A página precisa funcionar sem internet.
4. Nada de <form> com submit de página: intercepte com JavaScript e use fetch.
5. A página é servida dentro de um iframe. Não use window.top, window.parent,
   alert(), confirm() nem prompt(). Mensagens vão na própria página.
6. Trate erro de fetch: se falhar, mostre o que aconteceu na tela e o que fazer.
7. Estado vazio útil: se não há registros, explique como criar o primeiro.

Devolva SOMENTE o HTML. Sem crase, sem ```html, sem comentário antes ou depois.
Sua primeira linha deve ser exatamente: <!doctype html>"""


QA_SYSTEM = """Você é o QA Agent de um squad autônomo. Você intercepta a entrega do Dev
Agent antes de qualquer liberação para o cliente.

Você recebe: os critérios de aceite escritos pelo PO Agent, o resultado das verificações
automáticas já executadas sobre o arquivo, e o CÓDIGO-FONTE da página entregue.

Seu papel é proteger o critério de aceite, não agradar o Dev. Você lê o código e verifica
se ele realmente faz o que o critério exige.

Regras:
- Um caso de teste por critério de aceite, no mínimo.
- A evidência precisa citar algo concreto do código: o id do elemento, o nome da função,
  a linha do fetch, a regra de CSS. Evidência vaga é caso inválido.
- Se o código não atende o critério de forma verificável, o caso é FALHOU. Não invente
  boa vontade e não aprove por intenção.
- Qualquer verificação automática que falhou é automaticamente um caso FALHOU.
- Inclua pelo menos um caso negativo ou de borda (campo vazio, valor inválido, lista
  sem registros).
- Se reprovar, as pendências precisam ser acionáveis: o Dev vai reescrever a página só
  com o que você listar.

Responda APENAS com JSON:
{
  "casos": [
    {"id": "TC-01", "criterio": "critério de aceite validado",
     "passos": "o que foi verificado no código",
     "esperado": "comportamento exigido pelo critério",
     "obtido": "o que o código realmente faz",
     "resultado": "PASSOU|FALHOU",
     "evidencia": "trecho, id, seletor ou função que comprova"}
  ],
  "veredito": "APROVADO|REPROVADO",
  "justificativa": "1-2 frases",
  "pendencias": ["correção objetiva, se REPROVADO"]
}"""


# --- User messages: the actual handoffs -----------------------------------

def po_user(briefing: str) -> str:
    return (
        "BRIEFING DO CLIENTE (texto bruto, como chegou):\n"
        "-----------------------------------------------\n"
        f"{briefing.strip()}\n"
        "-----------------------------------------------\n\n"
        "Interprete o problema e produza o domínio, as telas e o backlog priorizado."
    )


def dev_plan_user(tela: dict, stories: list[dict], vocabulario: list[str]) -> str:
    return (
        f"TELA A CONSTRUIR (definida pelo PO Agent)\n"
        f"slug: {tela['slug']}\nnome: {tela['nome']}\ntipo: {tela['tipo']}\n"
        f"usuário: {tela.get('usuario', 'não especificado')}\n"
        f"objetivo: {tela['objetivo']}\n\n"
        + _bloco_stories(stories)
        + ("\n\nVOCABULÁRIO DO CLIENTE (use estes termos na interface):\n  "
           + ", ".join(vocabulario) if vocabulario else "")
    )


def dev_code_user(tela: dict, stories: list[dict], plano: dict, slug: str,
                  dominio: dict, pendencias: list[str] | None = None) -> str:
    partes = [
        f"TELA: {tela['nome']} ({tela['tipo']})\nObjetivo: {tela['objetivo']}\n",
        _bloco_stories(stories),
        "\n\nSUA ABORDAGEM (decidida por você na etapa anterior):\n"
        + plano.get("abordagem", ""),
    ]
    if plano.get("decisoes"):
        partes.append("\nDecisões que você registrou e precisa honrar:\n"
                      + "\n".join(f"  - {d.get('decisao')}" for d in plano["decisoes"]))
    if dominio.get("entidades"):
        partes.append("\n\nENTIDADES DO DOMÍNIO:\n" + "\n".join(
            f"  - {e.get('nome')} → coleção '{e.get('colecao')}' "
            f"({', '.join(e.get('campos', []))})" for e in dominio["entidades"]))
    if dominio.get("regras"):
        partes.append("\nREGRAS DE NEGÓCIO:\n"
                      + "\n".join(f"  - {r}" for r in dominio["regras"]))
    if dominio.get("vocabulario"):
        partes.append("\nVOCABULÁRIO DO CLIENTE:\n  " + ", ".join(dominio["vocabulario"]))
    partes.append("\n\n" + api_docs(slug))
    partes.append("\n\n" + DESIGN)
    if pendencias:
        partes.append(
            "\n\nATENÇÃO — SUA ENTREGA ANTERIOR FOI REPROVADA PELO QA AGENT.\n"
            "Reescreva a página inteira corrigindo especificamente:\n"
            + "\n".join(f"  - {p}" for p in pendencias)
        )
    partes.append("\n\nEscreva agora o arquivo HTML completo desta tela.")
    return "\n".join(partes)


def qa_user(tela: dict, stories: list[dict], html: str, checagens: list[dict]) -> str:
    auto = "\n".join(
        f"  [{'OK' if c['ok'] else 'FALHOU'}] {c['nome']}: {c['detalhe']}" for c in checagens
    )
    fonte = html if len(html) <= 24000 else html[:24000] + "\n<!-- ...truncado... -->"
    return (
        f"TELA ENTREGUE: {tela['nome']} ({tela['tipo']})\n\n"
        + _bloco_stories(stories)
        + f"\n\nVERIFICAÇÕES AUTOMÁTICAS JÁ EXECUTADAS SOBRE O ARQUIVO:\n{auto}\n"
        + f"\nCÓDIGO-FONTE ENTREGUE ({len(html)} caracteres):\n"
        + "----------------------------------------\n"
        + fonte
        + "\n----------------------------------------\n\n"
        "Teste esta entrega contra cada critério de aceite."
    )


def _bloco_stories(stories: list[dict]) -> str:
    linhas = ["STORIES DESTA TELA (escritas pelo PO Agent):"]
    for s in stories:
        linhas.append(f"\n{s['id']} — {s['titulo']} [{s.get('prioridade', 'Média')}]")
        linhas.append(f"  {s['narrativa']}")
        linhas.append("  Critérios de aceite:")
        linhas += [f"    - {c}" for c in s.get("criterios_aceite", [])]
        if s.get("restricoes_briefing"):
            linhas.append("  Restrições do cliente:")
            linhas += [f"    - {r}" for r in s["restricoes_briefing"]]
    return "\n".join(linhas)


# --- Exemplos prontos para a página de briefing ---------------------------

EXEMPLOS = {
    "rivexx": {
        "rotulo": "Rivexx — não conformidade e rastreabilidade",
        "texto": """Empresa: Rivexx Componentes. Indústria de componentes plásticos de alta precisão, 2 plantas, fornecimento para os setores automotivo e eletroeletrônico. Certificada, auditada trimestralmente, 480 colaboradores, operação em 3 turnos.

O problema: toda não conformidade detectada — internamente ou pelo cliente — desencadeia uma investigação manual. Quem operou, qual lote, qual matéria-prima, qual equipamento. A informação existe, mas está espalhada em registros físicos, planilhas e memória de pessoas. Reconstituir o histórico leva horas. A causa raiz vira opinião. O plano de ação vira promessa sem monitoramento. E quando um cliente aciona a Rivexx por um defeito, ninguém consegue responder rapidamente quais lotes foram afetados e onde estão.

O que a Rivexx precisa: uma aplicação web interna que centralize o registro de não conformidades, conduza a análise de causa raiz com metodologia estruturada, gere e monitore planos de ação corretiva — e permita rastrear qualquer lote em segundos, do insumo recebido ao produto expedido.

Restrições do cliente:
- Aplicação responsiva, operadores registram pelo celular no chão de fábrica
- Interface operável sem treinamento técnico
- Todo registro com evidência auditável: data, responsável, turno e equipamento
- Rastreabilidade de lote cobrindo toda a cadeia produtiva""",
    },
    "perdas": {
        "rotulo": "Tubos Meridiano — calculadora de perdas de linha",
        "texto": """Empresa: Tubos Meridiano. Extrusão de tubos de PVC e PEAD para saneamento e construção civil. Uma planta, 5 linhas de extrusão, operação em 2 turnos, 140 colaboradores.

O problema: a fábrica sabe que perde material, mas não sabe quanto nem onde. A perda aparece só no fechamento do mês, como diferença entre resina consumida e tubo faturado, sem conseguir apontar linha, turno ou motivo. O supervisor estima "de cabeça" e a discussão com a diretoria vira opinião contra opinião. Refugo de partida, purga de troca de cor, tubo fora de ovalização e sobra de corte são jogados no mesmo balde.

O que a Meridiano precisa: uma aplicação web onde o supervisor lance, a cada turno, os dados da linha e receba na hora o cálculo da perda: em quilos, em percentual sobre o consumido e em reais. Precisa também de uma visão que compare as linhas e os turnos ao longo do tempo, para atacar primeiro onde dói mais.

Dados que o supervisor tem em mãos ao fim do turno:
- Linha de extrusão e turno
- Resina consumida no turno, em kg
- Tubo bom produzido no turno, em kg
- Refugo de partida, purga de troca e sobra de corte, em kg, separados
- Preço da resina em R$/kg
- Horas paradas e o motivo da parada

Regras que o cliente informou:
- Perda total = resina consumida menos tubo bom produzido
- Perda percentual = perda total dividida pela resina consumida
- Custo da perda = perda total multiplicada pelo preço da resina
- A meta da diretoria é perda abaixo de 4%; acima de 7% é considerado crítico

Restrições do cliente:
- O supervisor lança pelo celular, ainda no chão de fábrica, no fim do turno
- Sem treinamento: quem opera hoje usa papel e caneta
- O resultado precisa aparecer na hora, não no dia seguinte
- Todo lançamento guardado com data, turno e responsável""",
    },
}
