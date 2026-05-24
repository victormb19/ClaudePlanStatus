#!/usr/bin/env bash
# Instala dependencias del sistema y registra ClaudePlanStatus en autostart.
#
# Pasos:
#   1. apt: gir1.2-ayatanaappindicator3-0.1 + python3-gi (typelib que necesita
#      PyGObject para crear el icono en la barra superior de GNOME).
#   2. .desktop en ~/.config/autostart/ para que arranque al iniciar sesión.
#
# No requiere Node, Bun, ni ccusage: el indicador llama directamente al
# endpoint OAuth de Anthropic con el token que ya guarda Claude Code en
# ~/.claude/.credentials.json.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> 1/2 Comprobando typelib AyatanaAppIndicator3…"
if python3 -c "import gi; gi.require_version('AyatanaAppIndicator3', '0.1')" 2>/dev/null; then
  echo "    Ya instalado."
else
  echo "    Instalando (requiere sudo)…"
  sudo apt update
  sudo apt install -y gir1.2-ayatanaappindicator3-0.1 python3-gi
fi

echo "==> 2/2 Registrando autostart…"
mkdir -p "$HOME/.config/autostart"
sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$PROJECT_DIR/claude-plan-indicator.desktop" \
  > "$HOME/.config/autostart/claude-plan-indicator.desktop"
echo "    Escrito en ~/.config/autostart/claude-plan-indicator.desktop"

if [ ! -f "$HOME/.claude/.credentials.json" ]; then
  echo
  echo "Aviso: no encuentro ~/.claude/.credentials.json"
  echo "Logueate en Claude Code antes de lanzar el indicador:"
  echo "  claude  (y completa el login OAuth)"
fi

echo
echo "Listo. Lánzalo ahora con:"
echo "  python3 $PROJECT_DIR/claude_plan_indicator.py &"
echo "y se iniciará solo en próximos logins."
