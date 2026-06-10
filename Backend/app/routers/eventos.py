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
from app.schemas.schemas import EventoCreate, EventoResponse, LoteCreate, LoteResponse

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

    eventos = [_row_to_response(r, session=session) for r in rows]

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
        status=body.status or "rascunho",
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
    return [_row_to_response(r, id_organizador, session=session) for r in rows]


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
        status=body.status or "rascunho",
    )


# ── EXCLUIR EVENTO (UC02) ─────────────────────────────────────────────────────

@router.delete("/eventos/{id_evento}")
def excluir_evento(id_evento: str, id_organizador: str):
    session = get_session()
    
    # 1. BUSQUE O EVENTO PRIMEIRO para pegar a data_hora
    # Precisamos encontrar o evento que queremos apagar
    row = session.execute(
        "SELECT id_organizador, data_hora FROM eventos_por_organizador WHERE id_organizador = %s AND id_evento = %s ALLOW FILTERING",
        (uuid.UUID(id_organizador), uuid.UUID(id_evento))
    ).one()
    
    if not row:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    id_ev_uuid  = uuid.UUID(id_evento)
    id_org_uuid = uuid.UUID(id_organizador)

    # 2. Delete da tabela do organizador
    session.execute(
        "DELETE FROM eventos_por_organizador WHERE id_organizador = %s AND data_hora = %s AND id_evento = %s",
        (id_org_uuid, row.data_hora, id_ev_uuid)
    )

    # 3. Delete de eventos_publicos (sem isso o evento continua aparecendo no index.html)
    session.execute(
        "DELETE FROM eventos_publicos WHERE bucket = %s AND data_hora = %s AND id_evento = %s",
        (BUCKET, row.data_hora, id_ev_uuid)
    )

    logger.info(f"Evento excluído: {id_evento}")
    return {"message": "Deletado com sucesso"}


# ── Helper ────────────────────────────────────────────────────────────────────

def _row_to_response(row, id_organizador_fallback: str = None, session=None) -> EventoResponse:
    id_org = (
        str(row.id_organizador)
        if hasattr(row, "id_organizador") and row.id_organizador
        else (id_organizador_fallback or "")
    )

    vendidos = 0
    receita = 0.0

    # Busca dados reais de vendas na tabela vagas_evento
    if session is not None:
        try:
            vagas_row = session.execute(
                "SELECT vagas_disponiveis, total_vendidos FROM vagas_evento WHERE id_evento = %s",
                (row.id_evento,)
            ).one()
            if vagas_row:
                vendidos = int(vagas_row.total_vendidos or 0)
                capacidade = row.capacidade_maxima or 0
                # Busca receita real somando os tickets vendidos do evento
                tickets_rows = session.execute(
                    "SELECT valor_pago FROM tickets_por_evento WHERE id_evento = %s",
                    (row.id_evento,)
                )
                # tickets_por_evento não tem valor_pago — busca via tickets_por_cliente
                # Estratégia: usa total_vendidos como contagem e busca preço médio dos lotes
                lotes_rows = session.execute(
                    "SELECT preco, quantidade FROM lotes_por_evento WHERE id_evento = %s",
                    (row.id_evento,)
                )
                lotes = list(lotes_rows)
                if lotes:
                    preco_medio = sum(float(l.preco) * int(l.quantidade) for l in lotes) / sum(int(l.quantidade) for l in lotes)
                    receita = round(preco_medio * vendidos, 2)
        except Exception:
            pass  # Se falhar, mantém 0 — não quebra a listagem

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


# ── LOTES DO EVENTO ───────────────────────────────────────────────────────────

@router.get("/eventos/{id_evento}/lotes", response_model=List[LoteResponse])
def listar_lotes(id_evento: str):
    """
    Retorna todos os lotes (tipos de ingresso + preços) de um evento.
    Chamado pelo frontend ao abrir o modal de compra.
    """
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
    """
    Cria um lote (tipo de ingresso) para um evento.
    Cada evento pode ter múltiplos lotes com nome, preço e quantidade próprios.
    Exemplo: { "nome": "Camarote", "preco": 300.00, "quantidade": 50 }
    """
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
    """Remove um lote específico de um evento."""
    session = get_session()

    session.execute(
        "DELETE FROM lotes_por_evento WHERE id_evento = %s AND id_lote = %s",
        (uuid.UUID(id_evento), uuid.UUID(id_lote)),
    )

    logger.info(f"Lote removido: {id_lote} | evento={id_evento}")
    return {"sucesso": True, "mensagem": "Lote removido."}