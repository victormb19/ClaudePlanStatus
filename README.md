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
poll_seconds = 60         # cada cuántos segundos refrescar (mín 15)
warn_pct = 70             # icono 🟡 a partir de este %
alert_pct = 90            # icono 🔴 a partir de este %
show_extras = true        # mostrar caps extra en el menú si existen
stale_marker = "*"        # sufijo cuando el dato mostrado es cacheado ("" = sin marca)
stale_max_age_hours = 0   # 0 = mostrar el dato cacheado siempre, sin caducidad
auto_refresh_token = true # renovar el token OAuth solo (reescribe .credentials.json)
refresh_margin_seconds = 300  # renovar este margen antes de que caduque
```

Cambios se aplican en el siguiente poll, o pulsa "Refrescar ahora".

## Manejo de tokens

El indicador re-lee `~/.claude/.credentials.json` en cada poll, así que cuando
Claude Code refresca el token automáticamente, el indicador lo recoge sin
reiniciar.

### Renovación automática (`auto_refresh_token = true`)

Si el `accessToken` está a punto de caducar (o la API responde `401`), el
indicador canjea el `refreshToken` contra
`POST https://console.anthropic.com/v1/oauth/token` y reintenta, sin que tengas
que abrir el CLI. Como Anthropic puede **rotar** el refresh token, la respuesta
se persiste en `~/.claude/.credentials.json`:

- escritura atómica (`.tmp` + `rename`) y permisos `0600`;
- copia previa en `~/.claude/.credentials.json.bak`;
- se conservan intactas las claves que no son del bloque `claudeAiOauth`.

Aun así es tu archivo de sesión del CLI: si prefieres que nada externo lo toque,
pon `auto_refresh_token = false` y quedará sólo el comportamiento de cache de
abajo. En el menú tienes "Renovar token ahora" para forzarlo a mano.

Si el refresh falla (refresh token revocado o ya gastado), verás
`refresh rechazado — abre \`claude\` 1 vez`.

### Si aun así no hay datos frescos

El indicador **sigue
mostrando el último % conocido** (cacheado en
`~/.cache/claude-plan-status/last_usage.json`) con el sufijo `*`:

```
🟢 5h 3% · 7d 62%*
```

y en el menú, en lugar de "Actualizado: HH:MM:SS", aparece
`Datos de HH:MM:SS (hace 20m) — token expirado, abre `claude` 1 vez`. Basta con
abrir `claude` una vez para que se renueve y el `*` desaparezca. Sólo verás
`⚠ Claude` sin números si nunca hubo un dato correcto o si superas
`stale_max_age_hours`.

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
