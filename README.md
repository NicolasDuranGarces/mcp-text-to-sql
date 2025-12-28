# MCP Text-to-SQL

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://www.docker.com/)

**MCP Server que traduce consultas en lenguaje natural a queries ejecutables sobre múltiples fuentes de datos.**

## 🚀 Características

- **Multi-fuente**: PostgreSQL, MySQL, SQLite, MongoDB, CSV, Excel
- **Multi-LLM**: OpenAI (o1, gpt-4o), Anthropic (Claude), Google Gemini
- **Lenguaje Natural**: Traduce preguntas en español/inglés a queries ejecutables
- **Respuestas Humanizadas**: Responde de forma natural para usuarios no técnicos
- **Modos de Consulta**: SQL, NoSQL, Archivos o Mixto
- **Seguridad**: Connection strings via variables de entorno, modo read-only
- **Arquitectura Limpia**: Hexagonal Architecture con SOLID principles

## 📋 Requisitos

- Docker & Docker Compose
- API Key de OpenAI, Anthropic, o Google Gemini

## ⚡ Quick Start

```bash
# Clonar y configurar
git clone <repository-url>
cd mcp-text-to-sql

# Copiar y editar configuración
cp .env.example .env
nano .env  # Agregar tu API key

# Build y run
make build && make up

# Verificar
curl http://localhost:8000/health
```

---

## 📦 Configuración de Datasources

### 🔒 Método Seguro (Recomendado)

Usa `connection_string_env` para referenciar variables de entorno en lugar de pasar credenciales en el body:

**1. Agregar conexión en `.env`:**
```env
# Tus conexiones de base de datos
POSTGRES_MAIN_URL=postgresql://user:password@host:5432/dbname
MONGO_ORDERS_URL=mongodb://user:password@host:27017/orders
MYSQL_LEGACY_URL=mysql://user:password@host:3306/legacy
```

**2. Configurar datasource referenciando la variable:**
```bash
curl -X POST http://localhost:8000/mcp/configure_datasource \
  -H "Content-Type: application/json" \
  -d '{
    "id": "main_db",
    "name": "Base de Datos Principal",
    "type": "postgresql",
    "connection_string_env": "POSTGRES_MAIN_URL"
  }'
```

> ⚠️ **Nota**: El método directo con `connection_string` sigue disponible pero NO se recomienda.

---

### 🐘 PostgreSQL

```bash
# En .env
POSTGRES_URL=postgresql://user:password@host:5432/dbname

# Configurar
curl -X POST http://localhost:8000/mcp/configure_datasource \
  -H "Content-Type: application/json" \
  -d '{
    "id": "postgres_main",
    "name": "PostgreSQL Production",
    "type": "postgresql",
    "connection_string_env": "POSTGRES_URL"
  }'
```

### 🐬 MySQL

```bash
# En .env
MYSQL_URL=mysql://user:password@host:3306/dbname

# Configurar
curl -X POST http://localhost:8000/mcp/configure_datasource \
  -H "Content-Type: application/json" \
  -d '{
    "id": "mysql_legacy",
    "name": "MySQL Legacy System",
    "type": "mysql",
    "connection_string_env": "MYSQL_URL"
  }'
```

### 🍃 MongoDB

```bash
# En .env
MONGO_URL=mongodb://user:password@host:27017/dbname

# Configurar
curl -X POST http://localhost:8000/mcp/configure_datasource \
  -H "Content-Type: application/json" \
  -d '{
    "id": "mongo_orders",
    "name": "MongoDB Orders",
    "type": "mongodb",
    "connection_string_env": "MONGO_URL"
  }'
```

### 📊 SQLite

```bash
# SQLite en archivo local (sin credenciales, usa path directo)
curl -X POST http://localhost:8000/mcp/configure_datasource \
  -H "Content-Type: application/json" \
  -d '{
    "id": "sqlite_local",
    "name": "SQLite Local",
    "type": "sqlite",
    "connection_string": "sqlite:///data/local.db"
  }'
```

### 📄 CSV

```bash
# Archivo CSV (montado en /app/data dentro del contenedor)
curl -X POST http://localhost:8000/mcp/configure_datasource \
  -H "Content-Type: application/json" \
  -d '{
    "id": "sales_csv",
    "name": "Ventas CSV",
    "type": "csv",
    "file_path": "/app/data/sales.csv"
  }'
```

### 📗 Excel

```bash
# Archivo Excel
curl -X POST http://localhost:8000/mcp/configure_datasource \
  -H "Content-Type: application/json" \
  -d '{
    "id": "inventory_excel",
    "name": "Inventario Excel",
    "type": "excel",
    "file_path": "/app/data/inventory.xlsx"
  }'
```

---

## 🎯 Modos de Consulta

Puedes cambiar el modo para filtrar qué datasources están disponibles:

```bash
# Solo SQL (PostgreSQL, MySQL, SQLite)
curl -X POST http://localhost:8000/mcp/set_query_mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "sql"}'

# Solo NoSQL (MongoDB)
curl -X POST http://localhost:8000/mcp/set_query_mode \
  -d '{"mode": "nosql"}'

# Solo Archivos (CSV, Excel)
curl -X POST http://localhost:8000/mcp/set_query_mode \
  -d '{"mode": "files"}'

# Mixto (todos)
curl -X POST http://localhost:8000/mcp/set_query_mode \
  -d '{"mode": "mixed"}'
```

---

## 💬 Ejecutar Consultas

Las respuestas son en lenguaje natural, perfectas para usuarios no técnicos:

```bash
# Consulta en lenguaje natural
curl -X POST http://localhost:8000/mcp/query \
  -H "Content-Type: application/json" \
  -d '{"query": "¿Cuántos clientes hay registrados?"}'

# Respuesta:
# {
#   "message": "¡Encontré 4 clientes registrados! ¿Te gustaría ver más detalles?",
#   "data": {...}
# }
```

```bash
# Preview (ver query sin ejecutar)
curl -X POST http://localhost:8000/mcp/preview_query \
  -H "Content-Type: application/json" \
  -d '{"query": "Muéstrame los 10 productos más vendidos"}'
```

---

## 🤖 Configuración Multi-LLM

### OpenAI (Default)
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=o1  # o: gpt-4o, o1-mini
```

### Anthropic (Claude)
```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-key-here
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

### Google Gemini
```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.0-flash
```

### Auto-detección
```env
LLM_PROVIDER=auto  # Usa el primer provider con API key configurada
```

---

## 🛠️ Comandos Make

| Comando | Descripción |
|---------|-------------|
| `make build` | Build Docker images |
| `make up` | Iniciar servicios |
| `make down` | Detener servicios |
| `make logs` | Ver logs |
| `make test` | Ejecutar tests |
| `make shell` | Shell en el contenedor |

---

## 📁 Estructura del Proyecto

```
mcp-text-to-sql/
├── src/
│   ├── domain/           # Entidades y Puertos (interfaces)
│   ├── application/      # Servicios de aplicación
│   ├── infrastructure/   # Adaptadores (SQL, NoSQL, Files, LLM)
│   └── api/              # FastAPI + MCP Tools
├── tests/
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

---

## 🔒 Seguridad

- ✅ Connection strings via variables de entorno (`connection_string_env`)
- ✅ Credenciales nunca expuestas en logs ni respuestas
- ✅ Modo read-only por defecto (solo SELECT)
- ✅ Variables sensibles via `.env` (no commitear)

---

## 📝 Licencia

MIT
