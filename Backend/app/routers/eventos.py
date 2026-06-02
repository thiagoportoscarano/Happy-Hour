import uuid
import logging
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, HTTPException

from app.db.cassandra import get_session
from app.schemas.schemas import EventoCreate, EventoResponse, LoteCreate, LoteResponse

router  = APIRouter(prefix="/api", tags=["Eventos"])
logger  = logging.getLogger(__name__)
BUCKET  = "todos"

@router.get("/eventos", response_model=List[EventoResponse])
def listar_eventos(categoria: str = None):
    session = get_session()

    rows = session.execute(
        "SELECT * FROM eventos_publicos WHERE bucket = %s",
        (BUCKET,)
    )

    eventos = [_row_to_response(r, session=session) for r in rows]

    if categoria and categoria != "todos":
        eventos = [e for e in eventos if e.categoria.lower() == categoria.lower()]

    return eventos

@router.post("/eventos", response_model=EventoResponse, status_code=201)
def criar_evento(id_organizador: str, body: EventoCreate):
    session      = get_session()
    id_evento    = uuid.uuid4()
    id_org_uuid  = uuid.UUID(id_organizador)
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
        status=body.status or "rascunho",
    )

@router.get("/organizadores/{id_organizador}/eventos", response_model=List[EventoResponse])
def eventos_do_organizador(id_organizador: str):
    session    = get_session()
    id_org_uuid = uuid.UUID(id_organizador)

    rows = session.execute(
        "SELECT * FROM eventos_por_organizador WHERE id_organizador = %s",
        (id_org_uuid,)
    )
    return [_row_to_response(r, id_organizador, session=session) for r in rows]

@router.put("/eventos/{id_evento}", response_model=EventoResponse)
def editar_evento(id_evento: str, id_organizador: str, body: EventoCreate):
    session     = get_session()
    id_ev_uuid  = uuid.UUID(id_evento)
    id_org_uuid = uuid.UUID(id_organizador)

    row_atual = session.execute(
        "SELECT data_hora FROM eventos_por_organizador "
        "WHERE id_organizador = %s AND id_evento = %s ALLOW FILTERING",
        (id_org_uuid, id_ev_uuid)
    ).one()

    if not row_atual:
        raise HTTPException(status_code=404, detail="Evento não encontrado.")

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
        status=body.status or "rascunho",
    )

@router.delete("/eventos/{id_evento}")
def excluir_evento(id_evento: str, id_organizador: str):
    session = get_session()

    row = session.execute(
        "SELECT id_organizador, data_hora FROM eventos_por_organizador WHERE id_organizador = %s AND id_evento = %s ALLOW FILTERING",
        (uuid.UUID(id_organizador), uuid.UUID(id_evento))
    ).one()
    
    if not row:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    id_ev_uuid  = uuid.UUID(id_evento)
    id_org_uuid = uuid.UUID(id_organizador)

    session.execute(
        "DELETE FROM eventos_por_organizador WHERE id_organizador = %s AND data_hora = %s AND id_evento = %s",
        (id_org_uuid, row.data_hora, id_ev_uuid)
    )

    session.execute(
        "DELETE FROM eventos_publicos WHERE bucket = %s AND data_hora = %s AND id_evento = %s",
        (BUCKET, row.data_hora, id_ev_uuid)
    )

    logger.info(f"Evento excluído: {id_evento}")
    return {"message": "Deletado com sucesso"}

def _row_to_response(row, id_organizador_fallback: str = None, session=None) -> EventoResponse:
    id_org = (
        str(row.id_organizador)
        if hasattr(row, "id_organizador") and row.id_organizador
        else (id_organizador_fallback or "")
    )

    vendidos = 0
    receita = 0.0
    if session is not None:
        try:
            vagas_row = session.execute(
                "SELECT vagas_disponiveis, total_vendidos FROM vagas_evento WHERE id_evento = %s",
                (row.id_evento,)
            ).one()
            if vagas_row:
                vendidos = int(vagas_row.total_vendidos or 0)
                capacidade = row.capacidade_maxima or 0
                tickets_rows = session.execute(
                    "SELECT valor_pago FROM tickets_por_evento WHERE id_evento = %s",
                    (row.id_evento,)
                )
                lotes_rows = session.execute(
                    "SELECT preco, quantidade FROM lotes_por_evento WHERE id_evento = %s",
                    (row.id_evento,)
                )
                lotes = list(lotes_rows)
                if lotes:
                    preco_medio = sum(float(l.preco) * int(l.quantidade) for l in lotes) / sum(int(l.quantidade) for l in lotes)
                    receita = round(preco_medio * vendidos, 2)
        except Exception:
            pass

    return EventoResponse(
        id_evento=str(row.id_evento),
        id_organizador=id_org,
        titulo=row.titulo or "",
        descricao=row.descricao or "",
        data_hora=row.data_hora,
        local=row.local or "",
        capacidade_maxima=row.capacidade_maxima or 0,
        categoria=row.categoria or "outros",
        status=getattr(row, "status", "ativo"),
        vendidos=vendidos,
        receita=receita,
    )

@router.get("/eventos/{id_evento}/lotes", response_model=List[LoteResponse])
def listar_lotes(id_evento: str):
    session = get_session()
    id_ev_uuid = uuid.UUID(id_evento)

    rows = session.execute(
        "SELECT * FROM lotes_por_evento WHERE id_evento = %s",
        (id_ev_uuid,)
    )
    return [
        LoteResponse(
            id_lote=str(r.id_lote),
            id_evento=str(r.id_evento),
            nome=r.nome,
            preco=float(r.preco),
            quantidade=r.quantidade,
        )
        for r in rows
    ]


@router.post("/eventos/{id_evento}/lotes", response_model=LoteResponse, status_code=201)
def criar_lote(id_evento: str, body: LoteCreate):
    session = get_session()
    id_ev_uuid = uuid.UUID(id_evento)
    id_lote = uuid.uuid4()

    session.execute(
        """
        INSERT INTO lotes_por_evento
          (id_evento, id_lote, nome, preco, quantidade)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (id_ev_uuid, id_lote, body.nome, body.preco, body.quantidade),
    )

    logger.info(f"Lote criado: '{body.nome}' R${body.preco} | evento={id_evento}")
    return LoteResponse(
        id_lote=str(id_lote),
        id_evento=id_evento,
        nome=body.nome,
        preco=body.preco,
        quantidade=body.quantidade,
    )


@router.delete("/eventos/{id_evento}/lotes/{id_lote}")
def deletar_lote(id_evento: str, id_lote: str):
    session = get_session()

    session.execute(
        "DELETE FROM lotes_por_evento WHERE id_evento = %s AND id_lote = %s",
        (uuid.UUID(id_evento), uuid.UUID(id_lote)),
    )

    logger.info(f"Lote removido: {id_lote} | evento={id_evento}")
    return {"sucesso": True, "mensagem": "Lote removido."}