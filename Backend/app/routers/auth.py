"""
app/routers/auth.py
───────────────────
Endpoints de autenticação:
  POST /api/login      → login de qualquer tipo de usuário
  POST /api/registro   → cadastro de cliente (tipo='cliente')
  POST /api/registro/organizador → cadastro de organizador

Otimizações aplicadas:
  - hash_senha e verificar_senha rodam em thread pool (run_in_executor)
    para não bloquear o event loop do uvicorn sob carga
  - Endpoints convertidos para async def
  - Argon2 com parâmetros ajustados para menor custo computacional
"""

import uuid
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from passlib.hash import argon2 as argon2_hash

from app.db.cassandra import get_session
from app.schemas.schemas import (
    LoginRequest, LoginResponse,
    RegistroClienteRequest, RegistroOrganizadorRequest, RegistroResponse,
)

router = APIRouter(prefix="/api", tags=["Auth"])
logger = logging.getLogger(__name__)

# Argon2 com parâmetros reduzidos para melhor throughput
# memory_cost: 32MB (padrão 65MB), time_cost: 2 (padrão 3)
_argon2 = argon2_hash.using(
    memory_cost=32768,
    time_cost=2,
    parallelism=2,
)


# ── Helpers assíncronos de hash ───────────────────────────────────────────────

async def _hash_senha(senha: str) -> str:
    """Roda o Argon2 em thread pool para não bloquear o event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _argon2.hash, senha)


async def _verificar_senha(senha: str, hash_armazenado: str) -> bool:
    """Verifica o hash em thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _argon2.verify, senha, hash_armazenado)


# ── LOGIN ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def fazer_login(req: LoginRequest):
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

    senha_ok = await _verificar_senha(req.senha, row.senha_hash)
    if not senha_ok:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    if row.status_conta != "confirmada":
        raise HTTPException(status_code=403, detail="Conta ainda não confirmada. Verifique seu e-mail.")

    return LoginResponse(
        sucesso=True,
        nome=row.nome,
        tipo=row.tipo,
        id_usuario=str(row.id_usuario),
    )


# ── REGISTRO CLIENTE ──────────────────────────────────────────────────────────

@router.post("/registro", response_model=RegistroResponse, status_code=201)
async def criar_conta_cliente(req: RegistroClienteRequest):
    """
    Cadastra um novo cliente.
    Hash do Argon2 é executado em thread pool para liberar o event loop.
    """
    session = get_session()
    _verificar_email_e_cpf_unicos(session, req.email, req.cpf, "cliente")

    novo_id   = uuid.uuid4()
    senha_hash = await _hash_senha(req.senha)

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
            senha_hash,
            "cliente",
            datetime.now(timezone.utc),
            "confirmada",
        ),
    )

    logger.info(f"Novo cliente cadastrado: {req.email}")
    return RegistroResponse(sucesso=True, mensagem="Conta criada com sucesso!")


# ── REGISTRO ORGANIZADOR ──────────────────────────────────────────────────────

@router.post("/registro/organizador", response_model=RegistroResponse, status_code=201)
async def criar_conta_organizador(req: RegistroOrganizadorRequest):
    """
    Cadastra um novo organizador.
    Se o e-mail já existir como 'cliente', promove a conta para 'organizador'
    (permitindo que a mesma pessoa compre e organize eventos).
    """
    session = get_session()
    email = req.email.lower().strip()

    existente = session.execute(
        "SELECT email, id_usuario, tipo FROM usuarios_por_email WHERE email = %s",
        (email,)
    ).one()

    if existente:
        if existente.tipo == "organizador":
            raise HTTPException(status_code=400, detail="Este e-mail já está cadastrado como organizador.")

        # Conta de cliente existente: promove para organizador
        nova_senha_hash = await _hash_senha(req.senha)
        session.execute(
            """
            UPDATE usuarios_por_email
            SET tipo = 'organizador', senha_hash = %s
            WHERE email = %s
            """,
            (nova_senha_hash, email),
        )
        logger.info(f"Cliente promovido a organizador: {email} | org: {req.nome_organizacao}")
        return RegistroResponse(sucesso=True, mensagem="Sua conta foi atualizada para organizador com sucesso!")

    # Verifica CPF duplicado apenas para cadastros novos
    cpf_existente = session.execute(
        "SELECT email FROM usuarios_por_email WHERE cpf = %s",
        (req.cpf,)
    ).one()
    if cpf_existente:
        raise HTTPException(status_code=400, detail="Este CPF já está cadastrado.")

    novo_id    = uuid.uuid4()
    senha_hash = await _hash_senha(req.senha)

    session.execute(
        """
        INSERT INTO usuarios_por_email
          (email, id_usuario, nome, cpf, senha_hash, tipo, data_cadastro, status_conta)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            email,
            novo_id,
            req.nome,
            req.cpf,
            senha_hash,
            "organizador",
            datetime.now(timezone.utc),
            "confirmada",
        ),
    )

    logger.info(f"Novo organizador cadastrado: {email} | org: {req.nome_organizacao}")
    return RegistroResponse(sucesso=True, mensagem="Conta de organizador criada com sucesso!")


# ── DELETAR CONTA ─────────────────────────────────────────────────────────────

@router.delete("/conta/{email}")
async def deletar_conta(email: str):
    session = get_session()

    row = session.execute(
        "SELECT id_usuario, tipo FROM usuarios_por_email WHERE email = %s",
        (email.lower().strip(),)
    ).one()

    if not row:
        raise HTTPException(status_code=404, detail="Conta não encontrada.")

    if row.tipo == "organizador":
        _deletar_eventos_do_organizador(session, row.id_usuario)

    session.execute(
        "DELETE FROM usuarios_por_email WHERE email = %s",
        (email.lower().strip(),)
    )

    logger.info(f"Conta deletada: {email} (tipo={row.tipo})")
    return {"sucesso": True, "mensagem": "Conta removida com sucesso."}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _deletar_eventos_do_organizador(session, id_organizador):
    BUCKET = "todos"
    rows   = session.execute(
        "SELECT data_hora, id_evento FROM eventos_por_organizador WHERE id_organizador = %s",
        (id_organizador,)
    )
    eventos = list(rows)

    for ev in eventos:
        session.execute(
            "DELETE FROM eventos_por_organizador "
            "WHERE id_organizador = %s AND data_hora = %s AND id_evento = %s",
            (id_organizador, ev.data_hora, ev.id_evento)
        )
        session.execute(
            "DELETE FROM eventos_publicos "
            "WHERE bucket = %s AND data_hora = %s AND id_evento = %s",
            (BUCKET, ev.data_hora, ev.id_evento)
        )

    logger.info(f"Cascata: {len(eventos)} evento(s) removido(s) do organizador {id_organizador}")


def _verificar_email_e_cpf_unicos(session, email: str, cpf: str, tipo: str):
    existente = session.execute(
        "SELECT email FROM usuarios_por_email WHERE email = %s",
        (email.lower().strip(),)
    ).one()
    if existente:
        raise HTTPException(status_code=400, detail="Este e-mail já está cadastrado.")

    cpf_existente = session.execute(
        "SELECT email FROM usuarios_por_email WHERE cpf = %s",
        (cpf,)
    ).one()
    if cpf_existente:
        raise HTTPException(status_code=400, detail="Este CPF já está cadastrado.")