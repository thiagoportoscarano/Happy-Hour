"""
app/db/cassandra.py
───────────────────
Gerencia a conexão com o Cassandra como singleton.
A sessão é criada uma vez no startup do FastAPI e reutilizada
em todos os endpoints (best practice do driver oficial).
"""

import os
import logging
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import DCAwareRoundRobinPolicy, RetryPolicy
from cassandra.query import ConsistencyLevel
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── Configurações via .env ──────────────────────────────────────────────────
CASSANDRA_HOSTS    = os.getenv("CASSANDRA_HOSTS", "127.0.0.1").split(",")
CASSANDRA_PORT     = int(os.getenv("CASSANDRA_PORT", 9042))
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "happy_hour")
CASSANDRA_USERNAME = os.getenv("CASSANDRA_USERNAME", "")
CASSANDRA_PASSWORD = os.getenv("CASSANDRA_PASSWORD", "")

# ── Singleton de sessão ─────────────────────────────────────────────────────
_cluster = None
_session = None


def get_session():
    """
    Retorna a sessão Cassandra já conectada.
    Levanta RuntimeError se connect() não foi chamado antes.
    """
    if _session is None:
        raise RuntimeError("Cassandra não conectado. Chame connect() no startup.")
    return _session


def connect():
    """
    Abre a conexão com o Cassandra e cria o keyspace + tabelas se não existirem.
    Deve ser chamado UMA vez no lifespan do FastAPI.
    """
    global _cluster, _session

    # Perfil de execução padrão: QUORUM para leitura e escrita
    profile = ExecutionProfile(
        load_balancing_policy=DCAwareRoundRobinPolicy(),
        retry_policy=RetryPolicy(),
        consistency_level=ConsistencyLevel.LOCAL_QUORUM,
        request_timeout=10.0,
    )

    kwargs = {
        "contact_points": CASSANDRA_HOSTS,
        "port": CASSANDRA_PORT,
        "execution_profiles": {EXEC_PROFILE_DEFAULT: profile},
        "protocol_version": 5,          # Cassandra 4+ / 5
        "connect_timeout": 10,
    }

    # Autenticação (se configurada no .env)
    if CASSANDRA_USERNAME and CASSANDRA_PASSWORD:
        kwargs["auth_provider"] = PlainTextAuthProvider(
            username=CASSANDRA_USERNAME,
            password=CASSANDRA_PASSWORD,
        )

    logger.info(f"Conectando ao Cassandra em {CASSANDRA_HOSTS}:{CASSANDRA_PORT}…")
    _cluster = Cluster(**kwargs)
    _session = _cluster.connect()

    _criar_keyspace()
    _session.set_keyspace(CASSANDRA_KEYSPACE)
    _criar_tabelas()

    logger.info(f"✅ Cassandra conectado — keyspace '{CASSANDRA_KEYSPACE}'")


def disconnect():
    """Fecha a conexão. Chamado no shutdown do FastAPI."""
    global _cluster, _session
    if _session:
        _session.shutdown()
    if _cluster:
        _cluster.shutdown()
    _session = None
    _cluster = None
    logger.info("Cassandra desconectado.")


# ── DDL ─────────────────────────────────────────────────────────────────────

def _criar_keyspace():
    """Cria o keyspace happy_hour se não existir."""
    _session.execute(f"""
        CREATE KEYSPACE IF NOT EXISTS {CASSANDRA_KEYSPACE}
        WITH replication = {{
            'class': 'SimpleStrategy',
            'replication_factor': 1
        }}
        AND durable_writes = true;
    """)
    # Para produção com múltiplos nós, troque por:
    # 'class': 'NetworkTopologyStrategy', 'datacenter1': 3


def _criar_tabelas():
    """
    Cria todas as tabelas do Happy Hour conforme o Esquema Físico
    do documento de especificação (seção 10.5 — Cassandra CQL DDL).

    Tabelas criadas:
      - usuarios_por_email      → autenticação / lookup de login
      - eventos_por_organizador → listagem e gestão de eventos (UC02)
      - tickets_por_cliente     → histórico de compras do cliente (UC01)
      - tickets_por_evento      → check-in pelo validador (UC03)
      - vagas_evento            → contador atômico de vagas (RN003)
    """

    # 1. Usuários — partition key = email (O(1) para login)
    _session.execute("""
        CREATE TABLE IF NOT EXISTS usuarios_por_email (
            email           TEXT,
            id_usuario      UUID,
            nome            TEXT,
            cpf             TEXT,
            senha_hash      TEXT,
            tipo            TEXT,
            data_cadastro   TIMESTAMP,
            status_conta    TEXT,
            PRIMARY KEY (email)
        );
    """)

    # Índice secundário para garantir unicidade de CPF (UC04)
    _session.execute("""
        CREATE INDEX IF NOT EXISTS idx_usuarios_cpf
        ON usuarios_por_email (cpf);
    """)

    # 2. Eventos por organizador — clustering por data (mais recente primeiro)
    _session.execute("""
        CREATE TABLE IF NOT EXISTS eventos_por_organizador (
            id_organizador      UUID,
            data_hora           TIMESTAMP,
            id_evento           UUID,
            titulo              TEXT,
            descricao           TEXT,
            local               TEXT,
            capacidade_maxima   INT,
            categoria           TEXT,
            PRIMARY KEY (id_organizador, data_hora, id_evento)
        ) WITH CLUSTERING ORDER BY (data_hora DESC, id_evento ASC);
    """)

    # 3. Todos os eventos — para a listagem pública (UC05)
    #    Partition key estática 'todos' agrupa tudo numa partição consultável
    _session.execute("""
        CREATE TABLE IF NOT EXISTS eventos_publicos (
            bucket          TEXT,
            data_hora       TIMESTAMP,
            id_evento       UUID,
            id_organizador  UUID,
            titulo          TEXT,
            descricao       TEXT,
            local           TEXT,
            capacidade_maxima INT,
            categoria       TEXT,
            PRIMARY KEY (bucket, data_hora, id_evento)
        ) WITH CLUSTERING ORDER BY (data_hora DESC, id_evento ASC);
    """)

    # 4. Tickets por cliente — histórico de compras
    _session.execute("""
        CREATE TABLE IF NOT EXISTS tickets_por_cliente (
            id_cliente          UUID,
            data_compra         TIMESTAMP,
            id_ticket           UUID,
            id_evento           UUID,
            titulo_evento       TEXT,
            data_evento         TIMESTAMP,
            local_evento        TEXT,
            codigo_qr           TEXT,
            status              TEXT,
            valor_pago          DECIMAL,
            forma_pagamento     TEXT,
            PRIMARY KEY (id_cliente, data_compra, id_ticket)
        ) WITH CLUSTERING ORDER BY (data_compra DESC, id_ticket ASC);
    """)

    # Índice para lookup por QR Code no histórico
    _session.execute("""
        CREATE INDEX IF NOT EXISTS idx_tickets_cliente_qr
        ON tickets_por_cliente (codigo_qr);
    """)

    # 5. Tickets por evento — check-in pelo validador (UC03)
    _session.execute("""
        CREATE TABLE IF NOT EXISTS tickets_por_evento (
            id_evento           UUID,
            codigo_qr           TEXT,
            id_ticket           UUID,
            id_cliente          UUID,
            nome_cliente        TEXT,
            status_validacao    TEXT,
            data_checkin        TIMESTAMP,
            PRIMARY KEY (id_evento, codigo_qr)
        ) WITH CLUSTERING ORDER BY (codigo_qr ASC);
    """)

    # 6. Vagas por evento — COUNTER atômico (RN003)
    _session.execute("""
        CREATE TABLE IF NOT EXISTS vagas_evento (
            id_evento           UUID PRIMARY KEY,
            vagas_disponiveis   COUNTER,
            total_vendidos      COUNTER
        );
    """)

    logger.info("Tabelas Cassandra verificadas/criadas com sucesso.")
