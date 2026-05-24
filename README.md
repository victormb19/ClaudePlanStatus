# ClaudePlanStatus

Indicador para GNOME que muestra en la barra superior los mismos porcentajes de
uso del plan de Claude Code que ves dentro de la sesión con `/usage` o en
[claude.ai/settings/usage](https://claude.ai/settings/usage): ventana de 5 horas
y cap semanal de 7 días.

```
🟢 5h 3% · 7d 62%      ← en la barra superior de GNOME
```

Al hacer clic se despliega el menú con detalle:

- Ventana 5h: `XX.X%` y cuándo resetea
- Semanal: `YY.Y%` y cuándo resetea
- Caps extra (Opus 7d, Sonnet 7d, extra_usage) si aplican a tu plan
- Acciones: Refrescar ahora, Editar config, Abrir uso en claude.ai, Salir

## ¿De dónde salen los datos?

Llama directamente al endpoint `GET https://api.anthropic.com/api/oauth/usage`
usando el access token OAuth que Claude Code ya tiene guardado en
`~/.claude/.credentials.json`. **No requiere API key, no consume cuota.**

## Requisitos

- Ubuntu 24.04+ con GNOME Shell y la extensión AppIndicator (incluida en Ubuntu).
- Python 3.11+ (Ubuntu 24.04 trae 3.12).
- Claude Code instalado y logueado (`claude` al menos una vez para crear
  `~/.claude/.credentials.json`).

## Instalación

```bash
git clone https://github.com/victormb19/ClaudePlanStatus.git ~/Documentos/ClaudePlanStatus
cd ~/Documentos/ClaudePlanStatus
./install.sh
```

El script:

1. Instala `gir1.2-ayatanaappindicator3-0.1` vía apt (te pedirá la contraseña).
2. Registra el `.desktop` en `~/.config/autostart/` para que arranque al iniciar sesión.

Para probarlo sin reiniciar la sesión:

```bash
python3 ~/Documentos/ClaudePlanStatus/claude_plan_indicator.py &
```

## Configuración (`config.toml`)

```toml
[ui]
poll_seconds = 60   # cada cuántos segundos refrescar (mín 15)
warn_pct = 70       # icono 🟡 a partir de este %
alert_pct = 90      # icono 🔴 a partir de este %
show_extras = true  # mostrar caps extra en el menú si existen
```

Cambios se aplican en el siguiente poll, o pulsa "Refrescar ahora".

## Manejo de tokens

El indicador re-lee `~/.claude/.credentials.json` en cada poll, así que cuando
Claude Code refresca el token automáticamente, el indicador lo recoge sin
reiniciar. Si el token expira y no estás usando el CLI, verás `⚠ Claude` con
"token expirado" — basta con abrir `claude` una vez para que se renueve.

## Desinstalar

```bash
rm ~/.config/autostart/claude-plan-indicator.desktop
pkill -f claude_plan_indicator.py
rm -rf ~/Documentos/ClaudePlanStatus
```

## Estructura

```
ClaudePlanStatus/
├── claude_plan_indicator.py     # script principal (PyGObject + AppIndicator)
├── config.toml                  # umbrales y opciones de UI
├── icon.svg                     # icono de la bandeja
├── claude-plan-indicator.desktop# plantilla de autostart
├── install.sh                   # instalador one-shot
└── README.md
```
