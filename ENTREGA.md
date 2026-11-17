# Entrega — pasos

## 1. Copiar los ficheros
Copia el contenido de esta carpeta sobre la raíz de tu repositorio
(respetando rutas). **Después elimina** los ficheros obsoletos (solo si
todavía existen en tu repo):

```bash
git rm -f main.py src/server/protocol.py \
       src/ui/__init__.py src/ui/categories_menu.py src/ui/fighters_menu.py \
       src/ui/main_menu.py src/ui/matches_menu.py src/ui/registrations_menu.py \
       src/ui/tournaments_menu.py src/ui/console.py src/ui/helpers.py
```

(`src/ui/console.py` y `src/ui/helpers.py` ahora viven en `src/client/ui/`.)

## 2. Comprobar
```bash
pip install -r requirements.txt
python scripts/gen_certs.py          # genera certs/ (no se versiona)
pytest                               # ~295 tests
ruff check src tests client.py server.py verify.py
black --check src tests client.py server.py verify.py
python verify.py
```

## 3. Probar a mano (autenticación)
```bash
APP_ENV=test python server.py                       # terminal 1
python client.py                                    # terminal 2 (client1)
python client.py --cert certs/client2/client2.pem \
                 --key certs/client2/client2.key    # terminal 3 (client2)
# Debe ser RECHAZADO (AUTH_FAILED):
python client.py --cert certs/test_invalid/rogue_client.pem \
                 --key certs/test_invalid/rogue_client.key
python client.py --cert certs/test_invalid/expired_client.pem \
                 --key certs/test_invalid/expired_client.key
```

## 4. Entregar
```bash
git add -A
git commit -m "TCP client/server backoffice: asyncio, mutual X.509 auth, AES-256-GCM"
git tag -a v2.0.0 -m "v2.0.0 - TCP client/server backoffice"   # usa la tag que pida cada práctica
git push origin main --tags
git rev-parse HEAD                   # <- SHA a entregar
git tag -l --points-at HEAD          # comprueba que la tag apunta a ese SHA
```