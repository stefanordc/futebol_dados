"""Web app de análise — FastAPI + frontend estático (estilo FotMob)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import queries
import queries_clube
import queries_entidade
import queries_liga
import queries_stats
import queries_finalizacoes_sofridas
import queries_performance
import queries_x1
import queries_x1_analise
import queries_x1_texto
import queries_nostradamus
import queries_galileu
import queries_tecnico_avancadas

DIR = Path(__file__).resolve().parent
TEMPLATES = DIR / "templates"
STATIC = DIR / "static"

app = FastAPI(title="Análise de Jogos", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def home():
    return FileResponse(TEMPLATES / "index.html")


@app.get("/jogo/{jogo_id}")
def pagina_jogo(jogo_id: int):
    return FileResponse(TEMPLATES / "match.html")


@app.get("/liga/{campeonato_id}")
def pagina_liga(campeonato_id: int):
    return FileResponse(TEMPLATES / "league.html")


@app.get("/estatisticas")
def pagina_estatisticas():
    return FileResponse(TEMPLATES / "stats.html")


@app.get("/clubes")
def pagina_clubes():
    return FileResponse(TEMPLATES / "clubes.html")


@app.get("/jogadores")
@app.get("/tecnicos")
@app.get("/arbitros")
def pagina_diretorio():
    return FileResponse(TEMPLATES / "directory.html")


@app.get("/apostas")
def pagina_apostas():
    return RedirectResponse(url="/apostas/x1",status_code=307)


@app.get("/apostas/nostradamus")
def pagina_nostradamus():
    return FileResponse(TEMPLATES / "nostradamus.html")


@app.get("/api/apostas/nostradamus/metadata")
def nostradamus_metadata():
    return {
       "metricas":queries_nostradamus.METRICAS,
       "comparadores":queries_nostradamus.COMPARADORES,
       "objetivos":queries_nostradamus.MERCADOS,
       "ligas":queries_nostradamus.ligas_disponiveis(),
    }


@app.post("/api/apostas/nostradamus/testar")
def nostradamus_testar(payload: dict):
    try:
        return queries_nostradamus.testar(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc


@app.get("/apostas/galileu")
def pagina_galileu():
    return FileResponse(TEMPLATES / "galileu.html")


@app.get("/apostas/galileu/relatorio")
def pagina_galileu_relatorio():
    return FileResponse(TEMPLATES / "galileu_report.html")


@app.post("/api/apostas/galileu/sinais")
def api_galileu_sinais(payload: dict):
    try:
        return queries_galileu.sinais(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc


@app.post("/api/apostas/galileu/confirmar")
def api_galileu_confirmar(payload: dict):
    try:
        return queries_galileu.confirmar(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc


@app.get("/api/apostas/galileu/relatorio")
def api_galileu_relatorio():
    return queries_galileu.relatorio()


@app.get("/apostas/x1")
def pagina_apostas_x1():
    return FileResponse(TEMPLATES / "bets_x1.html")


@app.post("/api/apostas/x1/favoritometro/texto")
def api_favoritometro_texto(fatos: dict):
    # IA opcional: a chave de acesso permanece exclusivamente no servidor.
    try:
        return {"texto": queries_x1_texto.gerar_texto(fatos)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        status = 503 if "Configure OPENAI_API_KEY" in str(exc) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@app.get("/api/apostas/x1/analise")
def api_apostas_x1_analise(
    campeonato_id: int = Query(..., ge=1),
    mandante_id: int = Query(..., ge=1),
    visitante_id: int = Query(..., ge=1),
    temporada: str = Query(..., min_length=1),
    jogos: str = Query("20", pattern="^(5|10|20|temporada)$"),
):
    try:
        return queries_x1_analise.analisar(
            campeonato_id, temporada, mandante_id, visitante_id, jogos
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/apostas/x1")
def api_apostas_x1(
    campeonato_id: int = Query(..., ge=1),
    mandante_id: int = Query(..., ge=1),
    visitante_id: int = Query(..., ge=1),
    temporada: str | None = None,
):
    try:
        return queries_x1.avaliar(campeonato_id, mandante_id, visitante_id, temporada)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/clube/{clube_id}")
def pagina_clube(clube_id: int):
    return FileResponse(TEMPLATES / "club.html")


@app.get("/jogador/{jogador_id}")
def pagina_jogador(jogador_id: int):
    return FileResponse(TEMPLATES / "entity.html")


@app.get("/tecnico/{tecnico_id}")
def pagina_tecnico(tecnico_id: int):
    return FileResponse(TEMPLATES / "entity.html")


@app.get("/arbitro/{arbitro_id}")
def pagina_arbitro(arbitro_id: int):
    return FileResponse(TEMPLATES / "entity.html")


@app.get("/api/clubes/meta")
def api_clubes_meta(
    pais: str | None = None,
    campeonato_id: int | None = None,
    temporada: str | None = None,
):
    paises = queries_stats.paises_com_dados()
    ligas = queries_stats.ligas_filtro(pais)
    if campeonato_id and not any(l["id"] == campeonato_id for l in ligas):
        campeonato_id = None
    temps = queries_stats.temporadas_filtro(campeonato_id, pais)
    temp = temporada if temporada in temps else (temps[0] if temps else None)
    clubes = (
        queries_stats.clubes_filtro(
            campeonato_id=campeonato_id, temporada=temp, pais=pais
        )
        if temp
        else []
    )
    return {
        "paises": paises,
        "pais": pais,
        "ligas": ligas,
        "campeonato_id": campeonato_id,
        "temporadas": temps,
        "temporada": temp,
        "clubes": clubes,
    }


@app.get("/api/ligas")
def api_ligas():
    return {"ligas": queries.listar_ligas()}


@app.get("/api/jogos")
def api_jogos(
    limite: int = Query(40, ge=1, le=200),
    campeonato_id: int | None = None,
):
    jogos = queries.ultimos_jogos(limite=limite, campeonato_id=campeonato_id)
    grupos = []
    mapa = {}
    for j in jogos:
        key = j["campeonato_id"]
        if key not in mapa:
            mapa[key] = {
                "campeonato_id": key,
                "campeonato": j.get("campeonato"),
                "pais": j.get("pais"),
                "logo": j.get("campeonato_logo"),
                "jogos": [],
            }
            grupos.append(mapa[key])
        mapa[key]["jogos"].append(j)
    return {"grupos": grupos, "total": len(jogos)}


@app.get("/api/jogo/{jogo_id}")
def api_jogo(jogo_id: int):
    detalhe = queries.detalhe_jogo(jogo_id)
    if not detalhe:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")
    return detalhe


@app.get("/api/liga/{campeonato_id}")
def api_liga(campeonato_id: int, temporada: str | None = None):
    dados = queries_liga.detalhe_liga(campeonato_id, temporada)
    if not dados:
        raise HTTPException(status_code=404, detail="Liga não encontrada")
    return dados


@app.get("/api/stats/meta")
def api_stats_meta(
    campeonato_id: int | None = None,
    temporada: str | None = None,
    pais: str | None = None,
    clube_id: int | None = None,
):
    paises = queries_stats.paises_com_dados()
    temps = queries_stats.temporadas_filtro(campeonato_id, pais, clube_id)
    temp = temporada if temporada in temps else (temps[0] if temps else None)
    ligas = queries_stats.ligas_filtro(pais, clube_id=clube_id, temporada=temp)
    if campeonato_id and not any(l["id"] == campeonato_id for l in ligas):
        campeonato_id = None
        temps = queries_stats.temporadas_filtro(None, pais, clube_id)
        temp = temporada if temporada in temps else (temps[0] if temps else None)
        ligas = queries_stats.ligas_filtro(pais, clube_id=clube_id, temporada=temp)
    clubes = (
        queries_stats.clubes_filtro(
            campeonato_id=campeonato_id, temporada=temp, pais=pais
        )
        if temp
        else []
    )
    if clube_id and not any(c["id"] == clube_id for c in clubes):
        clube_id = None
    return {
        "paises": paises,
        "pais": pais,
        "ligas": ligas,
        "campeonato_id": campeonato_id,
        "temporadas": temps,
        "temporada": temp,
        "clubes": clubes,
        "clube_id": clube_id,
        "grupos": queries_stats.GRUPOS_LABELS,
    }


@app.get("/api/stats/coletivas")
def api_stats_coletivas(
    campeonato_id: int | None = None,
    pais: str | None = None,
    temporada: str | None = None,
    grupo: str = "ataque",
    clubes: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
    ordenar: str | None = None,
    ordem: str = "desc",
    clube_id: int | None = None,
    mando: str | None = None,
):
    if grupo == "finalizacoes":
        return queries_stats.finalizacoes_clubes(
            temporada=temporada,
            campeonato_id=campeonato_id,
            pais=pais,
            ordenar=ordenar,
            ordem=ordem,
            page=page,
            page_size=page_size,
            clube_id=clube_id,
            mando=mando,
        )
    ids = None
    if clubes:
        ids = []
        for p in clubes.split(","):
            p = p.strip()
            if p.isdigit():
                ids.append(int(p))
        ids = ids[:5]
        if not ids:
            raise HTTPException(status_code=400, detail="Selecione ao menos 1 clube")
    return queries_stats.coletivas_tabela(
        campeonato_id=campeonato_id,
        pais=pais,
        temporada=temporada,
        grupo=grupo,
        clube_ids=ids,
        page=page,
        page_size=page_size,
        ordenar=ordenar,
        ordem=ordem,
        mando=mando,
        clube_id=clube_id,
    )


@app.get("/api/stats/finalizacoes")
def api_stats_finalizacoes(
    escopo: str = Query("jogador", pattern="^(clube|jogador|mapa)$"),
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
    ordenar: str | None = None,
    ordem: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
    limite: int = Query(50, ge=5, le=200),
    clube_id: int | None = None,
    jogador_id: int | None = None,
    mando: str | None = None,
):
    if escopo == "clube":
        return queries_stats.finalizacoes_clubes(
            temporada=temporada,
            campeonato_id=campeonato_id,
            pais=pais,
            ordenar=ordenar,
            ordem=ordem,
            page=page,
            page_size=page_size,
            clube_id=clube_id,
            mando=mando,
        )
    if escopo == "mapa":
        return {
            "mapa": queries_stats.finalizacoes_mapa(
                temporada=temporada,
                campeonato_id=campeonato_id,
                pais=pais,
                clube_id=clube_id,
                jogador_id=jogador_id,
                mando=mando,
            )
        }
    return queries_stats.finalizacoes_jogadores(
        temporada=temporada,
        campeonato_id=campeonato_id,
        pais=pais,
        ordenar=ordenar,
        ordem=ordem,
        limite=limite,
        jogador_id=jogador_id,
        clube_id=clube_id,
        mando=mando,
    )


@app.get("/api/stats/finalizacoes-sofridas")
def api_stats_finalizacoes_sofridas(
    escopo: str = Query("clube", pattern="^(clube|mapa)$"),
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
    mando: str = "todos",
    clube_id: int | None = None,
    mapa_clube_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
    ordenar: str = "gols",
    ordem: str = "desc",
):
    if escopo == "mapa" and not clube_id:
        return {"mapa": []}
    return queries_finalizacoes_sofridas.consultar(
        escopo=escopo, temporada=temporada, campeonato_id=campeonato_id,
        pais=pais, mando=mando, clube_id=clube_id,
        mapa_clube_id=mapa_clube_id, page=page, page_size=page_size,
        ordenar=ordenar, ordem=ordem,
    )


@app.get("/api/stats/individuais")
def api_stats_individuais(
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
    metrica: str = "gols",
    limite: int = Query(50, ge=5, le=200),
    posicao: str | None = None,
    clube_id: int | None = None,
    nacionalidade: str | None = None,
    ordenar: str | None = None,
    ordem: str = "desc",
    mando: str | None = None,
):
    return {
        "itens": queries_stats.individuais_ranking(
            temporada=temporada,
            campeonato_id=campeonato_id,
            pais=pais,
            metrica=metrica,
            limite=limite,
            posicao=posicao,
            clube_id=clube_id,
            nacionalidade=nacionalidade,
            ordenar=ordenar,
            ordem=ordem,
            mando=mando,
        ),
        "filtros": queries_stats.individuais_filtros(temporada, campeonato_id, pais),
    }


@app.get("/api/stats/tecnicos")
def api_stats_tecnicos(
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
    ordenar: str | None = None,
    ordem: str = "desc",
    mando: str | None = None,
):
    return {
        "itens": queries_stats.tecnicos_ranking(
            temporada=temporada,
            campeonato_id=campeonato_id,
            pais=pais,
            ordenar=ordenar,
            ordem=ordem,
            mando=mando,
        )
    }


@app.get("/api/stats/arbitros")
def api_stats_arbitros(
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
    ordenar: str | None = None,
    ordem: str = "desc",
):
    return {
        "itens": queries_stats.arbitros_ranking(
            temporada=temporada,
            campeonato_id=campeonato_id,
            pais=pais,
            ordenar=ordenar,
            ordem=ordem,
        )
    }


class EntidadePatch(BaseModel):
    nome: str | None = None
    foto: str | None = None


@app.get("/api/clube/{clube_id}")
def api_clube(
    clube_id: int,
    temporada: str | None = None,
    aba: str = "geral",
    comparar_id: int | None = None,
    grupo: str = "ataque",
    campeonato_id: int | None = None,
    mando: str | None = None,
):
    dados = queries_clube.detalhe_clube(
        clube_id,
        temporada=temporada,
        aba=aba,
        comparar_id=comparar_id,
        grupo=grupo,
        campeonato_id=campeonato_id,
        mando=mando,
    )
    if not dados:
        raise HTTPException(status_code=404, detail="Clube não encontrado")
    return dados


@app.get("/api/clube/{clube_id}/fundamentos")
def api_clube_fundamentos(
    clube_id: int, temporada: str,
    campeonato_id: int | None = None, mando: str = "todos",
):
    return queries_performance.fundamentos_clube(
        clube_id, temporada, campeonato_id=campeonato_id, mando=mando
    )


@app.get("/api/jogador/{jogador_id}")
def api_jogador(jogador_id: int, temporada: str | None = None):
    dados = queries_entidade.detalhe_jogador(jogador_id, temporada=temporada)
    if not dados:
        raise HTTPException(status_code=404, detail="Jogador não encontrado")
    return dados


@app.get("/api/tecnico/{tecnico_id}/estatisticas-avancadas")
def api_tecnico_estatisticas_avancadas(
    tecnico_id: int,
    temporada: str = Query(..., min_length=1),
):
    return queries_tecnico_avancadas.estatisticas_tecnico(tecnico_id, temporada)


@app.get("/api/tecnico/{tecnico_id}")
def api_tecnico(tecnico_id: int, temporada: str | None = None):
    dados = queries_entidade.detalhe_tecnico(tecnico_id, temporada=temporada)
    if not dados:
        raise HTTPException(status_code=404, detail="Técnico não encontrado")
    return dados


@app.get("/api/arbitro/{arbitro_id}")
def api_arbitro(arbitro_id: int, temporada: str | None = None):
    dados = queries_entidade.detalhe_arbitro(arbitro_id, temporada=temporada)
    if not dados:
        raise HTTPException(status_code=404, detail="Árbitro não encontrado")
    return dados


@app.patch("/api/entidade/{tipo}/{entidade_id}")
def api_patch_entidade(tipo: str, entidade_id: int, body: EntidadePatch):
    if tipo not in ("clube", "jogador", "tecnico", "arbitro"):
        raise HTTPException(status_code=400, detail="Tipo inválido")
    if body.nome is None and body.foto is None:
        raise HTTPException(status_code=400, detail="Informe nome ou foto")
    try:
        ok = queries_entidade.atualizar_entidade(
            tipo, entidade_id, nome=body.nome, foto=body.foto
        )
    except queries_entidade.EntidadeEditError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e
    if not ok:
        raise HTTPException(status_code=404, detail="Entidade não encontrada")
    return {"ok": True}


@app.middleware("http")
async def cache_static(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=300"
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
