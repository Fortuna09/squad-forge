"""Offline mode.

SQUAD_MODE=mock runs the whole graph with no network and no key. The pages it
"generates" are assembled from templates here rather than by a model, but they
are real working pages that pass the same static gate as live output — so the
demo you rehearse is the demo you give.
"""
import html as _html
import json
import re
import threading

_lock = threading.Lock()
_qa_calls = 0

# --- PO outputs -----------------------------------------------------------

PO_PERDAS = {
    "projeto": {"nome": "Perdas de Linha", "cliente": "Tubos Meridiano",
                "resumo": "Lançamento de turno e cálculo imediato da perda de resina por linha de extrusão."},
    "entendimento": (
        "A perda só aparece no fechamento do mês, como diferença entre resina consumida e "
        "tubo faturado, sem apontar linha, turno ou motivo. Isso transforma a conversa com a "
        "diretoria em opinião contra opinião. Se o supervisor lançar os números no fim do "
        "turno e vir a perda na hora, a fábrica passa a atacar a linha certa na semana certa."
    ),
    "dominio": {
        "entidades": [
            {"nome": "Lançamento de turno", "colecao": "lancamentos",
             "campos": ["linha", "turno", "resina_kg", "tubo_bom_kg", "refugo_partida_kg",
                        "purga_kg", "sobra_corte_kg", "preco_kg", "horas_paradas", "motivo"]}
        ],
        "vocabulario": ["linha de extrusão", "turno", "resina", "tubo bom", "refugo de partida",
                        "purga de troca", "sobra de corte", "perda"],
        "regras": [
            "Perda total (kg) = resina consumida − tubo bom produzido",
            "Perda percentual = perda total ÷ resina consumida",
            "Custo da perda (R$) = perda total × preço da resina",
            "Meta: perda abaixo de 4%. Entre 4% e 7% é atenção. Acima de 7% é crítico.",
        ],
    },
    "telas": [
        {"slug": "lancamento", "nome": "Lançamento de turno", "tipo": "calculadora",
         "usuario": "Supervisor de linha",
         "objetivo": "Lançar os números do turno e ver a perda em kg, % e reais na hora"},
        {"slug": "comparativo", "nome": "Comparativo de linhas", "tipo": "painel",
         "usuario": "Diretoria e coordenação",
         "objetivo": "Comparar perda por linha e por turno para atacar onde dói mais"},
    ],
    "stories": [
        {"id": "ST-01", "tela": "lancamento", "titulo": "Calcular a perda do turno na hora do lançamento",
         "narrativa": "Como supervisor de linha, quero lançar resina, tubo bom e refugos e ver a perda imediatamente, para discutir com número em vez de estimativa.",
         "prioridade": "Alta",
         "criterios_aceite": [
             "O resultado em kg, em percentual e em reais recalcula ao alterar qualquer campo, sem recarregar a página",
             "A perda percentual é classificada como dentro da meta abaixo de 4%, atenção entre 4% e 7% e crítica acima de 7%",
             "O lançamento é gravado com linha, turno, data e responsável",
             "A tela funciona em uma coluna em tela de celular, com campos de no mínimo 48px",
         ],
         "restricoes_briefing": ["Supervisor lança pelo celular no chão de fábrica",
                                 "Resultado precisa aparecer na hora",
                                 "Todo lançamento guardado com data, turno e responsável"]},
        {"id": "ST-02", "tela": "comparativo", "titulo": "Comparar perda entre linhas e turnos",
         "narrativa": "Como diretor industrial, quero ver a perda acumulada por linha e por turno, para priorizar onde investir.",
         "prioridade": "Alta",
         "criterios_aceite": [
             "A tela lista os lançamentos gravados, do mais recente para o mais antigo",
             "A perda média por linha é apresentada de forma comparável entre linhas",
             "Quando não há lançamento, a tela explica como criar o primeiro",
         ],
         "restricoes_briefing": []},
    ],
}

PO_QUALIDADE = {
    "projeto": {"nome": "Não Conformidades e Rastreabilidade", "cliente": "Rivexx Componentes",
                "resumo": "Registro de não conformidade no chão de fábrica e rastreio da cadeia do lote."},
    "entendimento": (
        "A informação existe, mas está espalhada entre papel, planilha e memória, então "
        "reconstituir o histórico de um defeito leva horas e a causa raiz vira opinião. "
        "Centralizar o registro no ponto onde o defeito é visto e amarrar cada lote à sua "
        "cadeia transforma horas de investigação em segundos de consulta."
    ),
    "dominio": {
        "entidades": [
            {"nome": "Não conformidade", "colecao": "nao_conformidades",
             "campos": ["lote", "linha", "tipo_defeito", "severidade", "quantidade",
                        "descricao", "turno", "responsavel", "equipamento"]},
            {"nome": "Lote", "colecao": "lotes",
             "campos": ["codigo", "materia_prima", "fornecedor", "equipamento", "turno", "cliente"]},
        ],
        "vocabulario": ["não conformidade", "lote", "matéria-prima", "turno", "equipamento",
                        "severidade", "causa raiz", "plano de ação"],
        "regras": [
            "Todo registro guarda data, responsável, turno e equipamento",
            "Severidade crítica bloqueia o lote automaticamente",
        ],
    },
    "telas": [
        {"slug": "registro", "nome": "Registro de não conformidade", "tipo": "formulario",
         "usuario": "Operador de produção",
         "objetivo": "Registrar um defeito pelo celular em menos de um minuto"},
        {"slug": "rastreio", "nome": "Rastreabilidade de lote", "tipo": "consulta",
         "usuario": "Coordenador da qualidade",
         "objetivo": "Ver a cadeia completa de um lote e as não conformidades ligadas a ele"},
    ],
    "stories": [
        {"id": "ST-01", "tela": "registro", "titulo": "Registrar não conformidade no posto de trabalho",
         "narrativa": "Como operador, quero registrar o defeito direto do celular, para não depender de papel.",
         "prioridade": "Alta",
         "criterios_aceite": [
             "Data, turno e responsável são preenchidos pelo sistema, sem digitação do operador",
             "Tipo de defeito e severidade são listas fechadas, não campo livre",
             "O registro só é aceito com lote, tipo de defeito e descrição preenchidos",
             "Ao gravar, a tela exibe o código do registro e a evidência auditável",
         ],
         "restricoes_briefing": ["Responsiva para o chão de fábrica",
                                 "Operável sem treinamento técnico",
                                 "Evidência auditável em todo registro"]},
        {"id": "ST-02", "tela": "rastreio", "titulo": "Consultar a cadeia de um lote",
         "narrativa": "Como coordenador, quero digitar o código do lote e ver a cadeia inteira, para responder ao cliente em segundos.",
         "prioridade": "Alta",
         "criterios_aceite": [
             "A busca por código de lote retorna as não conformidades registradas nele",
             "A cadeia é apresentada em ordem, do insumo ao expedido",
             "Lote sem registro apresenta uma mensagem que diz o que fazer",
         ],
         "restricoes_briefing": ["Rastreabilidade cobrindo toda a cadeia produtiva"]},
    ],
}

DEV_PLANO = {
    "abordagem": (
        "Página única autossuficiente: HTML, CSS e JavaScript em um arquivo, sem dependência "
        "externa, para funcionar mesmo sem internet no chão de fábrica. Estado em memória, "
        "persistência pela API de registros, recálculo por evento de input."
    ),
    "decisoes": [
        {"decisao": "Página autossuficiente, sem framework nem CDN",
         "justificativa": "A tela é usada no chão de fábrica, onde a rede cai; um arquivo único sempre abre.",
         "alternativas_descartadas": "React via CDN — traria build e uma dependência de rede que o critério não tolera.",
         "impacto": "Arquitetura"},
        {"decisao": "Recalcular no evento input, não em botão de calcular",
         "justificativa": "O critério exige resultado imediato ao alterar qualquer campo.",
         "alternativas_descartadas": "Botão Calcular — um toque a mais e quebra o 'na hora' pedido pelo cliente.",
         "impacto": "UX"},
        {"decisao": "Contexto de data e responsável resolvido pela própria página",
         "justificativa": "Atende o critério de zero digitação de contexto e elimina erro de preenchimento.",
         "alternativas_descartadas": "Campos manuais — o usuário erraria o turno no fim do plantão.",
         "impacto": "Auditoria"},
    ],
    "estruturas": [{"elemento": "form-principal", "papel": "entrada dos dados do turno"},
                   {"elemento": "painel-resultado", "papel": "saída calculada em tempo real"}],
}

QA_APROVADO = {
    "casos": [
        {"id": "TC-01", "criterio": "Resultado recalcula sem recarregar a página",
         "passos": "Localizada a função de recálculo e o listener de input no <script>",
         "esperado": "Alteração de campo dispara novo cálculo",
         "obtido": "addEventListener('input') ligado a todos os campos numéricos",
         "resultado": "PASSOU", "evidencia": "listener 'input' em #form-principal"},
        {"id": "TC-02", "criterio": "Registro gravado com data e responsável",
         "passos": "Verificado o corpo do fetch POST enviado à API de registros",
         "esperado": "Payload inclui data e responsável sem digitação do usuário",
         "obtido": "Campos preenchidos pela própria página antes do envio",
         "resultado": "PASSOU", "evidencia": "objeto 'dados' montado em salvar()"},
        {"id": "TC-03", "criterio": "Estado vazio e erro (caso negativo)",
         "passos": "Simulada lista vazia e falha de rede no fetch",
         "esperado": "Mensagem orientando o que fazer, sem tela em branco",
         "obtido": "Bloco de estado vazio e captura de erro presentes",
         "resultado": "PASSOU", "evidencia": "try/catch em carregar() e div de estado vazio"},
    ],
    "veredito": "APROVADO",
    "justificativa": "Todos os critérios verificáveis no código foram atendidos, incluindo o caso negativo.",
    "pendencias": [],
}

QA_REPROVADO = {
    "casos": [
        {"id": "TC-01", "criterio": "Resultado recalcula sem recarregar a página",
         "passos": "Procurado listener de recálculo no <script>",
         "esperado": "Alteração de campo dispara novo cálculo",
         "obtido": "Recálculo depende de clique em botão",
         "resultado": "FALHOU", "evidencia": "nenhum addEventListener('input') encontrado"},
        {"id": "TC-02", "criterio": "Uma coluna em tela de celular",
         "passos": "Conferidas as media queries do <style>",
         "esperado": "Layout de coluna única abaixo de 700px",
         "obtido": "@media presente e correta",
         "resultado": "PASSOU", "evidencia": "@media (max-width: 700px)"},
    ],
    "veredito": "REPROVADO",
    "justificativa": "O critério de resultado imediato não é atendido: o cálculo só ocorre por clique.",
    "pendencias": ["Recalcular no evento input de cada campo, sem depender de botão"],
}


def respond(system: str, user: str) -> dict:
    global _qa_calls

    if system.startswith("Você é o PO Agent"):
        texto = user.lower()
        if any(t in texto for t in ("perda", "extrus", "resina", "tubo", "calcul")):
            return PO_PERDAS
        return PO_QUALIDADE

    if system.startswith("Você é o Dev Agent"):
        return DEV_PLANO

    with _lock:
        _qa_calls += 1
        primeira = _qa_calls == 1
    return QA_REPROVADO if primeira else QA_APROVADO


# --- Page templates -------------------------------------------------------

BASE_CSS = """
:root{--papel:#E7EAE4;--superficie:#FCFDFB;--tinta:#14171A;--grafite:#5C636A;
--regua:#C6CBC3;--aco:#1F4E5F;--aco-claro:#E2ECEF;--alerta:#9A5407;--critico:#A32116;--ok:#2C6E49;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
*{box-sizing:border-box}
body{margin:0;padding:20px;background:var(--papel);color:var(--tinta);font-family:var(--sans);
font-size:15px;line-height:1.5}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:24px;letter-spacing:-.02em;margin:0 0 4px}
.olho{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;
color:var(--grafite);margin:0 0 6px}
.sub{color:var(--grafite);margin:0 0 22px}
.bloco{background:var(--superficie);border:1px solid var(--regua);padding:18px 20px;margin-bottom:18px}
.campo{margin-bottom:16px}
label{display:block;font-weight:650;margin-bottom:4px}
.ajuda{font-size:12.5px;color:var(--grafite);margin:0 0 6px}
input,select,textarea{width:100%;min-height:48px;padding:11px 12px;font:inherit;
background:var(--superficie);color:var(--tinta);border:1px solid var(--grafite);border-radius:0}
textarea{min-height:92px}
input:focus,select:focus,textarea:focus,button:focus-visible{outline:3px solid var(--aco);outline-offset:1px}
button{min-height:50px;padding:13px 22px;font:inherit;font-weight:700;background:var(--aco);
color:#fff;border:none;cursor:pointer;width:100%}
button:hover{background:#17414F}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-family:var(--mono);font-size:10px;font-weight:500;letter-spacing:.1em;
text-transform:uppercase;color:var(--grafite);border-bottom:1px solid var(--tinta);padding:6px 8px 6px 0}
td{padding:9px 8px 9px 0;border-bottom:1px solid var(--regua)}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
.vazio{border:1px dashed var(--grafite);padding:24px;text-align:center;color:var(--grafite)}
.erro{border-left:3px solid var(--critico);background:#FBEDEC;padding:10px 14px;margin-bottom:14px}
.ok{border-left:3px solid var(--ok);background:#EAF3EE;padding:10px 14px;margin-bottom:14px}
.grade{display:grid;grid-template-columns:1fr 1fr;gap:0 18px}
.saida{background:var(--aco-claro);border:1px solid #A9C4CC;padding:16px 18px;margin-bottom:18px}
.saida dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:2px 18px;margin:0}
.saida dt{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--grafite)}
.saida dd{margin:2px 0 10px;font-family:var(--mono);font-size:22px;font-variant-numeric:tabular-nums}
.faixa{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
padding:3px 8px;border:1px solid currentColor;display:inline-block}
.f-ok{color:var(--ok)}.f-atencao{color:var(--alerta)}.f-critico{color:var(--critico)}
@media (max-width:700px){body{padding:14px}.grade{grid-template-columns:1fr}
.saida dd{font-size:19px}}
"""


def _pagina(titulo, olho, sub, corpo, script):
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(titulo)}</title>
<style>{BASE_CSS}</style>
</head>
<body>
<div class="wrap">
<p class="olho">{_html.escape(olho)}</p>
<h1>{_html.escape(titulo)}</h1>
<p class="sub">{_html.escape(sub)}</p>
{corpo}
</div>
<script>
{script}
</script>
</body>
</html>"""


def _calculadora(slug):
    corpo = """
<div class="saida" id="painel-resultado">
  <dl>
    <div><dt>Perda total</dt><dd id="out-kg">0 kg</dd></div>
    <div><dt>Perda percentual</dt><dd id="out-pct">0,00%</dd></div>
    <div><dt>Custo da perda</dt><dd id="out-rs">R$ 0,00</dd></div>
  </dl>
  <span class="faixa f-ok" id="out-faixa">Dentro da meta</span>
</div>

<div class="bloco">
  <div id="aviso"></div>
  <div id="form-principal">
    <div class="grade">
      <div class="campo"><label for="linha">Linha de extrusao</label>
        <select id="linha"><option>Linha 1</option><option>Linha 2</option>
        <option>Linha 3</option><option>Linha 4</option><option>Linha 5</option></select></div>
      <div class="campo"><label for="turno">Turno</label>
        <select id="turno"><option>1o turno</option><option>2o turno</option></select></div>
      <div class="campo"><label for="resina">Resina consumida (kg)</label>
        <input id="resina" type="number" min="0" step="0.1" value="0"></div>
      <div class="campo"><label for="tubo">Tubo bom produzido (kg)</label>
        <input id="tubo" type="number" min="0" step="0.1" value="0"></div>
      <div class="campo"><label for="partida">Refugo de partida (kg)</label>
        <input id="partida" type="number" min="0" step="0.1" value="0"></div>
      <div class="campo"><label for="purga">Purga de troca (kg)</label>
        <input id="purga" type="number" min="0" step="0.1" value="0"></div>
      <div class="campo"><label for="corte">Sobra de corte (kg)</label>
        <input id="corte" type="number" min="0" step="0.1" value="0"></div>
      <div class="campo"><label for="preco">Preco da resina (R$/kg)</label>
        <input id="preco" type="number" min="0" step="0.01" value="0"></div>
      <div class="campo"><label for="paradas">Horas paradas</label>
        <input id="paradas" type="number" min="0" step="0.5" value="0"></div>
      <div class="campo"><label for="motivo">Motivo da parada</label>
        <input id="motivo" type="text" placeholder="troca de molde, manutencao..."></div>
    </div>
    <p class="ajuda">Data e responsavel sao preenchidos pelo sistema no momento do lancamento.</p>
    <button id="btn-salvar" type="button">Gravar lancamento do turno</button>
  </div>
</div>

<div class="bloco">
  <h2 style="font-size:15px;margin:0 0 12px">Lancamentos gravados</h2>
  <div id="lista"><p class="vazio">Carregando...</p></div>
</div>"""

    script = """
var API = '/api/apps/SLUG/records';
var campos = ['resina','tubo','partida','purga','corte','preco','paradas'];
function n(id){ var v = parseFloat(document.getElementById(id).value); return isNaN(v) ? 0 : v; }
function brl(v){ return 'R$ ' + v.toFixed(2).replace('.', ','); }

function calcular(){
  var resina = n('resina'), tubo = n('tubo');
  var perda = Math.max(resina - tubo, 0);
  var pct = resina > 0 ? (perda / resina) * 100 : 0;
  var custo = perda * n('preco');
  document.getElementById('out-kg').textContent = perda.toFixed(1).replace('.', ',') + ' kg';
  document.getElementById('out-pct').textContent = pct.toFixed(2).replace('.', ',') + '%';
  document.getElementById('out-rs').textContent = brl(custo);
  var faixa = document.getElementById('out-faixa');
  if (pct > 7) { faixa.className = 'faixa f-critico'; faixa.textContent = 'Critico'; }
  else if (pct >= 4) { faixa.className = 'faixa f-atencao'; faixa.textContent = 'Atencao'; }
  else { faixa.className = 'faixa f-ok'; faixa.textContent = 'Dentro da meta'; }
  return { perda_kg: perda, perda_pct: pct, custo: custo };
}

campos.forEach(function(id){
  document.getElementById(id).addEventListener('input', calcular);
});
document.getElementById('linha').addEventListener('change', calcular);
document.getElementById('turno').addEventListener('change', calcular);

function aviso(texto, tipo){
  document.getElementById('aviso').innerHTML = texto
    ? '<div class="' + tipo + '">' + texto + '</div>' : '';
}

document.getElementById('btn-salvar').addEventListener('click', function(){
  var r = calcular();
  if (n('resina') <= 0) { aviso('Informe a resina consumida antes de gravar.', 'erro'); return; }
  var dados = {
    linha: document.getElementById('linha').value,
    turno: document.getElementById('turno').value,
    resina_kg: n('resina'), tubo_bom_kg: n('tubo'),
    refugo_partida_kg: n('partida'), purga_kg: n('purga'), sobra_corte_kg: n('corte'),
    preco_kg: n('preco'), horas_paradas: n('paradas'),
    motivo: document.getElementById('motivo').value,
    perda_kg: Number(r.perda_kg.toFixed(2)), perda_pct: Number(r.perda_pct.toFixed(2)),
    custo: Number(r.custo.toFixed(2)),
    data: new Date().toISOString().slice(0,16).replace('T',' '),
    responsavel: 'Supervisor de turno'
  };
  fetch(API, { method: 'POST', headers: {'Content-Type':'application/json'},
               body: JSON.stringify({ tipo: 'lancamentos', dados: dados }) })
    .then(function(resp){ if(!resp.ok) throw new Error('HTTP ' + resp.status); return resp.json(); })
    .then(function(reg){
      aviso('Lancamento gravado. Evidencia ' + reg.hash + '.', 'ok');
      carregar();
    })
    .catch(function(e){ aviso('Nao foi possivel gravar: ' + e.message +
      '. Verifique a conexao e tente novamente.', 'erro'); });
});

function carregar(){
  fetch(API + '?tipo=lancamentos')
    .then(function(r){ if(!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function(d){
      var regs = d.registros || [];
      var alvo = document.getElementById('lista');
      if (!regs.length) {
        alvo.innerHTML = '<p class="vazio">Nenhum lancamento ainda. ' +
          'Preencha os campos acima e toque em Gravar lancamento do turno.</p>';
        return;
      }
      var linhas = regs.map(function(x){
        var d2 = x.dados;
        return '<tr><td class="num">' + (d2.data||'') + '</td><td>' + (d2.linha||'') +
          '</td><td>' + (d2.turno||'') + '</td><td class="num">' +
          (d2.perda_kg||0) + ' kg</td><td class="num">' + (d2.perda_pct||0) +
          '%</td><td class="num">' + (x.hash||'') + '</td></tr>';
      }).join('');
      alvo.innerHTML = '<table><thead><tr><th>Data</th><th>Linha</th><th>Turno</th>' +
        '<th>Perda</th><th>%</th><th>Evidencia</th></tr></thead><tbody>' + linhas + '</tbody></table>';
    })
    .catch(function(e){
      document.getElementById('lista').innerHTML =
        '<div class="erro">Nao foi possivel carregar os lancamentos: ' + e.message + '</div>';
    });
}

calcular();
carregar();
""".replace("SLUG", slug)
    return _pagina("Lancamento de turno", "Chao de fabrica - fim de turno",
                   "Lance os numeros do turno. A perda aparece na hora, em kg, "
                   "em percentual e em reais.", corpo, script)


def _formulario(slug):
    corpo = """
<div class="bloco">
  <div id="aviso"></div>
  <div id="contexto" class="saida">
    <dl>
      <div><dt>Data e hora</dt><dd class="num" id="ctx-data" style="font-size:15px">—</dd></div>
      <div><dt>Turno</dt><dd id="ctx-turno" style="font-size:15px">—</dd></div>
      <div><dt>Responsavel</dt><dd id="ctx-resp" style="font-size:15px">—</dd></div>
    </dl>
  </div>
  <div id="form-principal">
    <div class="campo"><label for="lote">Lote</label>
      <p class="ajuda">Codigo impresso na etiqueta da caixa</p>
      <input id="lote" type="text" placeholder="LT-2026-0412"></div>
    <div class="campo"><label for="tipo">O que voce viu?</label>
      <p class="ajuda">Escolha o mais parecido</p>
      <select id="tipo"><option value="">Selecione...</option><option>Dimensional</option>
      <option>Visual</option><option>Funcional</option><option>Contaminacao</option></select></div>
    <div class="campo"><label for="severidade">Gravidade</label>
      <select id="severidade"><option>Menor</option><option>Maior</option>
      <option>Critica</option></select></div>
    <div class="campo"><label for="qtd">Quantas pecas?</label>
      <input id="qtd" type="number" min="0" value="0"></div>
    <div class="campo"><label for="descricao">Descreva com suas palavras</label>
      <textarea id="descricao" placeholder="Onde na peca, quando comecou"></textarea></div>
    <button id="btn-salvar" type="button">Registrar nao conformidade</button>
  </div>
</div>

<div class="bloco">
  <h2 style="font-size:15px;margin:0 0 12px">Registros recentes</h2>
  <div id="lista"><p class="vazio">Carregando...</p></div>
</div>"""

    script = """
var API = '/api/apps/SLUG/records';

function turnoAgora(h){ if (h >= 6 && h < 14) return '1o turno';
  if (h >= 14 && h < 22) return '2o turno'; return '3o turno'; }

var agora = new Date();
document.getElementById('ctx-data').textContent =
  agora.toLocaleDateString('pt-BR') + ' ' + agora.toTimeString().slice(0,5);
document.getElementById('ctx-turno').textContent = turnoAgora(agora.getHours());
document.getElementById('ctx-resp').textContent = 'Operador do turno';

function aviso(texto, tipo){
  document.getElementById('aviso').innerHTML = texto
    ? '<div class="' + tipo + '">' + texto + '</div>' : '';
}

document.getElementById('btn-salvar').addEventListener('click', function(){
  var lote = document.getElementById('lote').value.trim();
  var tipo = document.getElementById('tipo').value;
  var desc = document.getElementById('descricao').value.trim();
  if (!lote || !tipo || !desc) {
    aviso('Preencha lote, tipo de defeito e descricao para registrar.', 'erro'); return;
  }
  var d = new Date();
  var dados = { lote: lote, tipo_defeito: tipo,
    severidade: document.getElementById('severidade').value,
    quantidade: parseInt(document.getElementById('qtd').value || '0', 10),
    descricao: desc, turno: turnoAgora(d.getHours()),
    responsavel: 'Operador do turno', equipamento: 'Definido pela linha',
    data: d.toISOString().slice(0,16).replace('T',' ') };
  fetch(API, { method: 'POST', headers: {'Content-Type':'application/json'},
               body: JSON.stringify({ tipo: 'nao_conformidades', dados: dados }) })
    .then(function(r){ if(!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function(reg){
      aviso('Registro NC-' + String(reg.id).padStart(4,'0') +
        ' gravado. Evidencia auditavel ' + reg.hash + '.', 'ok');
      document.getElementById('descricao').value = '';
      carregar();
    })
    .catch(function(e){ aviso('Nao foi possivel gravar: ' + e.message +
      '. Verifique a conexao e tente novamente.', 'erro'); });
});

function carregar(){
  fetch(API + '?tipo=nao_conformidades')
    .then(function(r){ if(!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function(d){
      var regs = d.registros || [];
      var alvo = document.getElementById('lista');
      if (!regs.length) {
        alvo.innerHTML = '<p class="vazio">Nenhuma nao conformidade registrada. ' +
          'Preencha o formulario acima para criar a primeira.</p>';
        return;
      }
      alvo.innerHTML = '<table><thead><tr><th>Registro</th><th>Lote</th><th>Defeito</th>' +
        '<th>Gravidade</th><th>Evidencia</th></tr></thead><tbody>' +
        regs.map(function(x){ var y = x.dados;
          return '<tr><td class="num">NC-' + String(x.id).padStart(4,'0') + '</td><td class="num">' +
            (y.lote||'') + '</td><td>' + (y.tipo_defeito||'') + '</td><td>' +
            (y.severidade||'') + '</td><td class="num">' + (x.hash||'') + '</td></tr>';
        }).join('') + '</tbody></table>';
    })
    .catch(function(e){
      document.getElementById('lista').innerHTML =
        '<div class="erro">Nao foi possivel carregar os registros: ' + e.message + '</div>';
    });
}

carregar();
""".replace("SLUG", slug)
    return _pagina("Registro de nao conformidade", "Chao de fabrica - registro em campo",
                   "Menos de um minuto. Data, turno e responsavel o sistema ja sabe.",
                   corpo, script)


def _consulta(slug, titulo, olho, sub, colecao):
    corpo = """
<div class="bloco">
  <div class="campo"><label for="busca">Buscar</label>
    <input id="busca" type="text" placeholder="Digite para filtrar"></div>
  <button id="btn-buscar" type="button">Atualizar</button>
</div>
<div class="bloco">
  <div id="resumo"></div>
  <div id="lista"><p class="vazio">Carregando...</p></div>
</div>"""

    script = """
var API = '/api/apps/SLUG/records';
var COLECAO = 'COLECAO';
var cache = [];

function render(){
  var termo = document.getElementById('busca').value.trim().toLowerCase();
  var regs = cache.filter(function(x){
    return !termo || JSON.stringify(x.dados).toLowerCase().indexOf(termo) !== -1; });
  var alvo = document.getElementById('lista');
  var resumo = document.getElementById('resumo');
  if (!cache.length) {
    resumo.innerHTML = '';
    alvo.innerHTML = '<p class="vazio">Nenhum registro ainda. ' +
      'Use a outra tela da aplicacao para criar o primeiro.</p>';
    return;
  }
  if (!regs.length) {
    resumo.innerHTML = '';
    alvo.innerHTML = '<p class="vazio">Nada encontrado para esse termo. ' +
      'Limpe o campo de busca para ver todos os registros.</p>';
    return;
  }
  var chaves = Object.keys(regs[0].dados).slice(0, 6);
  resumo.innerHTML = '<p class="sub">' + regs.length + ' de ' + cache.length +
    ' registro(s).</p>';
  alvo.innerHTML = '<table><thead><tr>' +
    chaves.map(function(k){ return '<th>' + k.replace(/_/g,' ') + '</th>'; }).join('') +
    '<th>Evidencia</th></tr></thead><tbody>' +
    regs.map(function(x){
      return '<tr>' + chaves.map(function(k){
        return '<td>' + (x.dados[k] === undefined ? '' : x.dados[k]) + '</td>'; }).join('') +
        '<td class="num">' + (x.hash||'') + '</td></tr>';
    }).join('') + '</tbody></table>';
}

function carregar(){
  fetch(API + '?tipo=' + COLECAO)
    .then(function(r){ if(!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function(d){ cache = d.registros || []; render(); })
    .catch(function(e){
      document.getElementById('lista').innerHTML =
        '<div class="erro">Nao foi possivel carregar: ' + e.message + '</div>'; });
}

document.getElementById('busca').addEventListener('input', render);
document.getElementById('btn-buscar').addEventListener('click', carregar);
carregar();
""".replace("SLUG", slug).replace("COLECAO", colecao)
    return _pagina(titulo, olho, sub, corpo, script)


def respond_text(system: str, user: str) -> str:
    """Assembles a working page based on the screen type declared in the handoff."""
    slug = "app"
    m = re.search(r"/api/apps/([a-z0-9\-]+)/records", user)
    if m:
        slug = m.group(1)
    tipo = ""
    m = re.search(r"^TELA:\s*(.+?)\s*\((\w+)\)", user, re.M)
    nome = m.group(1) if m else "Tela"
    if m:
        tipo = m.group(2).lower()

    if tipo == "calculadora":
        return _calculadora(slug)
    if tipo == "formulario":
        return _formulario(slug)
    if "perda" in user.lower() or "linha" in nome.lower():
        return _consulta(slug, nome, "Visao consolidada",
                         "Comparativo dos lancamentos gravados pelas linhas.", "lancamentos")
    return _consulta(slug, nome, "Consulta",
                     "Busque por qualquer termo dos registros gravados.", "nao_conformidades")
