#!/usr/bin/env bash
# Show current vs target WordPress project for WPRepro Agent, and point to
# the Render dashboard page where WPREPRO_SITE_URL can be changed.
#
# Usage: ./switch_project.sh https://globalklima.cl

set -euo pipefail

TARGET_URL="${1:-}"
if [ -z "$TARGET_URL" ]; then
    echo "Uso: ./switch_project.sh <target_url>"
    exit 1
fi
case "$TARGET_URL" in
    http://*|https://*) ;;
    *) TARGET_URL="https://${TARGET_URL}" ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

CURRENT_URL=""
RENDER_SERVICE_ID="${RENDER_SERVICE_ID:-}"
if [ -f "$ENV_FILE" ]; then
    CURRENT_URL=$(grep -E '^WPREPRO_SITE_URL\s*=' "$ENV_FILE" | tail -1 | cut -d'=' -f2- | tr -d ' \r' || true)
    if [ -z "$RENDER_SERVICE_ID" ]; then
        RENDER_SERVICE_ID=$(grep -E '^RENDER_SERVICE_ID\s*=' "$ENV_FILE" | tail -1 | cut -d'=' -f2- | tr -d ' \r' || true)
    fi
fi

echo "Proyecto actual (WPREPRO_SITE_URL): ${CURRENT_URL:-(no configurado)}"
echo "Proyecto destino:                   $TARGET_URL"
echo

if [ -n "$CURRENT_URL" ] && [ "$CURRENT_URL" = "$TARGET_URL" ]; then
    echo "✅ Ya coinciden — no es necesario cambiar nada."
    exit 0
fi

echo "⚠️  Necesitas actualizar WPREPRO_SITE_URL en Render a:"
echo "    $TARGET_URL"
echo
if [ -n "$RENDER_SERVICE_ID" ]; then
    echo "Dashboard de Render (Environment):"
    echo "    https://dashboard.render.com/web/${RENDER_SERVICE_ID}/env"
else
    echo "Dashboard de Render:"
    echo "    https://dashboard.render.com/"
    echo "(define RENDER_SERVICE_ID en api/.env para obtener el enlace directo a Environment)"
fi
echo
echo "Después de cambiar la variable, Render redeploya automáticamente."
echo "Verifica con: python check_project.py $TARGET_URL"
