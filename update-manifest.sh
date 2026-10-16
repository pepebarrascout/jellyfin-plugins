#!/usr/bin/env bash
#
# update-manifest.sh
# ==================
#
# Regenera manualmente el manifest.json combinado y el index.html de la
# landing page, leyendo los manifest.json de cada plugin publicado en
# https://github.com/pepebarrascout/jellyfin-plugin-*.
#
# Uso:
#   ./update-manifest.sh
#
# Si tienes un token de GitHub (para subir el rate-limit de la API),
# expórtalo antes:
#   export GITHUB_TOKEN=ghp_xxx
#   ./update-manifest.sh
#
# Después de ejecutarlo, haz commit y push de los cambios:
#   git add manifest.json index.html
#   git commit -m "Actualiza manifest combinado"
#   git push
#
# O usa el modo --commit para que el script haga commit automáticamente:
#   ./update-manifest.sh --commit
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

MANIFEST_FILE="$REPO_DIR/manifest.json"
HTML_FILE="$REPO_DIR/index.html"

# Colores para output (si la terminal los soporta)
if [ -t 1 ]; then
  C_BLUE='\033[0;34m'
  C_GREEN='\033[0;32m'
  C_YELLOW='\033[0;33m'
  C_RED='\033[0;31m'
  C_RESET='\033[0m'
else
  C_BLUE=''; C_GREEN=''; C_YELLOW=''; C_RED=''; C_RESET=''
fi

log()     { printf "${C_BLUE}[build]${C_RESET} %s\n" "$*"; }
ok()      { printf "${C_GREEN}[ok]${C_RESET}   %s\n" "$*"; }
warn()    { printf "${C_YELLOW}[warn]${C_RESET} %s\n" "$*"; }
fatal()   { printf "${C_RED}[err]${C_RESET}  %s\n" "$*" >&2; exit 1; }

# Verificar python3
command -v python3 >/dev/null 2>&1 || fatal "python3 no está instalado"
PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
log "python3 versión $PY_VER"

# Verificar que existe el script build_manifest.py
BUILD_PY="$SCRIPT_DIR/build_manifest.py"
[ -f "$BUILD_PY" ] || fatal "No se encuentra $BUILD_PY"

# Backup de los archivos actuales para detectar cambios
MANIFEST_BEFORE=""
HTML_BEFORE=""
[ -f "$MANIFEST_FILE" ] && MANIFEST_BEFORE=$(sha256sum "$MANIFEST_FILE" | cut -d' ' -f1)
[ -f "$HTML_FILE" ] && HTML_BEFORE=$(sha256sum "$HTML_FILE" | cut -d' ' -f1)

# Token opcional
TOKEN_ARG=()
if [ -n "${GITHUB_TOKEN:-}" ]; then
  TOKEN_ARG=(--token "$GITHUB_TOKEN")
  log "Usando GITHUB_TOKEN del entorno"
else
  log "Sin token (rate-limit aplicará si hay muchos fetches)"
fi

# Ejecutar build
log "Construyendo manifest y HTML..."
python3 "$BUILD_PY" \
  --output "$MANIFEST_FILE" \
  --html "$HTML_FILE" \
  "${TOKEN_ARG[@]}" || fatal "build_manifest.py falló"

# Comparar
MANIFEST_AFTER=$(sha256sum "$MANIFEST_FILE" | cut -d' ' -f1)
HTML_AFTER=$(sha256sum "$HTML_FILE" | cut -d' ' -f1)

if [ "$MANIFEST_BEFORE" = "$MANIFEST_AFTER" ] && [ "$HTML_BEFORE" = "$HTML_AFTER" ]; then
  ok "Sin cambios. manifest.json e index.html ya estaban al día."
  exit 0
fi

ok "manifest.json e index.html actualizados."
log "Cambios:"
[ "$MANIFEST_BEFORE" != "$MANIFEST_AFTER" ] && log "  - manifest.json modificado"
[ "$HTML_BEFORE" != "$HTML_AFTER" ] && log "  - index.html modificado"

# Modo commit automático
if [ "${1:-}" = "--commit" ] || [ "${2:-}" = "--commit" ]; then
  log "Haciendo commit automático..."
  cd "$REPO_DIR"
  git config user.name "update-manifest.sh"
  git config user.email "bot@users.noreply.github.com"
  git add "$MANIFEST_FILE" "$HTML_FILE"
  if git diff --cached --quiet; then
    ok "Nada que commitear (los archivos no cambiaron respecto al HEAD)."
  else
    TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M UTC')
    git commit -m "chore: actualización manual del manifest combinado ($TIMESTAMP)" >/dev/null
    if git remote get-url origin >/dev/null 2>&1; then
      log "Haciendo push..."
      git push origin "$(git rev-parse --abbrev-ref HEAD)"
      ok "Push completado."
    else
      warn "Commit creado, pero no hay remote 'origin'. Haz push manualmente."
    fi
  fi
else
  log "Para hacer commit y push automáticos, ejecuta con --commit:"
  log "  $0 --commit"
  log "O hazlo manualmente:"
  log "  cd \"$REPO_DIR\" && git add manifest.json index.html && git commit -m 'Actualiza manifest' && git push"
fi
