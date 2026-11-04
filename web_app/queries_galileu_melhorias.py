"""Melhoria guiada de métodos negativos no Galileu, sem alterar o original.

As propostas utilizam os otimizadores quantitativos já existentes no
Nostradamus. A seleção é feita exclusivamente no treino cronológico;
a validação posterior é exibida para avaliar a robustez da sugestão.
Este módulo é destinado ao aplicativo local, protegido por cookie de sessão.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
import queries_estrategias
import queries_nostradamus as ns
import queries_nostradamus_ai as ai
import queries_nostradamus_aovivo as live


def sequencias_prejuizo(bets, month, method_catalog):
    """Dois ou mais meses CIVIS consecutivos de prejuízo, terminando em month.

    Os saldos são calculados só das entradas executadas (green/red).
    Um mês de lucro, zero ou sem entrada interrompe a sequência.
    """
    if not month:
        return {}
    reference=date.fromisoformat(str(month)+"-01")
    available={int(m["id"]) for m in method_catalog}
    profit=defaultdict(lambda:defaultdict(lambda:Decimal("0")))
    executed=defaultdict(set)
    for bet in bets:
        if (bet.get("tipo")!="metodo" or bet.get("metodo_id") is None
            or bet.get("status") not in ("green","red")
            or bet.get("lucro_prejuizo") is None):
            continue
        mid=int(bet["metodo_id"])
        if mid not in available:
            continue
        key=str(bet["data"])[:7]
        # Não usar apostas de meses posteriores ao fechamento exibido.
        if key>month:
            continue
        profit[mid][key]+=Decimal(str(bet["lucro_prejuizo"]))
        executed[mid].add(key)
    flagged={}
    for mid in available:
        cursor=reference
        months=[]
        while True:
            key=cursor.strftime("%Y-%m")
            if key not in executed[mid] or profit[mid][key]>=0:
                break
            months.append({"mes":key,"lucro_prejuizo":float(profit[mid][key])})
            cursor=(cursor-timedelta(days=1)).replace(day=1)
            if len(months)>=120:
                break
        if len(months)<2:
            continue
        flagged[mid]={
            "meses_prejuizo_consecutivos":len(months),
            "prejuizo_acumulado":round(sum(v["lucro_prejuizo"] for v in months),2),
            "meses_prejuizo":months,
        }
    return flagged


def _source(method_id):
    """Obtém a versão atual, sem confiar em condições enviadas pelo navegador."""
    import queries_galileu_gameplay as gl
    if type(method_id) is not int or method_id<=0:
        raise ValueError("Método inválido.")
    if method_id>=gl.LIVE_METHOD_BASE:
        raw_id=method_id-gl.LIVE_METHOD_BASE
        source=next((r for r in live.listar_cenarios() if int(r["id"])==raw_id),None)
        if not source:
            raise ValueError("Cenário ao vivo não encontrado no Nostradamus.")
        return "ao_vivo",source
    source=next((r for r in queries_estrategias.listar() if int(r["id"])==method_id),None)
    if not source:
        raise ValueError("Estratégia pré-jogo não encontrada no Nostradamus.")
    return "pre_jogo",source


def _context(token,method_id):
    import queries_galileu_gameplay as gl
    current=gl.estado(token)
    if not current.get("iniciado") or not current.get("mes_encerrado"):
        raise ValueError("Finalize o mês antes de solicitar a melhoria de um método.")
    entry=next((
        item for item in current.get("metodos_fechamento",[])
        if item.get("metodo_id")==method_id
        and item.get("melhoria_elegivel") is True
    ),None)
    if entry is None:
        raise ValueError("A varinha só está disponível após dois meses seguidos de prejuízo.")
    kind,original=_source(method_id)
    return current,entry,kind,original


def _payload(kind,original,month):
    # A data de corte inclui apenas dados disponíveis até o fechamento,
    # nunca os resultados de meses seguintes da gameplay.
    first=date.fromisoformat(month+"-01")
    from calendar import monthrange
    month_end=first.replace(day=monthrange(first.year,first.month)[1])
    cutoff=min(month_end,date.today()-timedelta(days=1)).isoformat()
    if kind=="ao_vivo":
        cfg=dict(original["configuracao"])
        cfg["corte"]=cutoff
        return cfg
    leagues=original.get("campeonato_ids") or (
        [original["campeonato_id"]] if original.get("campeonato_id") else []
    )
    return {
        "objetivo":original["objetivo"],
        "corte":cutoff,
        "jogos":str(original.get("jogos") or "20"),
        "campeonato_ids":list(leagues),
        "condicoes":original["condicoes"],
        "odd_hipotetica":original.get("odd_hipotetica"),
        "comissao_pct":float(original.get("comissao_pct") or 4.5),
    }


def _default_name(original,month,index):
    suffix=f" (IA {month} · {index+1})"
    return str(original["nome"])[:80-len(suffix)]+suffix


def _analysis(token,method_id):
    current,entry,kind,source=_context(token,method_id)
    month=current["mes_encerrado"]
    payload=_payload(kind,source,month)
    output=live.analisar(payload) if kind=="ao_vivo" else ai.analisar(payload)
    suggestions=output.get("sugestoes") or []
    for i,item in enumerate(suggestions):
        item["nome_sugerido"]=_default_name(source,month,i)
    return {
        "metodo_id":method_id,
        "metodo":entry["nome"],
        "tipo":kind,
        "versao_original":int(source["versao"]),
        "mes_referencia":month,
        "meses_prejuizo_consecutivos":entry["meses_prejuizo_consecutivos"],
        "prejuizo_acumulado":entry["prejuizo_acumulado"],
        "meses_prejuizo":entry["meses_prejuizo"],
        "mensagem":output.get("mensagem") or "",
        "metodo_analise":output.get("metodo") or "",
        "aviso":output.get("aviso") or "Resultados históricos não garantem ganhos futuros.",
        "base_treino":output.get("base_treino"),
        "base_validacao":output.get("base_validacao"),
        "data_divisao":output.get("data_divisao"),
        "sugestoes":suggestions,
    },payload,source


def sugerir(token,method_id):
    analyzed,_,_=_analysis(token,method_id)
    return analyzed


def _apply_rule(payload,suggestion,kind):
    rules=list(payload.get("condicoes") or [])
    if suggestion["acao"]=="adicionar":
        if len(rules)>=10:
            raise ValueError("Limite de 10 condições atingido.")
        if not isinstance(suggestion.get("condicao"),dict):
            raise ValueError("Sugestão de inclusão inválida.")
        candidate=ns._valid_conditions([suggestion["condicao"]])[0]
        if candidate in rules:
            raise ValueError("A regra sugerida já existe.")
        rules.append(candidate)
    elif suggestion["acao"]=="remover":
        index=suggestion.get("indice")
        if type(index) is not int or not 0<=index<len(rules):
            raise ValueError("Regra de remoção não encontrada.")
        rules.pop(index)
    else:
        raise ValueError("Tipo de sugestão inválido.")
    if kind=="pre_jogo":
        rules=ns._valid_conditions(rules)  # exige entre 1 e 10
    elif rules:
        rules=ns._valid_conditions(rules)
    return {**payload,"condicoes":rules}


def salvar(token,method_id,request):
    """Recalcula a sugestão antes de salvar; nunca confia em regras da UI."""
    if not isinstance(request,dict):
        raise ValueError("Informe a sugestão escolhida.")
    index=request.get("indice")
    if type(index) is not int or not 0<=index<3:
        raise ValueError("Escolha uma das sugestões apresentadas.")
    analyzed,payload,original=_analysis(token,method_id)
    if (request.get("mes_referencia")!=analyzed["mes_referencia"]
        or request.get("versao_original")!=analyzed["versao_original"]):
        raise ValueError("O fechamento ou método foi atualizado. Gere as sugestões novamente.")
    if index>=len(analyzed["sugestoes"]):
        raise ValueError("Sugestão indisponível. Gere a análise novamente.")
    suggestion=analyzed["sugestoes"][index]
    cfg=_apply_rule(payload,suggestion,analyzed["tipo"])
    name=request.get("nome") or suggestion["nome_sugerido"]
    if not isinstance(name,str) or not 1<=len(name.strip())<=80:
        raise ValueError("Informe um nome de até 80 caracteres para o novo método.")
    if name.strip().casefold()==str(original["nome"]).strip().casefold():
        raise ValueError("O novo método deve possuir nome diferente do original.")
    cfg["nome"]=name.strip()
    # Sempre INSERT, nunca UPDATE: preserva o método original e seu histórico.
    saved=(live.criar_cenario(cfg) if analyzed["tipo"]=="ao_vivo"
           else queries_estrategias.criar(cfg))
    import queries_galileu_gameplay as gl
    return {
        "criado":True,
        "metodo_id":(gl.LIVE_METHOD_BASE+int(saved["id"])
                     if analyzed["tipo"]=="ao_vivo" else int(saved["id"])),
        "nome":saved["nome"],
        "tipo":analyzed["tipo"],
        "origem_id":method_id,
        "mensagem":"Novo método salvo no Nostradamus. O original e o histórico permanecem intactos. O Galileu considerará o novo método nos próximos meses.",
    }
