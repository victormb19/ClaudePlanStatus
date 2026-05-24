# ClaudePlanStatus

Indicador para GNOME que muestra en la barra superior cuánto has consumido de tu
plan de Claude Code: ventana rodante de 5 horas y total semanal. Los datos salen
de [`ccusage`](https://github.com/ryoppippi/ccusage) leyendo los JSONL locales
en `~/.claude/projects/` — no llama a ninguna API.

```
🟢 5h 12% · 7d 35%      ← en la barra superior de GNOME
```

Al hacer clic se despliega el menú con detalles:

- Tokens consumidos en el bloque activo de 5h y tiempo restante.
- Tokens consumidos en la semana actual.
- Coste estimado (bloque y semana).
- Acciones: Refrescar ahora, Editar config, Salir.

## Requisitos

- Ubuntu 24.04+ con GNOME Shell y la extensión AppIndicator (incluida en Ubuntu).
- Python 3.11+ (Ubuntu 24.04 trae 3.12).
- `sudo` para una sola instalación de paquete del sistema.

## Instalación

```bash
cd ~/Documentos/ClaudePlanStatus
./install.sh
```

El script:

1. Instala `gir1.2-ayatanaappindicator3-0.1` vía apt (te pedirá la contraseña).
2. Instala [Bun](https://bun.sh) en `~/.bun` si no lo tienes.
3. Instala `ccusage` globalmente con Bun.
4. Crea un symlink del binario nativo en `~/.local/bin/ccusage`.
5. Registra el `.desktop` en `~/.config/autostart/` para que arranque al iniciar sesión.

Para probarlo sin reiniciar la sesión:

```bash
python3 ~/Documentos/ClaudePlanStatus/claude_plan_indicator.py &
```

## Configuración

Edita `config.toml` (o usa "Editar config…" desde el menú):

```toml
[limits]
threshold_5h = "auto"        # "auto" = usa tu mayor bloque histórico
threshold_weekly = 5000000   # tokens; ajusta según tu plan real

[ui]
poll_seconds = 30
show_cost = true
```

Los cambios se aplican en el siguiente poll (o pulsa "Refrescar ahora").

## Sobre los "%"

Anthropic no publica los caps de Pro/Max como número de tokens — el plan se mide
internamente por mensajes opacos. Este indicador muestra **tokens consumidos**
contra umbrales que configuras tú. El default `"auto"` para 5h toma como
referencia tu mayor bloque histórico (igual que `ccusage blocks -t max`), lo
que da un proxy razonable de tu uso máximo personal.

## Desinstalar

```bash
rm ~/.config/autostart/claude-plan-indicator.desktop
pkill -f claude_plan_indicator.py
rm -rf ~/Documentos/ClaudePlanStatus
# Opcional: rm ~/.local/bin/ccusage  &&  ~/.bun/bin/bun pm uninstall -g ccusage
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
