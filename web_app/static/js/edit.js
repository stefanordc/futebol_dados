/** Modal de edição de nome/foto na tabela raiz. */

export function pencilBtn(extraClass = "") {
  return `<button type="button" class="edit-pencil ${extraClass}" title="Editar" aria-label="Editar">✎</button>`;
}

export function openEditModal({ tipo, id, nome, foto, onSaved }) {
  const prev = document.querySelector(".edit-modal-backdrop");
  if (prev) prev.remove();

  const hasFoto = tipo === "jogador" || tipo === "arbitro";
  const backdrop = document.createElement("div");
  backdrop.className = "edit-modal-backdrop";
  backdrop.innerHTML = `
    <div class="edit-modal" role="dialog" aria-modal="true">
      <h3>Editar ${tipo}</h3>
      <label>Nome
        <input type="text" id="edit-nome" value="${(nome || "").replace(/"/g, "&quot;")}" />
      </label>
      ${
        hasFoto
          ? `<label>URL da foto
        <input type="url" id="edit-foto" value="${(foto || "").replace(/"/g, "&quot;")}" />
      </label>`
          : ""
      }
      <div class="edit-actions">
        <button type="button" class="chip-btn" data-cancel>Cancelar</button>
        <button type="button" class="chip-btn on" data-save>Salvar</button>
      </div>
      <p class="edit-err" hidden></p>
    </div>`;
  document.body.appendChild(backdrop);

  const close = () => backdrop.remove();
  backdrop.querySelector("[data-cancel]").addEventListener("click", close);
  backdrop.addEventListener("click", (ev) => {
    if (ev.target === backdrop) close();
  });
  backdrop.querySelector("[data-save]").addEventListener("click", async () => {
    const novoNome = backdrop.querySelector("#edit-nome").value.trim();
    const err = backdrop.querySelector(".edit-err");
    if (!novoNome) {
      err.hidden = false;
      err.textContent = "Nome obrigatório.";
      return;
    }
    const body = { nome: novoNome };
    if (hasFoto) {
      const f = backdrop.querySelector("#edit-foto")?.value?.trim();
      body.foto = f || null;
    }
    try {
      const res = await fetch(`/api/entidade/${tipo}/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        let detail = "Falha ao salvar";
        try {
          const data = await res.json();
          if (data?.detail) detail = typeof data.detail === "string" ? data.detail : detail;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      close();
      if (onSaved) await onSaved(body);
    } catch (e) {
      err.hidden = false;
      err.textContent = e.message || "Erro";
    }
  });
}
