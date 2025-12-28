# MCP Text-to-SQL

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://www.docker.com/)

**MCP Server que traduce consultas en lenguaje natural a queries ejecutables sobre múltiples fuentes de datos.**

## 🚀 Características

- **Multi-fuente**: PostgreSQL, MySQL, SQLite, MongoDB, DynamoDB, CSV, Excel
- **Lenguaje Natural**: Traduce preguntas en español/inglés a queries ejecutables
- **Modos de Consulta**: SQL, NoSQL, Archivos o Mixto
- **Preview**: Ver query generado antes de ejecutar
- **Arquitectura Limpia**: Hexagonal Architecture con SOLID principles

## 📋 Requisitos

- Docker & Docker Compose
- OpenAI API Key (para traducción NL→Query)

## ⚡ Quick Start

### 1. Clonar y configurar

```bash
git clone <repository-url>
cd mcp-text-to-sql

# Copiar configuración de entorno
cp .env.example .env

# IMPORTANTE: Editar .env y agregar tu OpenAI API key
nano .env  # o vim .env
```

### 2. Configurar tu API Key

Edita `.env` y reemplaza el valor de `OPENAI_API_KEY`:

```env
OPENAI_API_KEY=sk-your-actual-openai-api-key-here
```

### 3. Levantar servicios

```bash
# Build y run
make build
make up

# Verificar que está corriendo
curl http://localhost:8000/health
# {"status": "healthy"}
```

### 4. ¡Listo para usar!

El servidor MCP está disponible en `http://localhost:8000`.

## 🛠️ Comandos Make

| Comando | Descripción |
|---------|-------------|
| `make build` | Build Docker images |
| `make up` | Iniciar servicios |
| `make down` | Detener servicios |
| `make logs` | Ver logs |
| `make test` | Ejecutar tests |
| `make lint` | Ejecutar linter |
| `make shell` | Shell en el contenedor |

## 📡 MCP Tools

### Gestión de Datasources

```bash
# Configurar PostgreSQL
curl -X POST http://localhost:8000/mcp/configure_datasource \
  -H "Content-Type: application/json" \
  -d '{
    "id": "main_db",
    "name": "Base de Datos Principal",
    "type": "postgresql",
    "connection_string": "postgresql://user:pass@host:5432/dbname"
  }'

# Listar datasources
curl http://localhost:8000/mcp/list_datasources

# Cambiar modo
curl -X POST http://localhost:8000/mcp/set_query_mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "sql"}'
```

### Ejecutar Consultas

```bash
# Consulta en lenguaje natural
curl -X POST http://localhost:8000/mcp/query \
  -H "Content-Type: application/json" \
  -d '{"query": "¿Cuántos usuarios se registraron en diciembre?"}'

# Preview (ver query sin ejecutar)
curl -X POST http://localhost:8000/mcp/preview_query \
  -H "Content-Type: application/json" \
  -d '{"query": "Muéstrame los 10 productos más vendidos"}'

# Exportar resultados
curl -X POST http://localhost:8000/mcp/export_results \
  -H "Content-Type: application/json" \
  -d '{"format": "csv"}'
```

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
├── Makefile
└── .env.example
```

## 🔒 Seguridad

- Las credenciales nunca se exponen en logs
- Modo read-only por defecto (solo SELECT)
- Variables sensibles via `.env` (no commitear)

## 🧪 Testing

```bash
# Todos los tests
make test

# Solo unit tests
make test-unit

# Solo integration tests
make test-integration
```

## 📝 Licencia

MIT
