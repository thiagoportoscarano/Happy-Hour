import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from app.db.cassandra import get_session
from app.schemas.schemas import (
    LoginRequest,
    LoginResponse,
    RegistroClienteRequest,
    RegistroOrganizadorRequest,
    RegistroValidadorRequest,
    RegistroResponse,
)
from app.utils.security import hash_senha, verificar_senha

router = APIRouter(prefix="/api", tags=["Auth"])
logger = logging.getLogger(__name__)

@router.post("/login", response_model=LoginResponse)
def fazer_login(req: LoginRequest):
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

@router.post("/registro", response_model=RegistroResponse, status_code=201)
def criar_conta_cliente(req: RegistroClienteRequest):
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
            "confirmada",          
        ),
    )

    logger.info(f"Novo cliente cadastrado: {req.email}")
    return RegistroResponse(sucesso=True, mensagem="Conta criada com sucesso!")

@router.post("/registro/organizador", response_model=RegistroResponse, status_code=201)
def criar_conta_organizador(req: RegistroOrganizadorRequest):
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

@router.post("/registro/validador", response_model=RegistroResponse, status_code=201)
def criar_conta_validador(req: RegistroValidadorRequest):
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
            "validador",
            datetime.now(timezone.utc),
            "confirmada",
        ),
    )

    return RegistroResponse(
        sucesso=True,
        mensagem="Conta de validador criada com sucesso!"
    )

@router.delete("/conta/{email}")
def deletar_conta(email: str):
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

def _deletar_eventos_do_organizador(session, id_organizador):
    BUCKET = "todos"
    rows = session.execute(
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


def _verificar_email_e_cpf_unicos(session, email: str, cpf: str, tipo : str):
    existente = session.execute(
        "SELECT email FROM usuarios_por_email WHERE email = %s AND tipo = %s",
        (email.lower().strip(),tipo,)
    ).one()
    if existente:
        raise HTTPException(status_code=400, detail="Este e-mail já está cadastrado.")

    cpf_existente = session.execute(
        "SELECT email FROM usuarios_por_email WHERE cpf = %s AND tipo = %s",
        (cpf,tipo,)
    ).one()
    if cpf_existente:
        raise HTTPException(status_code=400, detail="Este CPF já está cadastrado.")