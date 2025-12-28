# Arquitectura del Sistema: MCP Text-to-SQL

Este documento detalla la arquitectura, decisiones de diseño y flujos de datos del sistema **MCP Text-to-SQL**.

## 1. Visión General de Arquitectura

El proyecto sigue una **Arquitectura Hexagonal (Ports & Adapters)** estricta para garantizar:
- **Desacoplamiento**: La lógica de negocio (Dominio/Aplicación) no depende de frameworks externos.
- **Testabilidad**: Componentes fáciles de mockear y probar aisladamente.
- **Extensibilidad**: Fácil adición de nuevos motores de base de datos o proveedores LLM sin tocar el núcleo.

```mermaid
graph TB
    subgraph "Infrastructure (Adapters)"
        API[FastAPI / MCP Tools]
        CLI[Command Line]
        
        subgraph "Persistencia"
            PG[PostgreSQL Adapter]
            MNG[MongoDB Adapter]
            FL[File Adapters]
        end
        
        subgraph "AI"
            LLM[LLM Translators]
        end
    end

    subgraph "Application (Services)"
        QS[QueryService]
        DS[DatasourceService]
    end

    subgraph "Domain (Core)"
        Ent[Entities: Query, Result]
        Ports[Ports: DatasourcePort, TranslatorPort]
    end

    API --> QS & DS
    QS --> Ports
    DS --> Ports
    
    PG & MNG & FL -.->|Implements| Ports
    LLM -.->|Implements| Ports
```

---

## 2. Patrones de Diseño Clave

### A. Template Method (LLM Translation)
Utilizado en el módulo de traducción para evitar duplicación de código (DRY) y mantener consistencia.

- **`BaseTranslator`**: Clase abstracta que define el esqueleto del algoritmo de traducción (`translate`). Implementa la lógica común (prompting, filtrado de contexto, parsing de JSON).
- **Subclases (`OpenAITranslator`, etc.)**: Solo implementan los métodos abstractos específicos del proveedor (`_call_llm`, `explain_query`).

```mermaid
classDiagram
    class TranslatorPort {
        <<interface>>
        +translate()
    }

    class BaseTranslator {
        <<Abstract>>
        +translate() Result
        #_filter_by_mode()
        #_build_system_prompt()
        #_call_llm()* Abstract
    }

    class OpenAITranslator {
        #_call_llm()
    }
    class AnthropicTranslator {
        #_call_llm()
    }
    class GeminiTranslator {
        #_call_llm()
    }

    TranslatorPort <|.. BaseTranslator
    BaseTranslator <|-- OpenAITranslator
    BaseTranslator <|-- AnthropicTranslator
    BaseTranslator <|-- GeminiTranslator
```

### B. Dependency Inversion & Factory (Datasources)
El `DatasourceService` no conoce las clases concretas de los adaptadores (e.g., `PostgreSQLAdapter`). Usa una `AdapterFactory` inyectada para crear instancias que cumplen con el protocolo `DatasourcePort`.

```mermaid
classDiagram
    class DatasourceService {
        -factory: AdapterFactory
        +get_adapter(id) DatasourcePort
    }

    class AdapterFactory {
        +create(Datasource) DatasourcePort
        +register(type, class)
    }

    class DatasourcePort {
        <<interface>>
        +connect()
        +execute(query)
    }

    DatasourceService --> AdapterFactory
    DatasourceService --> DatasourcePort
    AdapterFactory ..> DatasourcePort : Creates
```

---

## 3. Flujo de Ejecución: "Text-to-SQL"

Diagrama de secuencia que muestra cómo una consulta en lenguaje natural se transforma en datos.

1. **Usuario** envía query ("¿Cuantos productos hay?").
2. **QueryService** obtiene datasources activos del **DatasourceService**.
3. **QueryService** llama al **Translator** (LLM) con el esquema de la BD.
4. **Translator** genera SQL (o query nativo).
5. **QueryService** obtiene el **Adapter** correspondiente.
6. **Adapter** ejecuta la consulta en la BD real.
7. **Result** se devuelve y opcionalmente se enriquece con una respuesta natural.

```mermaid
sequenceDiagram
    participant User
    participant API as API Layer
    participant QS as QueryService
    participant LLM as LLM Translator
    participant DS as DatasourceService
    participant DB as Database Adapter

    User->>API: Query("¿Cuantos productos?")
    API->>QS: execute_query("¿Cuantos productos?")
    
    QS->>DS: get_active_datasources()
    DS-->>QS: [Datasource(Postgres)]
    
    QS->>LLM: translate(text, schema)
    Note right of LLM: Generates SQL using O1/GPT-4o
    LLM-->>QS: TranslationResult(SELECT count(*) FROM products)
    
    QS->>DS: get_adapter(ds_id)
    DS-->>QS: PostgreSQLAdapter
    
    QS->>DB: execute("SELECT count(*) FROM products")
    DB-->>QS: QueryResult(data=[{count: 5}])
    
    QS->>QS: generate_natural_response()
    QS-->>API: Result("Hay 5 productos...")
    API-->>User: JSON Response
```

## 4. Estructura de Componentes

### Capa de Dominio (`src/domain`)
Define las reglas de negocio y contratos (interfaces).
- **`entities/`**: Objetos puros como `Query`, `QueryResult`, `Datasource`.
- **`ports/`**: Interfaces que debe implementar la infraestructura.

### Capa de Aplicación (`src/application`)
Orquesta los casos de uso.
- **`QueryService`**: Coordina la traducción y ejecución.
- **`DatasourceService`**: Gestiona el ciclo de vida de conexiones.

### Capa de Infraestructura (`src/infrastructure`)
Detalles técnicos externos.
- **`adapters/sql`**: Implementaciones SQLAlchemy para Postgres, MySQL, etc.
- **`adapters/nosql`**: Implementaciones PyMongo.
- **`llm/`**: Integraciones con APIs de IA.
- **`config/`**: Manejo de variables de entorno (Pydantic Settings).

### Capa de API (`src/api`)
Punto de entrada.
- **`mcp_tools`**: Endpoints compatibles con Model Context Protocol.
