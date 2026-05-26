# Happy Hour — Backend (FastAPI + Cassandra)

Backend da plataforma de ingressos Happy Hour, desenvolvido para a disciplina de
Análise e Projeto de Sistemas — UNIRIO / Escola de Informática Aplicada.

---

## Estrutura do projeto

```
happyhour/
├── main.py                     ← ponto de entrada (uvicorn main:app)
├── requirements.txt
├── .env                        ← variáveis de ambiente (NÃO commitar)
├── docker-compose.yml          ← sobe o Cassandra local
└── app/
    ├── db/
    │   └── cassandra.py        ← conexão singleton + DDL automático
    ├── routers/
    │   ├── auth.py             ← /api/login, /api/registro
    │   ├── eventos.py          ← /api/eventos (CRUD)
    │   └── tickets.py          ← /api/tickets, /api/checkin, /api/vagas
    ├── schemas/
    │   └── schemas.py          ← modelos Pydantic (validação)
    └── utils/
        └── security.py         ← hash bcrypt de senha
```

---

## Passo a passo para rodar

### 1. Pré-requisitos

- Python 3.10+
- Docker + Docker Compose (para subir o Cassandra)
- Git

### 2. Clonar e instalar dependências

```bash
# Entre na pasta do projeto
cd happyhour

# Crie o ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Instale as dependências
pip install -r requirements.txt
```

### 3. Subir o Cassandra com Docker

```bash
docker-compose up -d
```

Aguarde ~60 segundos até o Cassandra estar saudável:

```bash
docker-compose ps        # STATUS deve ser "healthy"
```

Se quiser verificar manualmente:

```bash
docker exec -it happyhour-cassandra cqlsh
# Dentro do cqlsh:
DESCRIBE KEYSPACES;      # deve aparecer 'happy_hour' após o primeiro start da API
```

### 4. Configurar o .env

O arquivo `.env` já vem com valores padrão para desenvolvimento local.
Edite se necessário:

```
CASSANDRA_HOSTS=127.0.0.1
CASSANDRA_PORT=9042
CASSANDRA_KEYSPACE=happy_hour
SECRET_KEY=troque_por_uma_chave_aleatoria_longa_aqui
```

### 5. Rodar a API

```bash
uvicorn main:app --reload --port 8000
```

No primeiro start, a API vai:
1. Conectar ao Cassandra
2. Criar o keyspace `happy_hour` automaticamente
3. Criar todas as tabelas automaticamente

Acesse a documentação interativa em: **http://127.0.0.1:8000/docs**

---

## Endpoints disponíveis

| Método | Rota | Descrição | Caso de Uso |
|--------|------|-----------|-------------|
| GET  | `/health` | Status da API e Cassandra | — |
| POST | `/api/login` | Login de qualquer usuário | — |
| POST | `/api/registro` | Cadastro de cliente | UC04 |
| POST | `/api/registro/organizador` | Cadastro de organizador | UC04 |
| GET  | `/api/eventos` | Listar eventos públicos | UC05 |
| POST | `/api/eventos` | Criar evento | UC02 |
| PUT  | `/api/eventos/{id}` | Editar evento | UC02 |
| DELETE | `/api/eventos/{id}` | Excluir evento | UC02 |
| GET  | `/api/organizadores/{id}/eventos` | Eventos do organizador | UC02 |
| POST | `/api/tickets` | Comprar ingresso | UC01 |
| GET  | `/api/tickets/{id_cliente}` | Histórico do cliente | UC01 |
| POST | `/api/checkin` | Validar ticket na entrada | UC03 |
| GET  | `/api/vagas/{id_evento}` | Vagas disponíveis | RN003 |
| PATCH | `/api/tickets/{id}/cancelar` | Cancelar ingresso | RN002 |

---

## Como o Cassandra é usado

O backend usa o **cassandra-driver** oficial da DataStax.
A conexão segue o padrão de singleton recomendado: uma única sessão
é criada no startup do FastAPI e injetada nos endpoints via `get_session()`.

### Tabelas criadas automaticamente

| Tabela | Partition Key | Para que serve |
|--------|--------------|----------------|
| `usuarios_por_email` | email | Login O(1), unicidade de CPF |
| `eventos_por_organizador` | id_organizador | Painel do organizador (UC02) |
| `eventos_publicos` | bucket="todos" | Listagem pública (UC05) |
| `tickets_por_cliente` | id_cliente | Histórico de compras (UC01) |
| `tickets_por_evento` | id_evento | Check-in pelo validador (UC03) |
| `vagas_evento` | id_evento | Contador atômico de vagas (RN003) |

### Por que duas tabelas de eventos?

O Cassandra não permite queries sem a partition key. Por isso um mesmo evento
é gravado em duas tabelas (desnormalização intencional):
- `eventos_por_organizador` → consultas pelo organizador
- `eventos_publicos` → listagem geral para o site

---

## Conectar o frontend

O `login.js` e `login-organizador.js` já fazem `fetch('http://127.0.0.1:8000/api/login')`.
Nenhuma mudança é necessária — o CORS já está configurado para aceitar qualquer origem
em desenvolvimento.

---

## Próximos passos sugeridos

- [ ] Implementar JWT para sessão autenticada (não usar `localStorage` em produção)
- [ ] Adicionar confirmação por e-mail (status `aguardando_confirmacao`)
- [ ] Integrar gateway de pagamento (Stripe / PagSeguro) antes de emitir o ticket
- [ ] Trocar `SimpleStrategy` por `NetworkTopologyStrategy` ao escalar para cluster
- [ ] Adicionar testes com `pytest` + `pytest-asyncio`
