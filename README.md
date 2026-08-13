# Alterna Mobile (ALTM) - Backend Services

Este repositorio contiene el backend robusto, seguro, auditable y escalable para **Alterna Mobile (ALTM)**. El sistema está construido bajo un enfoque de **Arquitectura Limpia / Hexagonal**, utilizando Python 3.11+ y FastAPI, integrando persistencia transaccional con PostgreSQL 16 y una capa de mensajería/caché/gestión de sesiones mediante Redis.

---

## 🏗️ Arquitectura del Sistema

El proyecto sigue rigurosamente los principios de diseño de puertos y adaptadores (Arquitectura Hexagonal) para desacoplar las reglas de negocio de los detalles de infraestructura.

```mermaid
flowchart TD
    subgraph "Capas de Arquitectura"
        Domain["Domain (Reglas de Negocio / Modelos)"]
        UseCases["Use Cases (Casos de Uso / Aplicación)"]
        Ports["Ports (Definición de Interfaces/Contratos)"]
        Adapters["Adapters (Implementaciones de Infraestructura)"]
    end

    Adapters --> Ports
    UseCases --> Ports
    UseCases --> Domain
    Ports --> Domain
```

### Estructura del Código

- `app/domain/`: Contiene los modelos y entidades de negocio puros, libres de acoplamientos a bases de datos o frameworks externos.
- `app/usecases/`: Implementa las reglas de negocio de la aplicación (e.g. lógica de autenticación, step-up, transferencias).
- `app/ports/`: Define las interfaces abstractas (Protocolos) para bases de datos, APIs de custodios externos y servicios de mensajería.
- `app/adapters/`: Implementaciones de bajo nivel de los puertos definidos, tales como repositorios SQLAlchemy para PostgreSQL, clientes de Redis, etc.
- `app/core/`: Configuraciones de la aplicación, constantes y utilidades transversales (seguridad, cifrado, variables de entorno).

---

## 🛠️ Requisitos Previos

Antes de comenzar, asegúrate de tener instalado:

- **Python** (versión 3.11 o 3.12 recomendada)
- **Docker** y **Docker Compose**
- Un cliente de base de datos de tu preferencia (opcional)

---

## 🐳 Despliegue con Docker (Recomendado)

Se ha integrado soporte completo para contenedores utilizando un archivo `Dockerfile` optimizado y un entorno de orquestación multiproceso estructurado con `docker-compose.yml`. Esto levanta de forma automática e integrada:
1. Una base de datos relacional **PostgreSQL 16**.
2. Un servidor de almacenamiento in-memory y caché **Redis 7**.
3. La aplicación de **FastAPI (Alterna Backend)**.

### Pasos para iniciar con Docker Compose:

1. **Clonar e iniciar los servicios:**
   Levanta la base de datos, Redis y el backend con un solo comando:
   ```bash
   docker-compose up --build
   ```

2. **Acceder a la aplicación:**
   Una vez que el contenedor esté corriendo, podrás acceder a la aplicación en:
   - **API Backend:** `http://localhost:8000`
   - **Documentación Swagger UI (Interactive API Docs):** `http://localhost:8000/docs`
   - **Documentación ReDoc:** `http://localhost:8000/redoc`

3. **Detener los servicios:**
   Para apagar y eliminar los contenedores sin borrar los datos persistidos (las bases de datos se respaldan en volúmenes persistentes locales):
   ```bash
   docker-compose down
   ```

---

## 💻 Instalación y Ejecución Local (Desarrollo Manual)

Si prefieres ejecutar el entorno localmente fuera de contenedores, sigue estos pasos:

### 1. Configuración de Entorno Virtual

Crea y activa un entorno virtual de Python:

```bash
# Crear el entorno virtual
python -m venv venv

# Activar en Linux/macOS
source venv/bin/activate

# Activar en Windows
venv\Scripts\activate
```

### 2. Instalación de Dependencias

Instala todas las librerías necesarias especificadas en el archivo de requisitos:

```bash
pip install -r requirements.txt
```

### 3. Configurar Variables de Entorno

Puedes crear un archivo `.env` en la raíz del proyecto para definir la conectividad y configuraciones del sistema (asegúrate de levantar previamente PostgreSQL 16 y Redis de manera independiente):

```env
DATABASE_URL=postgresql://postgres:password123@localhost:5432/altm_db
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=supersecretjwtkeyforaltmdevelopment123!
```

### 4. Ejecutar la Aplicación

Inicia el servidor local de desarrollo con recarga en caliente utilizando `uvicorn`:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

---

## 🧪 Ejecución de Pruebas Unitarias e Integración

El proyecto incluye una suite completa de pruebas utilizando `pytest`.

Para correr los tests en tu entorno de desarrollo local, ejecuta:

```bash
python -m pytest
```

O si deseas ver una salida detallada:

```bash
pytest -v
```

---

## ⚙️ Configuración del Entorno de Producción

En entornos de producción, asegúrate de:
1. **Reemplazar secretos predeterminados:** Cambiar `JWT_SECRET` y contraseñas de PostgreSQL por valores complejos generados de forma segura mediante variables de entorno del host o gestores de secretos.
2. **Cifrado de Comunicaciones:** Toda comunicación entre el cliente (PWA Mobile) y el back-end debe realizarse estrictamente bajo TLS (HTTPS y WSS) utilizando certificados válidos.
3. **Gestión de Migraciones (Alembic):** Ejecutar las migraciones de base de datos de manera secuencial antes del despliegue productivo del código de la aplicación.
