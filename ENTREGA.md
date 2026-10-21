# Entrega v2.0.0 — pasos

## 1. Copiar los ficheros
Copia el contenido de esta carpeta sobre la raíz de tu repositorio
(respetando rutas). **Después elimina** los ficheros obsoletos:

```bash
git rm main.py src/server/protocol.py \
       src/ui/__init__.py src/ui/categories_menu.py src/ui/fighters_menu.py \
       src/ui/main_menu.py src/ui/matches_menu.py src/ui/registrations_menu.py \
       src/ui/tournaments_menu.py src/ui/console.py src/ui/helpers.py
```

(`src/ui/console.py` y `src/ui/helpers.py` ahora viven en `src/client/ui/`.)

## 2. Comprobar
```bash
pip install -r requirements.txt
pytest                       # 280 tests
ruff check src tests client.py server.py verify.py
python verify.py
```

## 3. Entregar
```bash
git add -A
git commit -m "Refactor to TCP client/server architecture (v2.0.0)"
git tag -a v2.0.0 -m "v2.0.0 - TCP client/server backoffice"
git push origin main --tags
git rev-parse HEAD           # <- SHA a entregar
```
