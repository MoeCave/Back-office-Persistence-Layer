# Arquitectura Concurrente del Servidor TCP (`asyncio` + `ThreadPoolExecutor`)

## 1. Visión general y modelo híbrido

El servidor TCP (`server.py` / `src/server/app.py`) utiliza un modelo híbrido en dos niveles para atender múltiples clientes simultáneos sin reescribir la capa de dominio ni los repositorios ORM síncronos:

1. **Capa de red no bloqueante (`asyncio`):** Un único *event loop* gestiona el socket de escucha, la lectura/escritura de tramas TCP (`StreamReader` / `StreamWriter`), los *timeouts* por cliente y el control de admisión.
2. **Capa de persistencia aislada (`ThreadPoolExecutor`):** Cada petición válida se delega mediante `loop.run_in_executor(executor, handle_request, envelope, router)` a un *pool* dedicado de hilos (`db-worker-*`), evitando que las consultas a base de datos o la serialización de DTOs congelen al resto de clientes conectados.

```text
Clientes TCP (N conexiones simultáneas, cada uno con su certificado X.509)
  ├── client.py (ServerGateway síncrono, sockets bloqueantes)
  └── AsyncServerGateway (asyncio)
         │
         ▼  Fase 1 — Handshake mutuo M1→M4 (tramas !I + JSON, ≤ 64 KiB)
         ▼  Fase 2 — Sesión: [ !I | seq (!Q) | AES-256-GCM(JSON) + tag ]
┌─────────────────────────────────────────────────────────────────┐
│ Event Loop (asyncio - Hilo Principal)                           │
│  1. asyncio.start_server -> _on_connect()                       │
│  2. asyncio.Semaphore(max_connections)  [Control de admisión]   │
│  3. perform_server_handshake_async  [timeout: handshake_timeout]│
│       valida certificado vs CA, firma RSA-PSS, clave RSA-OAEP   │
│       (operaciones RSA -> run_in_executor)                      │
│  4. wait_for(read_encrypted_message, client_timeout)  [descifra]│
│  5. loop.run_in_executor(executor, handle_request, ...)         │
│  6. wait_for(write_encrypted_message, write_timeout)  [cifra]   │
└───────────────────────────────┬─────────────────────────────────┘
                                │ (cola de tareas acotada)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ ThreadPoolExecutor (max_workers = --workers)                    │
│  [db-worker-0]   [db-worker-1]   ...   [db-worker-W]            │
│       │               │                     │                   │
│       ▼               ▼                     ▼                   │
│  Router.handle -> Service -> UnitOfWork (1 Session por petición)│
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
                   SQLAlchemy Engine (SQLite / PostgreSQL)
```

Un cliente que no supera el handshake (certificado ausente, caducado,
firmado por otra CA, firma inválida o tráfico sin cifrar) recibe
`AUTH_FAILED` y se cierra su conexión **antes** de llegar al *router*.
Los detalles criptográficos están en [`SECURITY.md`](SECURITY.md) y el
formato de las tramas en [`PROTOCOL.md`](PROTOCOL.md).

## 2. Ciclo de vida de una petición y apagado ordenado

```mermaid
sequenceDiagram
    autonumber
    participant C as Cliente TCP
    participant L as Event Loop (handle_client)
    participant E as ThreadPoolExecutor
    participant R as Router + UnitOfWork + BD

    C->>L: Conexión TCP
    L->>L: Comprueba Semaphore(max_connections)
    C->>L: M1 client_hello (certificado, nonce_c)
    L->>E: Valida certificado vs CA + firma M2 (RSA)
    L->>C: M2 server_hello
    C->>L: M3 client_proof
    L->>E: Verifica firma + cifra clave AES (RSA-OAEP)
    L->>C: M4 session_key
    Note over C,L: Sesión AES-256-GCM establecida (si falla: AUTH_FAILED + cierre)
    C->>L: Trama cifrada (!I + seq + ciphertext + tag)
    L->>L: read_encrypted_message [timeout: client_timeout]
    L->>E: await run_in_executor(handle_request)
    E->>R: Abre Session nueva -> Ejecuta consulta -> Commit/Rollback -> Cierra Session
    R-->>E: Envelope respuesta (ok / error)
    E-->>L: Devuelve dict serializable
    L->>C: write_encrypted_message [timeout: write_timeout]
```

### Protocolo de apagado ordenado (*Graceful Shutdown*)

Al recibir `SIGINT` o `SIGTERM` (o activarse `stop_event`):

1. `server.close()` deja de aceptar nuevas conexiones entrantes inmediatamente.
2. `_shutdown_active_tasks(active_tasks)` cancela las tareas de clientes activos (`task.cancel()`), espera su finalización (`asyncio.gather(..., return_exceptions=True)`) y cierra sus `StreamWriter` de forma limpia.
3. `await server.wait_closed()` confirma el cierre del descriptor de escucha (evitando el *deadlock* de Python 3.12+ al ejecutarse después de cancelar las tareas cliente).
4. `executor.shutdown(wait=True)` espera a que finalicen las transacciones en curso en los hilos trabajadores antes de invocar `engine.dispose()`.

## 3. Diseño *Sans-I/O* del protocolo (`src/common/protocol.py`)

La codificación y decodificación de tramas se ha separado de la E/S de red:

* **Núcleo puro (`encode_message`, `decode_header`, `decode_body`):** Opera exclusivamente sobre `bytes` y `dict`, validando el límite `MAX_MESSAGE_BYTES` (64 MiB) antes de reservar memoria para el cuerpo.
* **Tramas cifradas (`encode_encrypted_message`, `decode_encrypted_body`):** Añaden el número de secuencia y delegan en `SessionCipher` (AES-256-GCM) sin tocar la E/S.
* **Adaptador síncrono (`send_message`, `receive_message`):** Utilizado por `ServerGateway` (`src/client/gateway.py`).
* **Adaptador asíncrono (`write_message`, `read_message`):** Utilizado por el servidor y por `AsyncServerGateway` (`src/client/async_gateway.py`), empleando `reader.readexactly(...)` para reensamblar tramas fragmentadas por TCP.

## 4. Controles de resiliencia y seguridad entre hilos

| Mecanismo | Parámetro CLI / Constante | Comportamiento ante fallo o saturación |
| :--- | :--- | :--- |
| **Control de admisión** | `--max-connections` (defecto: `100`) | Si el semáforo está lleno (`semaphore.locked()`), la conexión excedente se cierra de inmediato sin saturar memoria ni descriptores. |
| **Inactividad de lectura** | `--client-timeout` (defecto: `900.0` s) | Desconecta clientes ociosos cuando expira `asyncio.wait_for(read_message(...))`. |
| **Protección *slow-reader*** | `DEFAULT_WRITE_TIMEOUT` (constante, `30.0` s) | Cancela y cierra clientes que no vacían su ventana TCP al recibir respuestas. |
| **JSON o UTF-8 inválido** | `MalformedMessageError` | Responde `BAD_REQUEST` manteniendo alineado el flujo TCP para la siguiente trama. |
| **Trama sobredimensionada** | `MessageTooLargeError` (`> 64 MiB`) | Responde `BAD_REQUEST` y cierra el socket para evitar desincronización del flujo. |
| **Handshake mutuo** | `--handshake-timeout` (defecto: `10.0` s) | Si el cliente no completa M1→M4 a tiempo, o su certificado/firma es inválido, recibe `AUTH_FAILED` y se cierra la conexión. |
| **Integridad de trama cifrada** | `CipherIntegrityError` | Tag GCM inválido, *replay* o secuencia incorrecta: responde `INTEGRITY_ERROR` y cierra el socket. |
| **Aislamiento transaccional** | `UnitOfWork` por petición | Cada llamada en `Router` instancia su propia `Session` de SQLAlchemy; nunca se comparten sesiones ni objetos ORM entre hilos. |

## 5. Comparativa: Modelo Híbrido vs. Async SQLAlchemy 2.0

En `src/domain/async_db.py` se incluye un corte vertical (*vertical slice*) con `create_async_engine`, `AsyncSession` (`expire_on_commit=False`) y `AsyncUnitOfWork` como referencia arquitectónica:

* **Modelo híbrido (`asyncio` + `ThreadPoolExecutor`):** Mantiene intactos los repositorios, `UnitOfWork`, servicios y `Router` de la Práctica 1. El paralelismo efectivo está acotado por $\min(N_{\text{clientes}}, W_{\text{workers}}, \text{conexiones\_BD})$.
* **Async SQLAlchemy 2.0 (`AsyncSession` + `asyncpg`/`aiosqlite`):** Elimina los hilos trabajadores y escala miles de conexiones en un solo hilo, pero requiere convertir toda la pila de llamadas a `async def` (*function coloring*) y sustituir la carga perezosa por `selectinload()` para evitar `MissingGreenlet`.