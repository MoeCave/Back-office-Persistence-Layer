# Arquitectura de Seguridad: Autenticación Mutua X.509 y Cifrado AES-256-GCM

## 1. Visión general y objetivos criptográficos

La capa de transporte TCP de **Tournament Back-Office** (`src/common/crypto.py`, `src/common/handshake.py`, `src/common/protocol.py`) protege todas las comunicaciones cliente-servidor mediante un diseño híbrido de clave pública y clave simétrica inspirado en TLS 1.3:

1. **Autenticación mutua bidireccional (mTLS / PKI X.509 v3):** Tanto el servidor como cada cliente poseen un par de claves **RSA-3072** y un certificado X.509 firmado por la Autoridad Certificadora Raíz interna (`Tournament Manager Root CA`). Ningún par confía en el otro sin verificar cadena de firma, ventana temporal (`not_valid_before` / `not_valid_after`), extensión `ExtendedKeyUsage` (`serverAuth` vs. `clientAuth`) y, en el cliente, coincidencia estricta del *hostname*/IP en `SubjectAlternativeName` (SAN).
2. **Prueba de posesión criptográfica (*Proof of Possession*) y frescura (*Nonces*):** Ambos extremos demuestran en tiempo real que poseen la clave privada correspondiente a su certificado firmando con **RSA-PSS (SHA-256, MGF1, salt máximo)** retos aleatorios de 128 bits (`nonce_c`, `nonce_s`) y el resumen SHA-256 del certificado del interlocutor.
3. **Intercambio seguro de clave efímera por sesión:** El servidor genera una clave de sesión aleatoria de 256 bits (`os.urandom(32)`) única para cada conexión TCP y la transporta cifrada con la clave pública del cliente mediante **RSA-OAEP (SHA-256, MGF1)**, vinculando ambos *nonces* dentro del sobre cifrado.
4. **Confidencialidad, integridad y orden estricto post-handshake:** Todas las peticiones y respuestas JSON se cifran con **AES-256-GCM** usando *nonces* deterministas de 96 bits derivados de la dirección del flujo (`CLIENT_TO_SERVER` / `SERVER_TO_CLIENT`) y un contador monótono de 64 bits (`seq`), autenticando además el *transcript hash* SHA-256 completo del *handshake* como *Additional Authenticated Data* (AAD).

---

## 2. Jerarquía PKI y gestión de certificados (`scripts/gen_certs.py`)

El script `scripts/gen_certs.py` aprovisiona una PKI autónoma bajo el directorio `certs/` (excluido del control de versiones mediante `.gitignore` para proteger las claves privadas `.key`):

| Entidad | Ruta Certificado | Ruta Clave Privada | `ExtendedKeyUsage` | Extensiones clave |
| :--- | :--- | :--- | :--- | :--- |
| **Root CA** | `certs/ca/ca.pem` | `certs/ca/ca.key` | — | `BasicConstraints(ca=True, path_length=0)`, `key_cert_sign=True` |
| **Servidor** | `certs/server/server.pem` | `certs/server/server.key` | `serverAuth` | `SAN: DNS:localhost, IP:127.0.0.1` |
| **Cliente 1** | `certs/client1/client1.pem` | `certs/client1/client1.key` | `clientAuth` | `CN=client1` |
| **Cliente 2** | `certs/client2/client2.pem` | `certs/client2/client2.key` | `clientAuth` | `CN=client2` |
| **CA Rogue (Test)** | `certs/test_invalid/rogue_client.pem` | `certs/test_invalid/rogue_client.key` | `clientAuth` | Emitido por una CA no confiable (prueba negativa) |
| **Caducado (Test)** | `certs/test_invalid/expired_client.pem` | `certs/test_invalid/expired_client.key` | `clientAuth` | Ventana temporal expirada (prueba negativa) |

---

## 3. Protocolo de *Handshake* Mutuo (M1 → M4)

Antes de admitir cualquier operación de dominio (`fighters`, `tournaments`, `categories`, `matches`, `registrations`), cliente y servidor ejecutan un intercambio estricto de 4 mensajes acotado a `MAX_HANDSHAKE_BYTES = 64 KiB` y `handshake_timeout = 10.0 s`:

```mermaid
sequenceDiagram
    autonumber
    participant C as Cliente (ServerGateway / AsyncServerGateway)
    participant S as Servidor (asyncio + ThreadPoolExecutor)

    Note over C: Genera nonce_c (16 B)
    C->>S: M1 client_hello {version, cert_pem, nonce_c}
    Note over S: Valida cert_pem contra ca.pem (EKU=clientAuth)<br/>Genera nonce_s (16 B)<br/>Firma RSA-PSS("SERVER_HELLO:" || nonce_c || nonce_s || sha256(cert_C))
    S->>C: M2 server_hello {version, cert_pem, nonce_s, signature}
    Note over C: Valida cert_pem contra ca.pem (EKU=serverAuth + SAN)<br/>Verifica firma RSA-PSS del servidor<br/>Firma RSA-PSS("CLIENT_PROOF:" || nonce_s || nonce_c || sha256(cert_S))
    C->>S: M3 client_proof {signature}
    Note over S: Verifica firma RSA-PSS del cliente<br/>Genera K_ses = os.urandom(32)<br/>Cifra RSA-OAEP(pub_C, K_ses || nonce_c || nonce_s)
    S->>C: M4 session_key {encrypted_key}
    Note over C,S: Ambos calculan TH = SHA-256(M1 || M2 || M3 || M4)<br/>e inicializan SessionCipher(K_ses, TH)