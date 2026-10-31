const $ = (sel, el = document) => el.querySelector(sel);

function jogoIdFromUrl() {
  const m = location.pathname.match(/\/jogo\/(\d+)/);
  return m ? Number(m[1]) : null;
}

function n(v, dig = 0) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("pt-BR", {
    minimumFractionDigits: dig,
    maximumFractionDigits: dig,
  });
}

function pct(a, b) {
  const t = (Number(a) || 0) + (Number(b) || 0);
  if (!t) return [50, 50];
  const left = Math.round((100 * Number(a || 0)) / t);
  return [left, 100 - left];
}

function winnerPill(casa, fora, dig = 0) {
  const c = Number(casa);
  const f = Number(fora);
  const cs = n(casa, dig);
  const fs = n(fora, dig);
  if (casa == null && fora == null) {
    return [`<span class="cmp-val left">—</span>`, `<span class="cmp-val right">—</span>`];
  }
  if (!Number.isNaN(c) && !Number.isNaN(f) && c > f) {
    return [`<span class="cmp-val left"><span class="pill">${cs}</span></span>`, `<span class="cmp-val right">${fs}</span>`];
  }
  if (!Number.isNaN(c) && !Number.isNaN(f) && f > c) {
    return [`<span class="cmp-val left">${cs}</span>`, `<span class="cmp-val right"><span class="pill fora-win">${fs}</span></span>`];
  }
  return [
    `<span class="cmp-val left"><span class="pill soft">${cs}</span></span>`,
    `<span class="cmp-val right"><span class="pill soft">${fs}</span></span>`,
  ];
}

function cmp(label, casa, fora, dig = 0) {
  const [l, r] = winnerPill(casa, fora, dig);
  return `<div class="cmp-row">${l}<div class="label">${label}</div>${r}</div>`;
}

function fmtData(iso) {
  if (!iso) return "";
  const d = new Date(iso + (iso.length === 10 ? "T12:00:00" : ""));
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
}

function logo(src, size = 20) {
  if (!src) return "";
  return `<img src="${src}" alt="" style="width:${size}px;height:${size}px;object-fit:contain" onerror="this.style.opacity=.15" />`;
}

function linkClube(id, nome, extraClass = "entity-link") {
  if (!nome) return "—";
  if (!id) return `<span>${nome}</span>`;
  return `<a class="${extraClass}" href="/clube/${id}">${nome}</a>`;
}

function linkJogador(id, nome, extraClass = "entity-link") {
  if (!nome) return "—";
  if (!id) return `<span>${nome}</span>`;
  return `<a class="${extraClass}" href="/jogador/${id}">${nome}</a>`;
}

function linkTecnico(id, nome, extraClass = "entity-link coach-link") {
  if (!nome) return "";
  if (!id) return `<span class="${extraClass}">${nome}</span>`;
  return `<a class="${extraClass}" href="/tecnico/${id}">${nome}</a>`;
}

function linkArbitro(id, nome, extraClass = "entity-link") {
  if (!nome) return "—";
  if (!id) return `<span>${nome}</span>`;
  return `<a class="${extraClass}" href="/arbitro/${id}">${nome}</a>`;
}

function shotFiltroClass(tipo) {
  const t = (tipo || "").toLowerCase();
  if (t.includes("gol")) return "gol";
  if (t === "defendida" || t.includes("defend")) return "certa";
  return "errada";
}

function ratingClass(r, motm) {
  if (motm) return "motm";
  if (r == null) return "mid";
  if (r >= 7.5) return "";
  if (r >= 6.5) return "mid";
  return "low";
}

function shotClass(tipo, mando) {
  const t = (tipo || "").toLowerCase();
  let base = "parafora";
  if (t.includes("gol")) base = "gol";
  else if (t.includes("defend")) base = "defendida";
  else if (t.includes("bloque")) base = "bloqueada";
  else if (t.includes("trave")) base = "trave";
  return `${base}${mando === "Fora" ? " fora" : ""}`;
}

/** Converte coords FotMob (metros 105×68) para campo vertical: casa ataca cima. */
function shotPos(f) {
  const x = Number(f.coordenada_x);
  const y = Number(f.coordenada_y);
  if (Number.isNaN(x) || Number.isNaN(y)) return null;
  const left = (100 * y) / 68;
  const topFromGoal = (100 * (105 - x)) / 105;
  if (f.mando === "Casa") {
    return { left, top: topFromGoal };
  }
  return { left: 100 - left, top: 100 - topFromGoal };
}

function minutoLabel(g) {
  if (g.minuto == null) return "—";
  return g.minuto_adicional != null ? `${g.minuto}+${g.minuto_adicional}'` : `${g.minuto}'`;
}

function minutoPct(g) {
  const base = Number(g.minuto) || 0;
  const add = Number(g.minuto_adicional) || 0;
  // escala ~0–95' + acréscimos no fim
  const t = Math.min(98, base + Math.min(add, 8) * 0.4);
  return Math.max(2, Math.min(98, (t / 95) * 100));
}

function sectionTimeline(gols, jogo) {
  const gc = Number(jogo.gols_casa) || 0;
  const gf = Number(jogo.gols_fora) || 0;
  if (gc === 0 && gf === 0) return "";
  if (!gols?.length) return "";

  const events = gols
    .map((g) => {
      const lado = g.foi_gol_contra
        ? g.mando === "Casa"
          ? "fora"
          : "casa"
        : g.mando === "Casa"
          ? "casa"
          : "fora";
      return `<div class="timeline-event ${lado}" style="left:${minutoPct(g)}%" title="${g.jogador || ""}">
        <div class="min">${minutoLabel(g)} · ${g.placar_casa}-${g.placar_fora}</div>
        <div class="ball"></div>
      </div>`;
    })
    .join("");

  const legend = gols
    .map(
      (g) =>
        `<span><strong>${minutoLabel(g)}</strong> ${linkJogador(g.jogador_id, g.jogador || "Gol")}${g.foi_gol_contra ? " (GC)" : ""} · ${g.placar_casa}-${g.placar_fora}</span>`
    )
    .join("");

  return `
    <div class="timeline">
      <div style="display:flex;justify-content:space-between;padding:0 .5rem;font-weight:700;font-size:.9rem">
        <span>${logo(jogo.casa_logo, 18)} ${linkClube(jogo.casa_id, jogo.casa)}</span>
        <span>${linkClube(jogo.fora_id, jogo.fora)} ${logo(jogo.fora_logo, 18)}</span>
      </div>
      <div class="timeline-track">
        <div class="timeline-line"></div>
        <div class="timeline-ht" title="Intervalo"></div>
        ${events}
      </div>
      <div class="timeline-legend">${legend}</div>
    </div>`;
}

function sectionPrincipais(casa, fora, jogo) {
  const [pc, pf] = [
    Number(casa?.posse_bola) || 0,
    Number(fora?.posse_bola) || 0,
  ];
  return `
    <section class="section" data-sec="principais">
      <h2>Estatísticas principais</h2>
      ${sectionTimeline(jogo.gols, jogo)}
      <div class="cmp-teams">
        <div>${logo(jogo.casa_logo, 22)} ${linkClube(jogo.casa_id, jogo.casa)}</div>
        <div>${linkClube(jogo.fora_id, jogo.fora)} ${logo(jogo.fora_logo, 22)}</div>
      </div>
      <div class="stat-main">
        <div class="posse-row">
          <div class="posse-labels"><span>${pc}%</span><span>Posse de bola</span><span>${pf}%</span></div>
          <div class="posse-bar">
            <div class="casa" style="width:${pc}%"></div>
            <div class="fora" style="width:${pf}%"></div>
          </div>
        </div>
        ${cmp("Gols esperados (xG)", casa?.xg, fora?.xg, 2)}
        ${cmp("Total de chutes", casa?.total_chutes, fora?.total_chutes)}
        ${cmp("Toques na área adversária", casa?.toques_area_adversaria, fora?.toques_area_adversaria)}
      </div>
    </section>`;
}

function sectionDetalhes(casa, fora, jogo) {
  return `
    <section class="section" data-sec="detalhes">
      <h2>Estatísticas detalhadas</h2>
      <div class="cmp-teams">
        <div>${logo(jogo.casa_logo, 22)} ${linkClube(jogo.casa_id, jogo.casa)}</div>
        <div>${linkClube(jogo.fora_id, jogo.fora)} ${logo(jogo.fora_logo, 22)}</div>
      </div>
      <div class="stats-grid">
        <div class="stats-box">
          <h3>Gols esperados</h3>
          ${cmp("Gols esperados (xG)", casa?.xg, fora?.xg, 2)}
          ${cmp("xG jogada normal", casa?.xg_jogada_normal, fora?.xg_jogada_normal, 2)}
          ${cmp("xG jogada ensaiada", casa?.xg_jogada_ensaiada, fora?.xg_jogada_ensaiada, 2)}
          ${cmp("xG sem pênaltis", casa?.xg_sem_penalti, fora?.xg_sem_penalti, 2)}
          ${cmp("xG no alvo (xGOT)", casa?.xgot, fora?.xgot, 2)}
        </div>
        <div class="stats-box">
          <h3>Chutes</h3>
          ${cmp("Total de chutes", casa?.total_chutes, fora?.total_chutes)}
          ${cmp("Finalizações fora do gol", casa?.chutes_fora, fora?.chutes_fora)}
          ${cmp("Finalizações no gol", casa?.chutes_certos, fora?.chutes_certos)}
          ${cmp("Chutes bloqueados", casa?.chutes_bloqueados, fora?.chutes_bloqueados)}
          ${cmp("Chutes na trave", casa?.chutes_trave, fora?.chutes_trave)}
          ${cmp("Chutes dentro da área", casa?.chutes_dentro_area, fora?.chutes_dentro_area)}
          ${cmp("Chutes de fora da área", casa?.chutes_fora_area, fora?.chutes_fora_area)}
        </div>
        <div class="stats-box">
          <h3>Passes</h3>
          ${cmp("Passes", casa?.passes, fora?.passes)}
          ${cmp("Passes certos", casa?.passes_certos, fora?.passes_certos)}
          ${cmp("Passes longos", casa?.passes_longos, fora?.passes_longos)}
          ${cmp("Cruzamentos", casa?.cruzamentos, fora?.cruzamentos)}
        </div>
        <div class="stats-box">
          <h3>Defesa</h3>
          ${cmp("Desarmes", casa?.desarmes, fora?.desarmes)}
          ${cmp("Interceptações", casa?.interceptacoes, fora?.interceptacoes)}
          ${cmp("Bloqueios", casa?.bloqueios, fora?.bloqueios)}
          ${cmp("Bolas afastadas", casa?.bolas_afastadas, fora?.bolas_afastadas)}
          ${cmp("Defesas do goleiro", casa?.defesas_goleiro, fora?.defesas_goleiro)}
        </div>
      </div>
    </section>`;
}

function sectionShotmap(finais, jogo) {
  const dots = finais
    .map((f, i) => {
      const pos = shotPos(f);
      if (!pos) return "";
      const color = f.mando === "Casa" ? "var(--casa)" : "#fff";
      const filtro = shotFiltroClass(f.tipo_evento);
      return `<button type="button" class="shot-dot ${shotClass(f.tipo_evento, f.mando)}"
        data-i="${i}" data-filtro="${filtro}" style="left:${pos.left}%;top:${pos.top}%;color:${color}"
        title="${f.jogador || ""} · ${f.tipo_evento || ""}"></button>`;
    })
    .join("");

  return `
    <section class="section" data-sec="finalizacoes">
      <h2>Mapa de chutes</h2>
      <div class="modo-toggle shot-filtros" id="shot-filtros">
        <button type="button" class="chip-btn on" data-shot-filtro="todos">Todas</button>
        <button type="button" class="chip-btn" data-shot-filtro="gol">Gols</button>
        <button type="button" class="chip-btn" data-shot-filtro="certa">Certas</button>
        <button type="button" class="chip-btn" data-shot-filtro="errada">Erradas</button>
      </div>
      <div class="shot-layout">
        <div class="shot-detail" id="shot-detail">
          <div class="empty" style="padding:1rem 0">Clique em uma finalização no campo.</div>
        </div>
        <div>
          <div class="pitch-wrap" id="pitch">
            <div class="pitch-lines">
              <div class="halfway"></div>
              <div class="circle"></div>
              <div class="box top"></div>
              <div class="box bottom"></div>
            </div>
            ${dots}
          </div>
          <div style="display:flex;justify-content:space-between;margin-top:.5rem;color:var(--muted);font-size:.8rem">
            <span>${linkClube(jogo.casa_id, jogo.casa)} (cima)</span>
            <span>${linkClube(jogo.fora_id, jogo.fora)} (baixo)</span>
          </div>
        </div>
      </div>
    </section>`;
}

function renderShotDetail(f) {
  if (!f) return;
  const minuto =
    f.minuto_adicional != null
      ? `${f.minuto} + ${f.minuto_adicional}'`
      : f.minuto != null
        ? `${f.minuto}'`
        : "—";
  const gx = f.local_x_gol != null ? Math.min(95, Math.max(5, Number(f.local_x_gol))) : null;
  const gz = f.altura_z_gol != null ? Math.min(90, Math.max(8, 100 - Number(f.altura_z_gol) * 12)) : null;
  $("#shot-detail").innerHTML = `
    <div class="player">
      ${f.jogador_foto ? `<img src="${f.jogador_foto}" alt="" />` : `<div style="width:44px;height:44px;border-radius:50%;background:#333"></div>`}
      <div>
        <strong>${linkJogador(f.jogador_id, f.jogador || "Jogador")}</strong>
        <div style="color:var(--muted);font-size:.85rem">${minuto} · ${linkClube(f.clube_id, f.clube || f.mando || "")}</div>
      </div>
    </div>
    <div class="shot-kv">
      <div><span>Tipo de chute</span><strong>${f.tipo_finalizacao || "—"}</strong></div>
      <div><span>Situação</span><strong>${f.situacao_jogada || "—"}</strong></div>
      <div><span>Resultado</span><strong>${f.tipo_evento || "—"}</strong></div>
    </div>
    <div class="goal-mini">${gx != null && gz != null ? `<span class="goal-dot" style="left:${gx}%;bottom:${gz}%"></span>` : ""}</div>
    <div class="shot-kv">
      <div><span>xG</span><strong>${n(f.xg, 2)}</strong></div>
      <div><span>xGOT</span><strong>${n(f.xgot, 2)}</strong></div>
    </div>`;
}

function ocupacaoHtml(jogo) {
  const pub = Number(jogo.publico);
  const cap = Number(jogo.capacidade);
  if (!pub || !cap || cap <= 0) return "";
  const pctOcup = Math.max(0, Math.min(100, (100 * pub) / cap));
  return `
    <div class="ocupacao">
      <div class="ocupacao-ring-wrap">
        <div class="ocupacao-ring" style="--p:${pctOcup.toFixed(1)}"></div>
        <span>${pctOcup.toFixed(0)}%</span>
      </div>
      <div>
        <h3>Taxa de ocupação</h3>
        <p>${n(pub)} presentes de ${n(cap)} lugares</p>
        <div class="ocupacao-bar"><i style="width:${pctOcup}%"></i></div>
      </div>
    </div>`;
}

function sectionInfo(jogo) {
  const arb = jogo.arbitro_stats || {};
  return `
    <section class="section" data-sec="info">
      <h2>Informações do jogo</h2>
      <div class="info-grid">
        <div class="info-row"><span class="info-ico">📍</span><div><strong>${jogo.estadio || "Estádio não informado"}</strong></div></div>
        <div class="info-row"><span class="info-ico">👥</span><div>Capacidade <strong>${n(jogo.capacidade)}</strong></div></div>
        <div class="info-row"><span class="info-ico">🎟</span><div>Público <strong>${n(jogo.publico)}</strong></div></div>
        ${ocupacaoHtml(jogo)}
        <div class="info-row"><span class="info-ico">📅</span><div>${fmtData(jogo.data)} · ${jogo.rodada || ""} · ${jogo.temporada || ""}</div></div>
      </div>
      ${
        jogo.arbitro
          ? `<div class="arb-card">
              ${jogo.arbitro_foto ? `<img src="${jogo.arbitro_foto}" alt="" />` : `<div style="width:52px;height:52px;border-radius:50%;background:#333"></div>`}
              <div>
                <strong>${linkArbitro(jogo.arbitro_id, jogo.arbitro)}</strong>
                <div style="color:var(--muted);font-size:.85rem">${jogo.arbitro_pais || "Árbitro"} · ${jogo.campeonato || ""}</div>
              </div>
            </div>
            <div class="arb-stats">
              <div class="arb-stat"><div class="n">${n(arb.amarelos_por_jogo, 1)}</div><div class="t">Cartões amarelos / jogo</div></div>
              <div class="arb-stat"><div class="n">${n(arb.faltas_por_jogo, 1)}</div><div class="t">Faltas / jogo</div></div>
            </div>`
          : ""
      }
    </section>`;
}

function fisicoPctZoom(valor, min, max) {
  // Escala ampliada em torno dos dois valores: diferença pequena (ex.: 0,44 km)
  // ocupa fatia visível da barra, em vez de sumir numa escala 0→max.
  const span = Math.max(max - min, 0);
  const pad = Math.max(span * 2.5, max * 0.02, 0.01);
  const baseline = Math.max(0, min - pad);
  const range = Math.max(max - baseline, 0.01);
  return Math.max(8, Math.min(100, Math.round((100 * (valor - baseline)) / range)));
}

function fisicoBar(label, casaVal, foraVal, dig, unidade, jogo) {
  const cOk = casaVal != null && casaVal !== "" && Number.isFinite(Number(casaVal));
  const fOk = foraVal != null && foraVal !== "" && Number.isFinite(Number(foraVal));
  const c = cOk ? Number(casaVal) : 0;
  const f = fOk ? Number(foraVal) : 0;
  const max = Math.max(c, f, 0.01);
  const min = Math.min(cOk ? c : max, fOk ? f : max);
  const pc = cOk ? fisicoPctZoom(c, min, max) : 0;
  const pf = fOk ? fisicoPctZoom(f, min, max) : 0;
  const diff = Math.abs(c - f);
  const liderCasa = cOk && fOk && c > f;
  const liderFora = cOk && fOk && f > c;
  const diffHtml =
    (liderCasa || liderFora) && diff > 0
      ? `<div class="fisico-diff">${n(diff, dig)}${unidade} a mais · ${
          liderCasa ? jogo.casa : jogo.fora
        }</div>`
      : "";

  const linha = (lado, nome, id, logoSrc, valOk, val, pct, lider) => `
    <div class="fisico-line ${lider ? "lider" : ""}">
      <div class="fisico-line-meta">
        ${logo(logoSrc, 22)}
        <span class="fisico-line-name">${linkClube(id, nome)}</span>
      </div>
      <div class="fisico-track" aria-hidden="true">
        <div class="fisico-fill ${lado}" style="width:${pct}%"></div>
      </div>
      <strong class="fisico-val">${valOk ? `${n(val, dig)}${unidade}` : "—"}</strong>
    </div>`;

  return `
    <div class="fisico-card">
      <div class="fisico-card-title">${label}</div>
      <div class="fisico-lines">
        ${linha("casa", jogo.casa, jogo.casa_id, jogo.casa_logo, cOk, casaVal, pc, liderCasa)}
        ${linha("fora", jogo.fora, jogo.fora_id, jogo.fora_logo, fOk, foraVal, pf, liderFora)}
      </div>
      ${diffHtml}
    </div>`;
}

function sectionFisicos(fisicos, jogo) {
  if (!fisicos?.encontrado) {
    return `
      <section class="section" data-sec="fisicos">
        <h2>Dados físicos</h2>
        <div class="fisicos-msg">${fisicos?.motivo || "Dados físicos indisponíveis."}</div>
      </section>`;
  }
  const casa = fisicos.casa || {};
  const fora = fisicos.fora || {};
  return `
    <section class="section" data-sec="fisicos">
      <h2>Dados físicos</h2>
      <p style="color:var(--muted);font-size:.85rem;margin:0 0 1rem">
        Distância e sprints no jogo completo${fisicos.origem === "cruzamento" ? " (cruzados com a coleta Sofascore)" : ""}.
      </p>
      <div class="fisico-grid">
        ${fisicoBar("Distância percorrida", casa.distancia_percorrida, fora.distancia_percorrida, 2, " km", jogo)}
        ${fisicoBar("Sprints", casa.sprints, fora.sprints, 0, "", jogo)}
      </div>
    </section>`;
}

function sectionOdds(odds, jogo) {
  if (!odds || (odds.odd_casa == null && odds.odd_empate == null && odds.odd_fora == null)) {
    return `
      <section class="section" data-sec="odds">
        <h2>Odds</h2>
        <div class="empty">Odds não disponíveis para este jogo.</div>
      </section>`;
  }
  const c = Number(odds.odd_casa);
  const e = Number(odds.odd_empate);
  const f = Number(odds.odd_fora);
  const inv = (x) => (x > 0 ? 1 / x : 0);
  const total = inv(c) + inv(e) + inv(f);
  const pct = (x) => (total ? Math.round((100 * inv(x)) / total) : 0);
  const minOdd = Math.min(c || 999, e || 999, f || 999);
  const pill = (val, isFav) =>
    `<div class="odd-box ${isFav ? "fav" : ""}"><div class="odd-n">${n(val, 2)}</div><div class="odd-p">${pct(val)}%</div></div>`;
  return `
    <section class="section" data-sec="odds">
      <h2>Odds 1X2</h2>
      <p style="color:var(--muted);font-size:.85rem;margin:0 0 1rem">Probabilidades implícitas a partir das odds.</p>
      <div class="odds-grid">
        <div class="odd-col">
          <div class="odd-label">${logo(jogo.casa_logo, 22)} ${linkClube(jogo.casa_id, jogo.casa)}</div>
          ${pill(c, c === minOdd)}
        </div>
        <div class="odd-col">
          <div class="odd-label">Empate</div>
          ${pill(e, e === minOdd)}
        </div>
        <div class="odd-col">
          <div class="odd-label">${linkClube(jogo.fora_id, jogo.fora)} ${logo(jogo.fora_logo, 22)}</div>
          ${pill(f, f === minOdd)}
        </div>
      </div>
    </section>`;
}

function playerNode(p, flipY = false) {
  const y = flipY ? 100 - (p.y || 50) : p.y || 50;
  const foto = p.foto ? `style="background-image:url('${p.foto}')"` : "";
  const r = p.rating;
  const key = p.jogador_id ?? p.id;
  const subIcon = p.saiu
    ? `<span class="sub-icon" title="Substituído" aria-label="Substituído"><span class="up">↑</span><span class="down">↓</span></span>`
    : "";
  const ratingHtml =
    r != null
      ? `<span class="rating ${ratingClass(r, p.motm)}">${n(r, 1)}${p.motm ? " ★" : ""}</span>`
      : "";
  return `
    <div class="player-node ${p.saiu ? "saiu" : ""}" style="left:${p.x}%;top:${y}%" data-player="${key}" role="button" tabindex="0">
      <div class="avatar-wrap">
        <div class="avatar" ${foto}>${ratingHtml}</div>
        ${subIcon}
      </div>
      <div class="label">${linkJogador(p.jogador_id, p.nome || "", "player-name-link")}</div>
    </div>`;
}

function sectionEscalacao(esc, jogo) {
  const casa = esc?.casa || { titulares: [], reservas: [] };
  const fora = esc?.fora || { titulares: [], reservas: [] };
  const entraram = (lista) => lista.filter((p) => p.entrou);
  const banco = (lista) => lista.filter((p) => !p.entrou);

  const chipEntrada = (p) => {
    const key = p.jogador_id ?? p.id;
    return `<button type="button" class="bench-chip entrou" data-player="${key}">
      ${p.foto ? `<img src="${p.foto}" alt="" />` : ""}
      <span class="bench-name">${linkJogador(p.jogador_id, p.nome || "", "player-name-link")}</span>
      ${p.rating != null ? `<span class="bench-rating ${ratingClass(p.rating)}">${n(p.rating, 1)}</span>` : ""}
      <span class="sub-icon in" title="Entrou">↑</span>
    </button>`;
  };
  const chipBanco = (p) => {
    const key = p.jogador_id ?? p.id;
    return `<span class="bench-chip muted-chip" data-player="${key}">${p.foto ? `<img src="${p.foto}" alt="" />` : ""}${linkJogador(p.jogador_id, p.nome || "", "player-name-link")}</span>`;
  };

  const lado = (bloco, clubeId, clubeNome, logoSrc, tecnicoId, tecnicoNome, flip) => `
    <div>
      <div class="lineup-head">
        ${logo(logoSrc, 22)}
        <strong>${linkClube(clubeId, clubeNome)}</strong>
        ${
          tecnicoNome
            ? `<span class="coach-badge">Téc. ${linkTecnico(tecnicoId, tecnicoNome)}</span>`
            : ""
        }
      </div>
      <div class="lineup-pitch">
        <div class="mid"></div>
        ${(bloco.titulares || []).map((p) => playerNode(p, flip)).join("")}
      </div>
      ${
        entraram(bloco.reservas || []).length
          ? `<div class="subs-in">
              <div class="subs-label">Entraram</div>
              <div class="bench">${entraram(bloco.reservas || []).map(chipEntrada).join("")}</div>
            </div>`
          : ""
      }
      ${
        banco(bloco.reservas || []).length
          ? `<div class="bench">${banco(bloco.reservas || []).map(chipBanco).join("")}</div>`
          : ""
      }
    </div>`;

  return `
    <section class="section" data-sec="escalacao">
      <h2>Escalação</h2>
      <p style="color:var(--muted);font-size:.85rem;margin:0 0 1rem">
        Clique em um jogador para ver as estatísticas da partida. ↑↓ = saiu · ↑ = entrou.
      </p>
      <div class="lineup-grid">
        ${lado(casa, jogo.casa_id, jogo.casa, jogo.casa_logo, jogo.tecnico_casa_id, jogo.tecnico_casa, false)}
        ${lado(fora, jogo.fora_id, jogo.fora, jogo.fora_logo, jogo.tecnico_fora_id, jogo.tecnico_fora, true)}
      </div>
    </section>`;
}

const PLAYER_STAT_ROWS = [
  ["gols", "Gols"],
  ["assistencias", "Assistências"],
  ["toques_bolas", "Toques"],
  ["passes_certos", "Passes certos"],
  ["cruzamentos", "Cruzamentos"],
  ["dribles", "Dribles"],
  ["disputas_aereas", "Duelos aéreos"],
  ["desarmes", "Desarmes"],
  ["interceptacoes", "Interceptações"],
  ["dribles_sofridos", "Dribles sofridos"],
  ["faltas_cometidas", "Faltas cometidas"],
  ["impedimentos", "Impedimentos"],
  ["chutes_total", "Chutes"],
  ["chutes_certos", "Chutes no gol"],
  ["xg", "xG", 2],
  ["xa", "xA", 2],
  ["rating", "Nota", 1],
];

function maxBar(players, key) {
  let m = 0;
  for (const p of players) {
    const v = Number(p[key]);
    if (!Number.isNaN(v)) m = Math.max(m, v);
  }
  return m || 1;
}

function openPlayerModal(player, allPlayers) {
  const existing = $("#player-modal");
  if (existing) existing.remove();
  const rows = PLAYER_STAT_ROWS.map(([key, label, dig = 0]) => {
    const val = player[key];
    if (val == null) return "";
    const w = Math.round((100 * Number(val)) / maxBar(allPlayers, key));
    return `<div class="pstat"><span>${label}</span><strong>${n(val, dig)}</strong><div class="bar"><i style="width:${w}%"></i></div></div>`;
  }).join("");

  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.id = "player-modal";
  backdrop.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true">
      <div class="modal-head">
        ${player.foto ? `<img src="${player.foto}" alt="" />` : `<div style="width:56px;height:56px;border-radius:50%;background:#333"></div>`}
        <div>
          <strong style="font-size:1.05rem">${linkJogador(player.jogador_id, player.nome || "Jogador")}</strong>
          <div style="color:var(--muted);font-size:.85rem">${linkClube(player.clube_id, player.clube || player.mando || "")} · ${player.posicao || ""} · ${n(player.minutos)}'</div>
        </div>
        ${player.rating != null ? `<div class="rating-lg ${ratingClass(player.rating, player.motm)}">${n(player.rating, 1)}</div>` : ""}
        <button class="modal-close" type="button" aria-label="Fechar">✕</button>
      </div>
      ${rows || `<div class="empty">Sem estatísticas individuais.</div>`}
    </div>`;
  document.body.appendChild(backdrop);
  const close = () => backdrop.remove();
  backdrop.addEventListener("click", (ev) => {
    if (ev.target === backdrop || ev.target.closest(".modal-close")) close();
  });
}

function flattenPlayers(esc) {
  const out = [];
  for (const lado of ["casa", "fora"]) {
    const bloco = esc?.[lado] || {};
    for (const p of [...(bloco.titulares || []), ...(bloco.reservas || [])]) out.push(p);
  }
  return out;
}

function render(jogo) {
  const casa = jogo.estatisticas?.completo?.Casa || {};
  const fora = jogo.estatisticas?.completo?.Fora || {};
  const finais = jogo.finalizacoes || [];
  const players = flattenPlayers(jogo.escalacao);
  const byId = Object.fromEntries(players.map((p) => [String(p.jogador_id ?? p.id), p]));

  $("#conteudo").innerHTML = `
    <div class="match-hero">
      <div class="match-league">
        ${logo(jogo.campeonato_logo, 18)}
        <span>${jogo.pais ? `${jogo.pais} — ` : ""}${jogo.campeonato || ""}</span>
      </div>
      <div class="scoreboard">
        <div class="team-side">
          <a href="/clube/${jogo.casa_id}">${logo(jogo.casa_logo, 64)}</a>
          <div class="name">${linkClube(jogo.casa_id, jogo.casa)}</div>
        </div>
        <div class="score-big">${jogo.gols_casa ?? "-"} - ${jogo.gols_fora ?? "-"}</div>
        <div class="team-side">
          <a href="/clube/${jogo.fora_id}">${logo(jogo.fora_logo, 64)}</a>
          <div class="name">${linkClube(jogo.fora_id, jogo.fora)}</div>
        </div>
      </div>
      <div class="match-meta">${fmtData(jogo.data)} · ${jogo.rodada || ""} · ${jogo.temporada || ""}</div>
    </div>

    <div class="tabs" id="tabs">
      <button class="tab active" data-tab="principais" type="button">Principais</button>
      <button class="tab" data-tab="detalhes" type="button">Estatísticas</button>
      <button class="tab" data-tab="fisicos" type="button">Dados Físicos</button>
      <button class="tab" data-tab="odds" type="button">Odds</button>
      <button class="tab" data-tab="finalizacoes" type="button">Finalizações</button>
      <button class="tab" data-tab="escalacao" type="button">Escalação</button>
      <button class="tab" data-tab="info" type="button">Informações</button>
    </div>

    ${sectionPrincipais(casa, fora, jogo)}
    ${sectionDetalhes(casa, fora, jogo)}
    ${sectionFisicos(jogo.dados_fisicos, jogo)}
    ${sectionOdds(jogo.odds, jogo)}
    ${sectionShotmap(finais, jogo)}
    ${sectionEscalacao(jogo.escalacao, jogo)}
    ${sectionInfo(jogo)}
  `;

  document.title = `${jogo.casa} ${jogo.gols_casa ?? ""}-${jogo.gols_fora ?? ""} ${jogo.fora}`;

  const secs = [...document.querySelectorAll("[data-sec]")];
  function showTab(name) {
    secs.forEach((s) => s.classList.toggle("hidden", s.dataset.sec !== name));
    document.querySelectorAll("#tabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  }
  showTab("principais");
  $("#tabs").addEventListener("click", (ev) => {
    const btn = ev.target.closest(".tab");
    if (btn) showTab(btn.dataset.tab);
  });

  const pitch = $("#pitch");
  if (pitch) {
    pitch.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".shot-dot");
      if (!btn || btn.classList.contains("shot-hidden")) return;
      pitch.querySelectorAll(".shot-dot").forEach((d) => d.classList.remove("active"));
      btn.classList.add("active");
      renderShotDetail(finais[Number(btn.dataset.i)]);
      showTab("finalizacoes");
    });
    const firstGol = finais.findIndex((f) => (f.tipo_evento || "").toLowerCase().includes("gol"));
    const idx = firstGol >= 0 ? firstGol : 0;
    if (finais[idx]) {
      const btn = pitch.querySelector(`.shot-dot[data-i="${idx}"]`);
      if (btn) {
        btn.classList.add("active");
        renderShotDetail(finais[idx]);
      }
    }
  }

  $("#shot-filtros")?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-shot-filtro]");
    if (!btn || !pitch) return;
    const f = btn.dataset.shotFiltro;
    document.querySelectorAll("#shot-filtros .chip-btn").forEach((b) => b.classList.toggle("on", b === btn));
    pitch.querySelectorAll(".shot-dot").forEach((dot) => {
      const df = dot.dataset.filtro;
      // Certas = no gol (gols + defendidas)
      const show =
        f === "todos" ||
        df === f ||
        (f === "certa" && (df === "certa" || df === "gol"));
      dot.classList.toggle("shot-hidden", !show);
    });
  });

  document.querySelectorAll("[data-player]").forEach((el) => {
    el.addEventListener("click", (ev) => {
      if (ev.target.closest("a")) return;
      ev.preventDefault();
      const p = byId[String(el.dataset.player)];
      if (p) openPlayerModal(p, players);
    });
  });
}

async function init() {
  const id = jogoIdFromUrl();
  if (!id) {
    $("#conteudo").innerHTML = `<div class="error">Jogo inválido.</div>`;
    return;
  }
  try {
    const res = await fetch(`/api/jogo/${id}`);
    if (!res.ok) throw new Error(res.status === 404 ? "Jogo não encontrado" : "Falha ao carregar");
    render(await res.json());
  } catch (e) {
    $("#conteudo").innerHTML = `<div class="error">${e.message}</div>`;
  }
}

init();
