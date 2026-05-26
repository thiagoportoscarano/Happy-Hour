from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from cassandra.cluster import Cluster
import uuid

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# CONEXÃO E CORREÇÃO AUTOMÁTICA DO BANCO DE DADOS
# ---------------------------------------------------------
try:
    cluster = Cluster(['127.0.0.1'])
    session = cluster.connect('happyhour')
    
    # 1. Tabela de Organizadores
    session.execute("""
        CREATE TABLE IF NOT EXISTS organizadores (
            email text PRIMARY KEY,
            nome text,
            cpf text,
            senha text,
            tipo text
        )
    """)
    # Corrige a tabela se ela for antiga (adiciona a coluna 'tipo')
    try: session.execute("ALTER TABLE organizadores ADD tipo text")
    except: pass

    # 2. Tabela de Eventos (agora com id_organizador e status)
    session.execute("""
        CREATE TABLE IF NOT EXISTS eventos (
            id_evento text PRIMARY KEY,
            id_organizador text,
            titulo text,
            categoria text,
            data_hora text,
            local text,
            capacidade_maxima int,
            descricao text,
            status text
        )
    """)
    # Corrige a tabela se ela for antiga
    try: session.execute("ALTER TABLE eventos ADD id_organizador text")
    except: pass
    try: session.execute("ALTER TABLE eventos ADD status text")
    except: pass

    # 3. Cria um índice para permitir filtrar rapidamente os eventos de um organizador
    session.execute("CREATE INDEX IF NOT EXISTS idx_org ON eventos (id_organizador)")

    # 4. Criação de usuários de Teste automáticos para te ajudar a validar
    session.execute("INSERT INTO organizadores (email, nome, cpf, senha, tipo) VALUES ('contato@djprod.com', 'DJ Productions (Dono)', '11122233344', '123456', 'organizador') IF NOT EXISTS")
    session.execute("INSERT INTO organizadores (email, nome, cpf, senha, tipo) VALUES ('colab@djprod.com', 'Lucas (Colaborador)', '00000000000', '123456', 'colaborador') IF NOT EXISTS")

except Exception as e:
    print(f"⚠️ Alerta Cassandra: {e}")

# ---------------------------------------------------------
# MODELOS DE DADOS
# ---------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    senha: str

class RegistroRequest(BaseModel):
    nome: str
    email: str
    cpf: str
    senha: str
    tipo: Optional[str] = "organizador"

class EventoRequest(BaseModel):
    titulo: str
    categoria: str
    data_hora: str
    local: str
    capacidade_maxima: int
    descricao: str
    status: Optional[str] = "rascunho"

# ---------------------------------------------------------
# ENDPOINTS DE AUTENTICAÇÃO
# ---------------------------------------------------------
@app.post("/api/login")
def fazer_login(req: LoginRequest):
    # Agora puxamos explicitamente o "tipo" do banco
    query = session.prepare("SELECT email, nome, senha, tipo FROM organizadores WHERE email = ?")
    resultado = session.execute(query, [req.email]).one()
    
    if resultado and resultado.senha == req.senha:
        return {
            "sucesso": True, 
            "nome": resultado.nome,
            "id_usuario": resultado.email,
            "tipo": resultado.tipo or "cliente" # Devolve o cargo correto para o Frontend!
        }
    raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

@app.post("/api/registro")
def criar_conta(req: RegistroRequest):
    check = session.prepare("SELECT email FROM organizadores WHERE email = ?")
    if session.execute(check, [req.email]).one():
        raise HTTPException(status_code=400, detail="Este e-mail já está cadastrado.")
    
    insert = session.prepare("INSERT INTO organizadores (email, nome, cpf, senha, tipo) VALUES (?, ?, ?, ?, ?)")
    session.execute(insert, [req.email, req.nome, req.cpf, req.senha, req.tipo])
    return {"sucesso": True, "mensagem": "Conta criada com sucesso!"}

# ---------------------------------------------------------
# ENDPOINTS DE EVENTOS (COM TRAVAS DE SEGURANÇA)
# ---------------------------------------------------------
@app.get("/api/eventos")
def listar_todos_eventos():
    # Usado na página principal (Home) para ver todos
    try:
        rows = session.execute("SELECT * FROM eventos")
        return [dict(r._asdict()) for r in rows]
    except:
        return []

@app.get("/api/organizadores/{id_organizador}/eventos")
def listar_eventos_org(id_organizador: str):
    # O endpoint que o painel tenta acessar para listar eventos
    try:
        query = session.prepare("SELECT * FROM eventos WHERE id_organizador = ?")
        rows = session.execute(query, [id_organizador])
        return [dict(r._asdict()) for r in rows]
    except:
        return []

@app.post("/api/eventos")
def criar_evento(evento: EventoRequest, id_organizador: str):
    # TRAVA: Somente 'organizador' pode criar
    user = session.execute("SELECT tipo FROM organizadores WHERE email=?", [id_organizador]).one()
    if not user or user.tipo != 'organizador':
        raise HTTPException(status_code=403, detail="Apenas os organizadores donos podem criar eventos.")

    id_evento = str(uuid.uuid4())[:8]
    insert = session.prepare("""
        INSERT INTO eventos (id_evento, id_organizador, titulo, categoria, data_hora, local, capacidade_maxima, descricao, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """)
    session.execute(insert, [
        id_evento, id_organizador, evento.titulo, evento.categoria, 
        evento.data_hora, evento.local, evento.capacidade_maxima, 
        evento.descricao, evento.status
    ])
    return {"sucesso": True, "id_evento": id_evento}

@app.put("/api/eventos/{id_evento}")
def editar_evento(id_evento: str, evento: EventoRequest, id_organizador: str):
    # TRAVA: Apenas o dono do evento pode editá-lo
    ev = session.execute("SELECT id_organizador FROM eventos WHERE id_evento=?", [id_evento]).one()
    if not ev or ev.id_organizador != id_organizador:
        raise HTTPException(status_code=403, detail="Acesso negado. Você não tem permissão para editar este evento.")

    update = session.prepare("""
        UPDATE eventos SET titulo=?, categoria=?, data_hora=?, local=?, capacidade_maxima=?, descricao=?, status=?
        WHERE id_evento=?
    """)
    session.execute(update, [
        evento.titulo, evento.categoria, evento.data_hora, evento.local, 
        evento.capacidade_maxima, evento.descricao, evento.status, id_evento
    ])
    return {"sucesso": True}

@app.delete("/api/eventos/{id_evento}")
def excluir_evento(id_evento: str, id_organizador: str):
    # TRAVA: Apenas o dono do evento pode excluí-lo
    ev = session.execute("SELECT id_organizador FROM eventos WHERE id_evento=?", [id_evento]).one()
    if not ev or ev.id_organizador != id_organizador:
        raise HTTPException(status_code=403, detail="Acesso negado. Você não tem permissão para excluir este evento.")

    delete = session.prepare("DELETE FROM eventos WHERE id_evento=?")
    session.execute(delete, [id_evento])
    return {"sucesso": True}