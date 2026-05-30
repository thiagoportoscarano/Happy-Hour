"""
app/routers/tickets.py
──────────────────────
Endpoints de tickets e check-in:
  POST   /api/tickets                  → comprar ingresso(s) (UC01)
  GET    /api/tickets/{id_cliente}     → histórico do cliente
  DELETE /api/tickets/{id_ticket}      → apagar ingresso do banco
  POST   /api/checkin                  → validar ticket na entrada (UC03)
  GET    /api/vagas/{id_evento}        → vagas disponíveis (RN003)
  PATCH  /api/tickets/{id_ticket}/cancelar → cancelar sem apagar (mantido)
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, HTTPException, Query
from decimal import Decimal

from app.db.cassandra import get_session
from app.schemas.schemas import (
    CompraRequest, TicketResponse,
    CheckinRequest, CheckinResponse,
)

router = APIRouter(prefix="/api", tags=["Tickets"])
logger = logging.getLogger(__name__)


# ── COMPRAR INGRESSO(S) ───────────────────────────────────────────────────────

@router.post("/tickets", response_model=List[TicketResponse], status_code=201)
def comprar_ingresso(req: CompraRequest):
    """
    Emite um ou mais ingressos de uma vez (req.quantidade).
    Verifica vagas suficientes para o total antes de emitir qualquer ticket.
    Retorna lista com todos os tickets gerados.
    """
    session     = get_session()
    id_ev_uuid  = uuid.UUID(req.id_evento)
    id_cli_uuid = uuid.UUID(req.id_cliente)
    quantidade  = max(1, req.quantidade)

    vagas_row = session.execute(
        "SELECT vagas_disponiveis FROM vagas_evento WHERE id_evento = %s",
        (id_ev_uuid,)
    ).one()

    vagas_atuais = int(vagas_row.vagas_disponiveis) if vagas_row else 0
    if vagas_atuais <= 0:
        raise HTTPException(status_code=409, detail="Ingressos esgotados para este evento.")
    if vagas_atuais < quantidade:
        raise HTTPException(
            status_code=409,
            detail=f"Vagas insuficientes. Disponíveis: {vagas_atuais}, solicitados: {quantidade}."
        )

    tickets_gerados = []
    agora          = datetime.now(timezone.utc)
    valor_unitario = Decimal(str(req.valor_pago))

    for i in range(quantidade):
        id_ticket = uuid.uuid4()
        codigo_qr = f"QR-{req.id_evento[:8].upper()}-{str(id_ticket)[:8].upper()}"
        data_compra = agora.replace(microsecond=(agora.microsecond + i) % 1_000_000)

        session.execute(
            """
            INSERT INTO tickets_por_cliente
              (id_cliente, data_compra, id_ticket, id_evento, titulo_evento,
               data_evento, local_evento, codigo_qr, status, valor_pago, forma_pagamento)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                id_cli_uuid, data_compra, id_ticket, id_ev_uuid,
                req.titulo_evento, req.data_evento, req.local_evento,
                codigo_qr, "ativo", valor_unitario, req.forma_pagamento,
            ),
        )

        session.execute(
            """
            INSERT INTO tickets_por_evento
              (id_evento, codigo_qr, id_ticket, id_cliente, nome_cliente,
               status_validacao, data_checkin)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (id_ev_uuid, codigo_qr, id_ticket, id_cli_uuid, "Cliente", "ativo", None),
        )

        logger.info(f"Ingresso emitido: {codigo_qr} | evento={req.id_evento} ({i+1}/{quantidade})")
        tickets_gerados.append(TicketResponse(
            id_ticket=str(id_ticket),
            id_evento=req.id_evento,
            codigo_qr=codigo_qr,
            status="ativo",
            data_compra=data_compra,
            titulo_evento=req.titulo_evento,
            valor_pago=float(valor_unitario),
        ))

    # Atualiza o counter uma única vez com o total
    session.execute(
        """
        UPDATE vagas_evento
        SET vagas_disponiveis = vagas_disponiveis - %s,
            total_vendidos    = total_vendidos    + %s
        WHERE id_evento = %s
        """,
        (quantidade, quantidade, id_ev_uuid),
    )

    return tickets_gerados


# ── HISTÓRICO DO CLIENTE ──────────────────────────────────────────────────────

@router.get("/tickets/{id_cliente}", response_model=List[TicketResponse])
def historico_cliente(id_cliente: str):
    session = get_session()
    id_cli_uuid = uuid.UUID(id_cliente)

    rows = session.execute(
        "SELECT * FROM tickets_por_cliente WHERE id_cliente = %s",
        (id_cli_uuid,)
    )
    return [
        TicketResponse(
            id_ticket=str(r.id_ticket),
            id_evento=str(r.id_evento),
            codigo_qr=r.codigo_qr,
            status=r.status,
            data_compra=r.data_compra,
            titulo_evento=r.titulo_evento,
            valor_pago=float(r.valor_pago),
        )
        for r in rows
    ]


# ── APAGAR INGRESSO DO BANCO ──────────────────────────────────────────────────

@router.delete("/tickets/{id_ticket}")
def deletar_ingresso(
    id_ticket: str,
    id_cliente: str = Query(...),
    id_evento: str  = Query(...),
    codigo_qr: str  = Query(...),
    data_compra: datetime = Query(...)
):
    """
    Remove permanentemente um ingresso das duas tabelas do Cassandra
    e devolve a vaga ao counter do evento.
    """
    session     = get_session()
    id_cli_uuid = uuid.UUID(id_cliente)
    id_ev_uuid  = uuid.UUID(id_evento)
    id_tk_uuid  = uuid.UUID(id_ticket)

    session.execute(
        "DELETE FROM tickets_por_cliente "
        "WHERE id_cliente = %s AND data_compra = %s AND id_ticket = %s",
        (id_cli_uuid, data_compra, id_tk_uuid),
    )

    session.execute(
        "DELETE FROM tickets_por_evento "
        "WHERE id_evento = %s AND codigo_qr = %s",
        (id_ev_uuid, codigo_qr),
    )

    session.execute(
        """
        UPDATE vagas_evento
        SET vagas_disponiveis = vagas_disponiveis + 1,
            total_vendidos    = total_vendidos    - 1
        WHERE id_evento = %s
        """,
        (id_ev_uuid,),
    )

    logger.info(f"Ingresso deletado: {id_ticket} | evento={id_evento}")
    return {"sucesso": True, "mensagem": "Ingresso removido do banco de dados."}


# ── CHECK-IN ──────────────────────────────────────────────────────────────────

@router.post("/checkin", response_model=CheckinResponse)
def validar_ticket(req: CheckinRequest):
    session = get_session()
    id_ev_uuid = uuid.UUID(req.id_evento)

    row = session.execute(
        "SELECT status_validacao, nome_cliente, id_ticket, id_cliente, data_compra "
        "FROM tickets_por_evento "
        "WHERE id_evento = %s AND codigo_qr = %s",
        (id_ev_uuid, req.codigo_qr)
    ).one()

    if not row:
        return CheckinResponse(autorizado=False, mensagem="QR Code invalido ou nao pertence a este evento.")

    if row.status_validacao == "utilizado":
        return CheckinResponse(autorizado=False, mensagem="TICKET JA UTILIZADO — acesso bloqueado.")

    if row.status_validacao == "cancelado":
        return CheckinResponse(autorizado=False, mensagem="Ticket cancelado — acesso negado.")

    agora = datetime.now(timezone.utc)

    session.execute(
        """
        UPDATE tickets_por_evento
        SET status_validacao = 'utilizado', data_checkin = %s
        WHERE id_evento = %s AND codigo_qr = %s
        """,
        (agora, id_ev_uuid, req.codigo_qr),
    )

    session.execute(
        """
        UPDATE tickets_por_cliente
        SET status = 'utilizado'
        WHERE id_cliente = %s AND data_compra = %s AND id_ticket = %s
        """,
        (row.id_cliente, row.data_compra, row.id_ticket),
    )

    logger.info(f"Check-in autorizado: {req.codigo_qr} | evento={req.id_evento}")
    return CheckinResponse(
        autorizado=True,
        mensagem="ENTRADA AUTORIZADA ✅",
        nome_cliente=row.nome_cliente,
    )


# ── VAGAS DISPONÍVEIS ─────────────────────────────────────────────────────────

@router.get("/vagas/{id_evento}")
def vagas_disponiveis(id_evento: str):
    session = get_session()
    id_ev_uuid = uuid.UUID(id_evento)

    row = session.execute(
        "SELECT vagas_disponiveis, total_vendidos FROM vagas_evento WHERE id_evento = %s",
        (id_ev_uuid,)
    ).one()

    if not row:
        raise HTTPException(status_code=404, detail="Evento nao encontrado.")

    return {
        "id_evento": id_evento,
        "vagas_disponiveis": row.vagas_disponiveis,
        "total_vendidos": row.total_vendidos,
    }


# ── CANCELAR SEM APAGAR (mantido para uso futuro) ────────────────────────────

@router.patch("/tickets/{id_ticket}/cancelar")
def cancelar_ingresso(
    id_ticket: str,
    id_cliente: str = Query(...),
    id_evento: str  = Query(...),
    codigo_qr: str  = Query(...),
    data_compra: datetime = Query(...)
):
    """
    Marca o ticket como 'cancelado' sem removê-lo do banco.
    O frontend usa DELETE /tickets/{id} para remoção permanente.
    """
    session     = get_session()
    id_cli_uuid = uuid.UUID(id_cliente)
    id_ev_uuid  = uuid.UUID(id_evento)
    id_tk_uuid  = uuid.UUID(id_ticket)

    session.execute(
        "UPDATE tickets_por_cliente SET status = 'cancelado' "
        "WHERE id_cliente = %s AND data_compra = %s AND id_ticket = %s",
        (id_cli_uuid, data_compra, id_tk_uuid),
    )

    session.execute(
        "UPDATE tickets_por_evento SET status_validacao = 'cancelado' "
        "WHERE id_evento = %s AND codigo_qr = %s",
        (id_ev_uuid, codigo_qr),
    )

    session.execute(
        """
        UPDATE vagas_evento
        SET vagas_disponiveis = vagas_disponiveis + 1,
            total_vendidos    = total_vendidos    - 1
        WHERE id_evento = %s
        """,
        (id_ev_uuid,),
    )

    logger.info(f"Ingresso cancelado: {id_ticket}")
    return {"sucesso": True, "mensagem": "Ingresso cancelado e vaga devolvida."}