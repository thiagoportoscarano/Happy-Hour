"""
app/routers/auth.py
───────────────────
Endpoints de autenticação:
  POST /api/login      → login de qualquer tipo de usuário
  POST /api/registro   → cadastro de cliente (tipo='cliente')
  POST /api/registro/organizador → cadastro de organizador
"""

import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from app.db.cassandra import get_session
from app.schemas.schemas import (
    LoginRequest, LoginResponse,
    RegistroClienteRequest, RegistroOrganizadorRequest, RegistroResponse,
)
from app.utils.security import hash_senha, verificar_senha

router = APIRouter(prefix="/api", tags=["Auth"])
logger = logging.getLogger(__name__)


# ── LOGIN ────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
def fazer_login(req: LoginRequest):
    """
    Autentica qualquer usuário pelo e-mail.
    O frontend de organizadores deve verificar se tipo == 'organizador'.
    """
    session = get_session()

    row = session.execute(
        "SELECT id_usuario, nome, senha_hash, tipo, status_conta "
        "FROM usuarios_por_email WHERE email = %s",
        (req.email.lower().strip(),)
    ).one()

    if not row:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    if not verificar_senha(req.senha, row.senha_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    if row.status_conta != "confirmada":
        raise HTTPException(status_code=403, detail="Conta ainda não confirmada. Verifique seu e-mail.")

    return LoginResponse(
        sucesso=True,
        nome=row.nome,
        tipo=row.tipo,
        id_usuario=str(row.id_usuario),
    )


# ── REGISTRO CLIENTE ─────────────────────────────────────────────────────────

@router.post("/registro", response_model=RegistroResponse, status_code=201)
def criar_conta_cliente(req: RegistroClienteRequest):
    """
    Cadastra um novo cliente.
    Alinhado com a tabela usuarios_por_email (partition key = email).
    Verifica unicidade de e-mail e CPF antes de inserir.
    """
    session = get_session()
    _verificar_email_e_cpf_unicos(session, req.email, req.cpf, req.tipo)

    novo_id = uuid.uuid4()
    session.execute(
        """
        INSERT INTO usuarios_por_email
          (email, id_usuario, nome, cpf, senha_hash, tipo, data_cadastro, status_conta)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            req.email.lower().strip(),
            novo_id,
            req.nome,
            req.cpf,
            hash_senha(req.senha),
            "cliente",
            datetime.now(timezone.utc),
            "confirmada",           # simplificado — em produção: 'aguardando_confirmacao'
        ),
    )

    logger.info(f"Novo cliente cadastrado: {req.email}")
    return RegistroResponse(sucesso=True, mensagem="Conta criada com sucesso!")


# ── REGISTRO ORGANIZADOR ──────────────────────────────────────────────────────

@router.post("/registro/organizador", response_model=RegistroResponse, status_code=201)
def criar_conta_organizador(req: RegistroOrganizadorRequest):
    """
    Cadastra um novo organizador.
    O campo tipo='organizador' diferencia na tabela usuarios_por_email.
    nome_organizacao e tipo_organizacao são armazenados junto por simplicidade
    (em produção poderiam ir para uma tabela ORGANIZADOR separada no PostgreSQL).
    """
    session = get_session()
    _verificar_email_e_cpf_unicos(session, req.email, req.cpf, req.tipo)

    novo_id = uuid.uuid4()
    session.execute(
        """
        INSERT INTO usuarios_por_email
          (email, id_usuario, nome, cpf, senha_hash, tipo, data_cadastro, status_conta)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            req.email.lower().strip(),
            novo_id,
            req.nome,
            req.cpf,
            hash_senha(req.senha),
            "organizador",
            datetime.now(timezone.utc),
            "confirmada",
        ),
    )

    logger.info(f"Novo organizador cadastrado: {req.email} | org: {req.nome_organizacao}")
    return RegistroResponse(sucesso=True, mensagem="Conta de organizador criada com sucesso!")


# ── DELETAR CONTA ────────────────────────────────────────────────────────────

@router.delete("/conta/{email}")
def deletar_conta(email: str):
    """
    Remove a conta do usuário.
    Se for organizador, apaga em cascata todos os seus eventos
    de eventos_por_organizador E de eventos_publicos.
    """
    session = get_session()

    # Busca o usuário pelo e-mail
    row = session.execute(
        "SELECT id_usuario, tipo FROM usuarios_por_email WHERE email = %s",
        (email.lower().strip(),)
    ).one()

    if not row:
        raise HTTPException(status_code=404, detail="Conta não encontrada.")

    # Se for organizador, apaga todos os eventos em cascata
    if row.tipo == "organizador":
        _deletar_eventos_do_organizador(session, row.id_usuario)

    # Apaga a conta
    session.execute(
        "DELETE FROM usuarios_por_email WHERE email = %s",
        (email.lower().strip(),)
    )

    logger.info(f"Conta deletada: {email} (tipo={row.tipo})")
    return {"sucesso": True, "mensagem": "Conta removida com sucesso."}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _deletar_eventos_do_organizador(session, id_organizador):
    """
    Apaga todos os eventos do organizador das duas tabelas:
      - eventos_por_organizador  (painel do organizador)
      - eventos_publicos         (listagem pública do index.html)
    """
    BUCKET = "todos"

    # Busca todos os eventos do organizador para ter data_hora e id_evento
    # (ambos fazem parte da chave primária e são necessários para o DELETE)
    rows = session.execute(
        "SELECT data_hora, id_evento FROM eventos_por_organizador WHERE id_organizador = %s",
        (id_organizador,)
    )
    eventos = list(rows)  # materializa antes de deletar

    for ev in eventos:
        # Remove da tabela do organizador
        session.execute(
            "DELETE FROM eventos_por_organizador "
            "WHERE id_organizador = %s AND data_hora = %s AND id_evento = %s",
            (id_organizador, ev.data_hora, ev.id_evento)
        )
        # Remove da listagem pública
        session.execute(
            "DELETE FROM eventos_publicos "
            "WHERE bucket = %s AND data_hora = %s AND id_evento = %s",
            (BUCKET, ev.data_hora, ev.id_evento)
        )

    logger.info(f"Cascata: {len(eventos)} evento(s) removido(s) do organizador {id_organizador}")


def _verificar_email_e_cpf_unicos(session, email: str, cpf: str, tipo : str):
    """Garante unicidade de e-mail (PK) e CPF (índice secundário) — UC04 FE2/FE3."""
    # E-mail: leitura direta pela partition key (O(1))
    existente = session.execute(
        "SELECT email FROM usuarios_por_email WHERE email = %s AND tipo = %s",
        (email.lower().strip(),tipo,)
    ).one()
    if existente:
        raise HTTPException(status_code=400, detail="Este e-mail já está cadastrado.")

    # CPF: leitura via índice secundário
    cpf_existente = session.execute(
        "SELECT email FROM usuarios_por_email WHERE cpf = %s AND tipo = %s",
        (cpf,tipo,)
    ).one()
    if cpf_existente:
        raise HTTPException(status_code=400, detail="Este CPF já está cadastrado.")