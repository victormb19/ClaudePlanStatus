#!/usr/bin/env bash
# Instala dependencias y registra ClaudePlanStatus en autostart de GNOME.
#
# Pasos:
#   1. apt: gir1.2-ayatanaappindicator3-0.1 (typelib que necesita PyGObject)
#   2. Bun (si falta) en ~/.bun
#   3. ccusage global con bun
#   4. Symlink ccusage nativo → ~/.local/bin/ccusage
#   5. .desktop en ~/.config/autostart/
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> 1/5 Instalando typelib AyatanaAppIndicator3 (requiere sudo)…"
if ! python3 -c "import gi; gi.require_version('AyatanaAppIndicator3', '0.1')" 2>/dev/null; then
  sudo apt update
  sudo apt install -y gir1.2-ayatanaappindicator3-0.1 python3-gi
else
  echo "    Ya instalado."
fi

echo "==> 2/5 Instalando Bun…"
if [ ! -x "$HOME/.bun/bin/bun" ]; then
  curl -fsSL https://bun.sh/install | bash
else
  echo "    Ya instalado en ~/.bun/bin/bun."
fi

echo "==> 3/5 Instalando ccusage global…"
"$HOME/.bun/bin/bun" install -g ccusage

echo "==> 4/5 Symlink ccusage → ~/.local/bin/ccusage…"
mkdir -p "$HOME/.local/bin"
NATIVE_CCUSAGE="$HOME/.bun/install/global/node_modules/@ccusage/ccusage-linux-x64/bin/ccusage"
if [ ! -x "$NATIVE_CCUSAGE" ]; then
  echo "    ERROR: no encuentro el binario nativo en $NATIVE_CCUSAGE" >&2
  exit 1
fi
ln -sf "$NATIVE_CCUSAGE" "$HOME/.local/bin/ccusage"
echo "    OK: $("$HOME/.local/bin/ccusage" --version)"

echo "==> 5/5 Registrando autostart…"
mkdir -p "$HOME/.config/autostart"
sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$PROJECT_DIR/claude-plan-indicator.desktop" \
  > "$HOME/.config/autostart/claude-plan-indicator.desktop"
echo "    Escrito en ~/.config/autostart/claude-plan-indicator.desktop"

echo
echo "Listo. Lánzalo ahora con:"
echo "  python3 $PROJECT_DIR/claude_plan_indicator.py &"
echo "y se iniciará solo en próximos logins."
