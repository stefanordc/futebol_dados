"""Assistente quantitativo do Nostradamus: regras explicáveis, validação futura simulada.

Treina limiares APENAS em datas cronologicamente anteriores à amostra
reservada para validação. Não faz chamadas a LLM nem promete ganhos reais.
"""
from __future__ import annotations
from math import ceil
import queries_nostradamus as ns

# Espaço pequeno de indicadores para que uma sugestão seja auditável.
FEATURES = (
    ("favorito", "chutes_certos"),
    ("zebra", "chutes_certos"),
    ("ambos", "chutes_certos"),
    ("favorito", "xg"),
    ("zebra", "xg"),
    ("ambos", "xg"),
    ("favorito", "gols_feitos"),
    ("ambos", "gols_feitos"),
    ("favorito", "escanteios"),
    ("ambos", "escanteios"),
    ("favorito", "pontos_jogo"),
)
ODD_MARKETS = (
    "back_favorito", "back_zebra", "back_empate",
    "over_15", "over_25", "over_35",
    "under_25", "ambos_marcam", "ambos_nao",
)
MAX_CANDIDATES=180
MIN_BASE_TRAIN=8
MIN_BASE_VALID=5
MIN_CANDIDATE_TRAIN=5
MIN_CANDIDATE_VALID=3


def _score(records):
    quoted=[r for r in records if r.get("unidades") is not None]
    n=len(quoted)
    if not n:
        return {"entradas":0,"total_reais":None,"media_reais":None,
                "roi_pct":None,"greens":0}
    profit=sum(r["unidades"] for r in quoted)*100
    return {"entradas":n, "total_reais":round(profit,2),
            "media_reais":round(profit/n,2),
            "roi_pct":round(profit/n,2),
            "greens":sum(1 for r in quoted if r["unidades"]>0)}


def _split(records):
    """Agrupa por data; nunca separa dois confrontos da mesma data."""
    ordered=sorted(records,key=lambda r:(r["data"],r["id"]))
    dates=sorted({r["data"] for r in ordered})
    if len(dates)<8:
        return [],[],None
    target=ceil(len(ordered)*0.65)
    boundary=None
    for day in dates[1:-1]:
        n=sum(r["data"]<=day for r in ordered)
        if n>=target:
            boundary=day
            break
    if boundary is None:
        return [],[],None
    left=[r for r in ordered if r["data"]<=boundary]
    right=[r for r in ordered if r["data"]>boundary]
    return left,right,boundary


def _feature(row,side,key):
    if side=="ambos":
        x=ns._n(row["stats_casa"].get(key))
        y=ns._n(row["stats_fora"].get(key))
        return min(x,y) if x is not None and y is not None else None
    favorite=row["favorito_casa"]
    if favorite is None:
        return None
    home=(favorite if side=="favorito" else not favorite)
    return ns._n(row["stats_casa" if home else "stats_fora"].get(key))


def _odd(row,market):
    try:
        actual=ns._market_for_game(market,row["favorito_casa"])
    except ValueError:
        return None
    value,_=ns._odds_for_game(row["partida"],actual,None)
    return value


def _quantiles(values):
    if not values:
        return []
    ordered=sorted(values)
    choices=set()
    for fraction in (0.25,0.40,0.5,0.60,0.75):
        pos=round((len(ordered)-1)*fraction)
        v=round(ordered[pos],2)
        if v>0:
            choices.add(v)
    return sorted(choices)


def _proposals(train):
    proposed=[]
    for market in ODD_MARKETS:
        values=[v for row in train if (v:=_odd(row,market)) is not None]
        if len(values)<MIN_BASE_TRAIN:
            continue
        for threshold in _quantiles(values):
            if 1.01<=threshold<=1000:
                proposed.append({
                    "tipo":"odd","mercado":market,
                    "odd_min":threshold,"odd_max":None
                })
                proposed.append({
                    "tipo":"odd","mercado":market,
                    "odd_min":None,"odd_max":threshold
                })
    for side,key in FEATURES:
        values=[v for row in train if (v:=_feature(row,side,key)) is not None]
        if len(values)<MIN_BASE_TRAIN:
            continue
        for threshold in _quantiles(values):
            proposed.append({
                "tipo":"indicador","lado":side,
                "mando_preferido":"indiferente","metrica":key,
                "comparador":"ge","referencia":"valor","valor":threshold
            })
    # Ordenação fixa para que a execução produza resultado reprodutível.
    return proposed[:MAX_CANDIDATES]


def _passes(row,condition):
    if condition["tipo"]=="odd":
        value=_odd(row,condition["mercado"])
        return value is not None and (
            condition["odd_min"] is None or value>=condition["odd_min"]
        ) and (
            condition["odd_max"] is None or value<=condition["odd_max"]
        )
    value=_feature(row,condition["lado"],condition["metrica"])
    return value is not None and value>=condition["valor"]


def _display(condition):
    if condition["tipo"]=="odd":
        market=ns.ODD_FILTER_MARKETS[condition["mercado"]]
        bound=("odd mínima de "+str(condition["odd_min"]).replace(".",",")
               if condition["odd_min"] is not None else
               "odd máxima de "+str(condition["odd_max"]).replace(".",","))
        return market+" · "+bound
    side={"favorito":"Favorito","zebra":"Zebra","ambos":"Ambos"}[condition["lado"]]
    return side+" · "+ns.METRICAS[condition["metrica"]]+" ≥ "+str(condition["valor"]).replace(".",",")


def _display_original(rule):
    """Rótulo curto para identificar uma regra existente, sem mudar seus dados."""
    if rule["tipo"]=="odd":
        return _display(rule)
    side={"favorito":"Favorito","zebra":"Zebra","ambos":"Ambos",
          "mandante":"Mandante","visitante":"Visitante"}.get(rule["lado"],"Equipe")
    return side+" · "+ns.METRICAS.get(rule["metrica"],rule["metrica"])


def analisar(payload,rows=None):
    """Encontra regras candidatas em treinamento e relata validação não utilizada.

    Retorna no máximo 3 sugestões. Comparações usam a mesma cotação do
    objetivo, stake R$100 e mesma data limite da estratégia original.
    """
    if not isinstance(payload,dict):
        raise ValueError("Parâmetros inválidos.")
    conditions=ns._valid_conditions(payload.get("condicoes"))
    baseline=ns.testar(payload,rows=rows,capture=True)
    originals=baseline.pop("_dados_otimizacao")
    raw_rows=baseline.pop("_jogos_originais")
    # Sem preço, não existe retorno monetário para aprender.
    priced=[r for r in originals if r.get("unidades") is not None]
    train,validation,boundary=_split(priced)
    if len(train)<MIN_BASE_TRAIN or len(validation)<MIN_BASE_VALID:
        return {"sugestoes":[],"corte":baseline["corte"],
                "base":_score(priced),
                "mensagem":"Amostra insuficiente com odds: são necessárias pelo menos 8 entradas de treino e 5 de validação, em datas distintas.",
                "metodo":"Regras interpretáveis, treino cronológico 65% e validação 35%."}
    original_train=_score(train)
    original_valid=_score(validation)
    ranked=[]

    # Inclusões: fazem apenas uma filtragem adicional das partidas já aprovadas.
    # O limite de 10 condições impede ADICIONAR, mas não impede REMOVER.
    if len(conditions)<10:
        existing={str(x) for x in conditions}
        for condition in _proposals(train):
            if str(ns._valid_conditions([condition])[0]) in existing:
                continue
            subset=[r for r in train if _passes(r,condition)]
            if len(subset)<max(MIN_CANDIDATE_TRAIN,ceil(len(train)*.4)) or len(subset)==len(train):
                continue
            score=_score(subset)
            gain=score["total_reais"]-original_train["total_reais"]
            mean=score["media_reais"]-original_train["media_reais"]
            if gain<=0 or mean<=0:
                continue
            ranked.append({
                "acao":"adicionar","condicao":condition,"indice":None,
                "descricao":_display(condition),"treino":score,"ganho":gain,
                "ganho_medio":mean,"amostra_validacao":None,
            })

    # Remoções: reexecuta as regras remanescentes sobre o MESMO universo bruto,
    # na MESMA data de corte. Assim pode recuperar partidas que o filtro excluía.
    # Não se olha o resultado da validação para escolher o que sugerir.
    if len(conditions)>1:
        for i in range(len(conditions)):
            remaining=[c for j,c in enumerate(conditions) if j!=i]
            alternative={**payload,"condicoes":remaining}
            candidate=ns.testar(alternative,rows=raw_rows,capture=True)
            candidate_rows=candidate.pop("_dados_otimizacao")
            candidate.pop("_jogos_originais",None)
            priced_candidate=[r for r in candidate_rows if r.get("unidades") is not None]
            older=[r for r in priced_candidate if r["data"]<=boundary]
            newer=[r for r in priced_candidate if r["data"]>boundary]
            if len(older)<max(MIN_CANDIDATE_TRAIN,ceil(len(train)*.4)):
                continue
            score=_score(older)
            gain=score["total_reais"]-original_train["total_reais"]
            mean=score["media_reais"]-original_train["media_reais"]
            if gain<=0 or mean<=0:
                continue
            ranked.append({
                "acao":"remover","condicao":None,"indice":i,
                "descricao":"Remover regra "+str(i+1)+": "+_display_original(conditions[i]),
                "treino":score,"ganho":gain,"ganho_medio":mean,
                "amostra_validacao":newer,
            })

    ranked.sort(key=lambda item:(
        -item["ganho"],-item["ganho_medio"],
        -item["treino"]["entradas"],item["descricao"],
    ))
    top=[]
    for item in ranked[:3]:
        if item["acao"]=="adicionar":
            subset=[r for r in validation if _passes(r,item["condicao"])]
        else:
            subset=item["amostra_validacao"]
        validated=_score(subset)
        top.append({
            "acao":item["acao"],
            "indice":item["indice"],
            "descricao":item["descricao"],
            "condicao":item["condicao"],
            "treino":item["treino"],
            "validacao":validated,
            "avaliacao":("Sinal positivo na validação"
                if len(subset)>=MIN_CANDIDATE_VALID
                and validated["total_reais"] is not None
                and validated["media_reais"]>original_valid["media_reais"]
                else "Sem confirmação na validação"),
        })
    return {
        "corte":baseline["corte"],"data_divisao":boundary,
        "base_treino":original_train,"base_validacao":original_valid,
        "sugestoes":top,
        "avaliadas":len(ranked),
        "metodo":"Busca de inclusão ou remoção de uma regra; treino cronológico 65% e validação posterior 35%.",
        "mensagem":("Nenhuma inclusão ou remoção de regra aumentou lucro total e médio no treino com amostra mínima."
                    if not top else
                    "Sugestões escolhidas apenas no treino. A validação posterior não influencia a escolha."),
        "aviso":"Resultados retrospectivos, sem garantia de lucro. A data de captura das odds importadas não comprova disponibilidade pré-jogo; Lay é estimado. Validação não substitui teste prospectivo.",
    }
