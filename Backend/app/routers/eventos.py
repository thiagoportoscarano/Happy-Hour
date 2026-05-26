"""
app/routers/eventos.py
──────────────────────
Endpoints de eventos:
  GET  /api/eventos                        → listagem pública (UC05)
  POST /api/eventos                        → criar evento (UC02 — Organizador)
  PUT  /api/eventos/{id_evento}            → editar evento (UC02)
  DELETE /api/eventos/{id_evento}          → excluir evento (UC02)
  GET  /api/organizadores/{id}/eventos     → eventos de um organizador
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, HTTPException

from app.db.cassandra import get_session
from app.schemas.schemas import EventoCreate, EventoResponse

router  = APIRouter(prefix="/api", tags=["Eventos"])
logger  = logging.getLogger(__name__)
BUCKET  = "todos"          # partition key estática para eventos_publicos


# ── LISTAGEM PÚBLICA (UC05) ───────────────────────────────────────────────────

@router.get("/eventos", response_model=List[EventoResponse])
def listar_eventos(categoria: str = None):
    """
    Retorna todos os eventos disponíveis.
    Aceita filtro por categoria (rock, samba, jazz, pop, indie…).
    """
    session = get_session()

    rows = session.execute(
        "SELECT * FROM eventos_publicos WHERE bucket = %s",
        (BUCKET,)
    )

    eventos = [_row_to_response(r) for r in rows]

    if categoria and categoria != "todos":
        eventos = [e for e in eventos if e.categoria.lower() == categoria.lower()]

    return eventos


# ── CRIAR EVENTO (UC02) ───────────────────────────────────────────────────────

@router.post("/eventos", response_model=EventoResponse, status_code=201)
def criar_evento(id_organizador: str, body: EventoCreate):
    """
    Cria um novo evento.
    Insere em eventos_por_organizador E eventos_publicos (desnormalização Cassandra).
    Inicializa o contador de vagas em vagas_evento.
    """
    session      = get_session()
    id_evento    = uuid.uuid4()
    id_org_uuid  = uuid.UUID(id_organizador)

    # ── Insert em eventos_por_organizador (painel do organizador)
    session.execute(
        """
        INSERT INTO eventos_por_organizador
          (id_organizador, data_hora, id_evento, titulo, descricao,
           local, capacidade_maxima, categoria)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (id_org_uuid, body.data_hora, id_evento, body.titulo,
         body.descricao or "", body.local, body.capacidade_maxima,
         body.categoria or "outros"),
    )

    # ── Insert em eventos_publicos (listagem para clientes)
    session.execute(
        """
        INSERT INTO eventos_publicos
          (bucket, data_hora, id_evento, id_organizador, titulo, descricao,
           local, capacidade_maxima, categoria)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (BUCKET, body.data_hora, id_evento, id_org_uuid, body.titulo,
         body.descricao or "", body.local, body.capacidade_maxima,
         body.categoria or "outros"),
    )

    # ── Inicializar contador de vagas (RN003) via UPDATE (obrigatório para COUNTER)
    session.execute(
        """
        UPDATE vagas_evento
        SET vagas_disponiveis = vagas_disponiveis + %s,
            total_vendidos    = total_vendidos    + 0
        WHERE id_evento = %s
        """,
        (body.capacidade_maxima, id_evento),
    )

    logger.info(f"Evento criado: {body.titulo} | id={id_evento}")
    return EventoResponse(
        id_evento=str(id_evento),
        id_organizador=id_organizador,
        titulo=body.titulo,
        descricao=body.descricao or "",
        data_hora=body.data_hora,
        local=body.local,
        capacidade_maxima=body.capacidade_maxima,
        categoria=body.categoria or "outros",
    )


# ── EVENTOS DO ORGANIZADOR ────────────────────────────────────────────────────

@router.get("/organizadores/{id_organizador}/eventos", response_model=List[EventoResponse])
def eventos_do_organizador(id_organizador: str):
    session    = get_session()
    id_org_uuid = uuid.UUID(id_organizador)

    rows = session.execute(
        "SELECT * FROM eventos_por_organizador WHERE id_organizador = %s",
        (id_org_uuid,)
    )
    return [_row_to_response(r, id_organizador) for r in rows]


# ── EDITAR EVENTO (UC02) ──────────────────────────────────────────────────────

@router.put("/eventos/{id_evento}", response_model=EventoResponse)
def editar_evento(id_evento: str, id_organizador: str, body: EventoCreate):
    """
    Cassandra não tem UPDATE genérico por chave não-primária em tabelas normais.
    A estratégia é DELETE + INSERT (padrão Cassandra para atualizar clustering keys).
    """
    session     = get_session()
    id_ev_uuid  = uuid.UUID(id_evento)
    id_org_uuid = uuid.UUID(id_organizador)

    # Busca o evento atual para saber a data_hora antiga (parte da PK)
    row_atual = session.execute(
        "SELECT data_hora FROM eventos_por_organizador "
        "WHERE id_organizador = %s AND id_evento = %s ALLOW FILTERING",
        (id_org_uuid, id_ev_uuid)
    ).one()

    if not row_atual:
        raise HTTPException(status_code=404, detail="Evento não encontrado.")

    # Delete + Insert na tabela do organizador
    session.execute(
        "DELETE FROM eventos_por_organizador "
        "WHERE id_organizador = %s AND data_hora = %s AND id_evento = %s",
        (id_org_uuid, row_atual.data_hora, id_ev_uuid),
    )
    session.execute(
        """
        INSERT INTO eventos_por_organizador
          (id_organizador, data_hora, id_evento, titulo, descricao,
           local, capacidade_maxima, categoria)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (id_org_uuid, body.data_hora, id_ev_uuid, body.titulo,
         body.descricao or "", body.local, body.capacidade_maxima,
         body.categoria or "outros"),
    )

    # Atualiza eventos_publicos também
    session.execute(
        """
        INSERT INTO eventos_publicos
          (bucket, data_hora, id_evento, id_organizador, titulo, descricao,
           local, capacidade_maxima, categoria)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (BUCKET, body.data_hora, id_ev_uuid, id_org_uuid, body.titulo,
         body.descricao or "", body.local, body.capacidade_maxima,
         body.categoria or "outros"),
    )

    logger.info(f"Evento atualizado: {id_evento}")
    return EventoResponse(
        id_evento=id_evento, id_organizador=id_organizador,
        titulo=body.titulo, descricao=body.descricao or "",
        data_hora=body.data_hora, local=body.local,
        capacidade_maxima=body.capacidade_maxima, categoria=body.categoria or "outros",
    )


# ── EXCLUIR EVENTO (UC02) ─────────────────────────────────────────────────────

@router.delete("/eventos/{id_evento}", status_code=204)
def excluir_evento(id_evento: str, id_organizador: str, data_hora: datetime):
    """
    Exclui o evento das duas tabelas.
    data_hora precisa ser passado porque faz parte da chave primária.
    """
    session     = get_session()
    id_ev_uuid  = uuid.UUID(id_evento)
    id_org_uuid = uuid.UUID(id_organizador)

    session.execute(
        "DELETE FROM eventos_por_organizador "
        "WHERE id_organizador = %s AND data_hora = %s AND id_evento = %s",
        (id_org_uuid, data_hora, id_ev_uuid),
    )
    session.execute(
        "DELETE FROM eventos_publicos "
        "WHERE bucket = %s AND data_hora = %s AND id_evento = %s",
        (BUCKET, data_hora, id_ev_uuid),
    )
    logger.info(f"Evento excluído: {id_evento}")


# ── Helper ────────────────────────────────────────────────────────────────────

def _row_to_response(row, id_organizador_fallback: str = None) -> EventoResponse:
    id_org = (
        str(row.id_organizador)
        if hasattr(row, "id_organizador") and row.id_organizador
        else (id_organizador_fallback or "")
    )
    return EventoResponse(
        id_evento=str(row.id_evento),
        id_organizador=id_org,
        titulo=row.titulo or "",
        descricao=row.descricao or "",
        data_hora=row.data_hora,
        local=row.local or "",
        capacidade_maxima=row.capacidade_maxima or 0,
        categoria=row.categoria or "outros",
    )
