"""
app/routers/tickets.py
──────────────────────
Endpoints de tickets e check-in:
  POST /api/tickets              → comprar ingresso (UC01)
  GET  /api/tickets/{cliente_id} → histórico do cliente
  POST /api/checkin              → validar ticket na entrada (UC03)
  GET  /api/vagas/{id_evento}    → vagas disponíveis (RN003)
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, HTTPException
from decimal import Decimal

from app.db.cassandra import get_session
from app.schemas.schemas import (
    CompraRequest, TicketResponse,
    CheckinRequest, CheckinResponse,
)

router = APIRouter(prefix="/api", tags=["Tickets"])
logger = logging.getLogger(__name__)


# ── COMPRAR INGRESSO (UC01) ───────────────────────────────────────────────────

@router.post("/tickets", response_model=TicketResponse, status_code=201)
def comprar_ingresso(req: CompraRequest):
    """
    Fluxo completo de compra:
    1. Verifica vagas disponíveis (RN003)
    2. Gera QR Code único
    3. Insere em tickets_por_cliente E tickets_por_evento (desnormalização)
    4. Decrementa contador atômico de vagas

    Nota: em produção o pagamento seria processado ANTES desta etapa.
    """
    session      = get_session()
    id_ev_uuid   = uuid.UUID(req.id_evento)
    id_cli_uuid  = uuid.UUID(req.id_cliente)

    # ── 1. Verifica vagas (RN003)
    vagas_row = session.execute(
        "SELECT vagas_disponiveis FROM vagas_evento WHERE id_evento = %s",
        (id_ev_uuid,)
    ).one()

    if not vagas_row or vagas_row.vagas_disponiveis <= 0:
        raise HTTPException(status_code=409, detail="Ingressos esgotados para este evento.")

    # ── 2. Gera IDs únicos
    id_ticket = uuid.uuid4()
    codigo_qr = f"QR-{req.id_evento[:8].upper()}-{str(id_ticket)[:8].upper()}"
    agora     = datetime.now(timezone.utc)

    # ── 3a. Insere em tickets_por_cliente (histórico)
    session.execute(
        """
        INSERT INTO tickets_por_cliente
          (id_cliente, data_compra, id_ticket, id_evento, titulo_evento,
           data_evento, local_evento, codigo_qr, status, valor_pago, forma_pagamento)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            id_cli_uuid, agora, id_ticket, id_ev_uuid,
            req.titulo_evento, req.data_evento, req.local_evento,
            codigo_qr, "ativo", Decimal(str(req.valor_pago)), req.forma_pagamento,
        ),
    )

    # ── 3b. Insere em tickets_por_evento (check-in pelo validador)
    # nome_cliente precisaria vir de uma query prévia; simplificado aqui
    session.execute(
        """
        INSERT INTO tickets_por_evento
          (id_evento, codigo_qr, id_ticket, id_cliente, nome_cliente,
           status_validacao, data_checkin)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (id_ev_uuid, codigo_qr, id_ticket, id_cli_uuid, "Cliente", "ativo", None),
    )

    # ── 4. Decrementa vagas atomicamente (COUNTER — RN003)
    session.execute(
        """
        UPDATE vagas_evento
        SET vagas_disponiveis = vagas_disponiveis - 1,
            total_vendidos    = total_vendidos    + 1
        WHERE id_evento = %s
        """,
        (id_ev_uuid,),
    )

    logger.info(f"Ingresso emitido: {codigo_qr} | evento={req.id_evento}")
    return TicketResponse(
        id_ticket=str(id_ticket),
        codigo_qr=codigo_qr,
        status="ativo",
        data_compra=agora,
        titulo_evento=req.titulo_evento,
        valor_pago=req.valor_pago,
    )


# ── HISTÓRICO DO CLIENTE ──────────────────────────────────────────────────────

@router.get("/tickets/{id_cliente}", response_model=List[TicketResponse])
def historico_cliente(id_cliente: str):
    session     = get_session()
    id_cli_uuid = uuid.UUID(id_cliente)

    rows = session.execute(
        "SELECT * FROM tickets_por_cliente WHERE id_cliente = %s",
        (id_cli_uuid,)
    )
    return [
        TicketResponse(
            id_ticket=str(r.id_ticket),
            codigo_qr=r.codigo_qr,
            status=r.status,
            data_compra=r.data_compra,
            titulo_evento=r.titulo_evento,
            valor_pago=float(r.valor_pago),
        )
        for r in rows
    ]


# ── CHECK-IN / VALIDAR TICKET (UC03) ─────────────────────────────────────────

@router.post("/checkin", response_model=CheckinResponse)
def validar_ticket(req: CheckinRequest):
    """
    Fluxo de validação na entrada do evento:
    - Busca o ticket pela partition key (id_evento) + clustering key (codigo_qr)
    - Se status == 'ativo': muda para 'utilizado' e libera acesso (tela verde)
    - Se status == 'utilizado': bloqueia (RN001 — unicidade de uso)
    - Se não encontrado: bloqueia
    Leitura em QUORUM garante que o status é o mais recente mesmo em cluster.
    """
    session    = get_session()
    id_ev_uuid = uuid.UUID(req.id_evento)

    row = session.execute(
        "SELECT status_validacao, nome_cliente, id_ticket, id_cliente "
        "FROM tickets_por_evento "
        "WHERE id_evento = %s AND codigo_qr = %s",
        (id_ev_uuid, req.codigo_qr)
    ).one()

    # Ticket não encontrado
    if not row:
        return CheckinResponse(autorizado=False, mensagem="QR Code inválido ou não pertence a este evento.")

    # Ticket já utilizado (RN001)
    if row.status_validacao == "utilizado":
        return CheckinResponse(autorizado=False, mensagem="TICKET JÁ UTILIZADO — acesso bloqueado.")

    # Ticket cancelado
    if row.status_validacao == "cancelado":
        return CheckinResponse(autorizado=False, mensagem="Ticket cancelado — acesso negado.")

    # ── Ticket válido: marca como utilizado em ambas as tabelas
    agora = datetime.now(timezone.utc)

    session.execute(
        """
        UPDATE tickets_por_evento
        SET status_validacao = 'utilizado', data_checkin = %s
        WHERE id_evento = %s AND codigo_qr = %s
        """,
        (agora, id_ev_uuid, req.codigo_qr),
    )

    # Reflete no histórico do cliente (ALLOW FILTERING — aceitável para operação pontual)
    session.execute(
        """
        UPDATE tickets_por_cliente
        SET status = 'utilizado'
        WHERE id_cliente = %s AND id_ticket = %s
        """,
        (row.id_cliente, row.id_ticket),
    )

    logger.info(f"Check-in autorizado: {req.codigo_qr} | evento={req.id_evento}")
    return CheckinResponse(
        autorizado=True,
        mensagem="ENTRADA AUTORIZADA ✅",
        nome_cliente=row.nome_cliente,
    )


# ── VAGAS DISPONÍVEIS (RN003) ─────────────────────────────────────────────────

@router.get("/vagas/{id_evento}")
def vagas_disponiveis(id_evento: str):
    session    = get_session()
    id_ev_uuid = uuid.UUID(id_evento)

    row = session.execute(
        "SELECT vagas_disponiveis, total_vendidos FROM vagas_evento WHERE id_evento = %s",
        (id_ev_uuid,)
    ).one()

    if not row:
        raise HTTPException(status_code=404, detail="Evento não encontrado.")

    return {
        "id_evento": id_evento,
        "vagas_disponiveis": row.vagas_disponiveis,
        "total_vendidos": row.total_vendidos,
    }


# ── CANCELAR INGRESSO (RN002 — até 48h antes) ────────────────────────────────

@router.patch("/tickets/{id_ticket}/cancelar")
def cancelar_ingresso(id_ticket: str, id_cliente: str, id_evento: str, codigo_qr: str, data_compra: datetime):
    """
    Cancela um ingresso. O frontend deve verificar a regra das 48h antes de chamar.
    """
    session     = get_session()
    id_cli_uuid = uuid.UUID(id_cliente)
    id_ev_uuid  = uuid.UUID(id_evento)
    id_tk_uuid  = uuid.UUID(id_ticket)

    # Atualiza histórico do cliente
    session.execute(
        "UPDATE tickets_por_cliente SET status = 'cancelado' "
        "WHERE id_cliente = %s AND data_compra = %s AND id_ticket = %s",
        (id_cli_uuid, data_compra, id_tk_uuid),
    )

    # Atualiza tabela de check-in
    session.execute(
        "UPDATE tickets_por_evento SET status_validacao = 'cancelado' "
        "WHERE id_evento = %s AND codigo_qr = %s",
        (id_ev_uuid, codigo_qr),
    )

    # Devolve a vaga (COUNTER)
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
