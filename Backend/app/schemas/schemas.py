from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime
import uuid

class LoginRequest(BaseModel):
    email: str
    senha: str


class LoginResponse(BaseModel):
    sucesso: bool
    nome: str
    tipo: str                    
    id_usuario: str


class RegistroClienteRequest(BaseModel):
    nome: str
    email: str
    cpf: str
    senha: str

    @field_validator("cpf")
    @classmethod
    def cpf_apenas_digitos(cls, v: str) -> str:
        return v.replace(".", "").replace("-", "").replace("/", "")


class RegistroOrganizadorRequest(BaseModel):
    nome: str                     
    email: str
    cpf: str
    senha: str
    tipo: str = "organizador"
    nome_organizacao: Optional[str] = None
    tipo_organizacao: Optional[str] = None

    @field_validator("cpf")
    @classmethod
    def cpf_apenas_digitos(cls, v: str) -> str:
        return v.replace(".", "").replace("-", "").replace("/", "")


class RegistroResponse(BaseModel):
    sucesso: bool
    mensagem: str


class EventoCreate(BaseModel):
    titulo: str
    descricao: Optional[str] = ""
    data_hora: datetime
    local: str
    capacidade_maxima: int
    categoria: Optional[str] = "outros"
    status: Optional[str] = "rascunho"


class EventoResponse(BaseModel):
    id_evento: str
    id_organizador: str
    titulo: str
    descricao: str
    data_hora: datetime
    local: str
    capacidade_maxima: int
    categoria: str
    status: str
    vendidos: int = 0
    receita: float = 0.0


class CompraRequest(BaseModel):
    id_evento: str
    id_cliente: str
    titulo_evento: str
    data_evento: datetime
    local_evento: str
    valor_pago: float
    forma_pagamento: str          


class TicketResponse(BaseModel):
    id_ticket: str
    id_evento: str        # necessário para cancelamento e deleção no frontend
    codigo_qr: str
    status: str
    data_compra: datetime
    titulo_evento: str
    valor_pago: float


class CheckinRequest(BaseModel):
    id_evento: str
    codigo_qr: str


class CheckinResponse(BaseModel):
    autorizado: bool
    mensagem: str
    nome_cliente: Optional[str] = None


class LoteCreate(BaseModel):
    nome: str
    preco: float
    quantidade: int


class LoteResponse(BaseModel):
    id_lote: str
    id_evento: str
    nome: str
    preco: float
    quantidade: int