# Backlog

Cosas encontradas fuera del alcance de la tarea en curso. Una línea cada una, con contexto suficiente.

- 2026-09-28 — La interfaz de Overlunky (barra de menú + línea de contadores "FRAME/START/TOTAL…",
  ~40 px arriba) sale en los frames de `render()`. Probado sin éxito: `draw_hud/draw_hotbar/
  draw_script_messages = 0` y `tabs_open = []` en `overlunky.ini`; un `imgui.ini` propio; F11 (`hide_ui`)
  con `xdotool windowfocus key F11`; `imgui_playlunky.ini` con la ventana en `Pos=-5000,-5000` y
  `Collapsed=1` hace que el juego caiga con un page fault. `hide_ui` solo se cambia con la tecla
  (`src/injected/ui.cpp` de overlunky). Vías sin probar: recortar las filas superiores en
  `X11FrameSource`, pedir upstream una opción de ini, o capturar dentro del juego (Fase 6).
- 2026-09-28 — Con `renderer="cpu"` (lavapipe) cada contenedor usa ~2,8 GiB de RAM frente a ~1 GiB con GPU.
- 2026-09-28 — Resolución de `render()` configurable (hoy fija en 640x360). La deciden dos cosas que
  deben coincidir: el tamaño de pantalla de Xvfb (`docker/entrypoint.sh` y `WineLauncher`, `640x360x24`)
  y `local.cfg` (`engine/launchers/config/local.cfg`: ventana `window_mode=2` al `window_scale=100` %
  de la pantalla; `resolutionx/y`). Propuesta: parámetro `render_resolution=(w, h)` → variable
  `RESOLUTION` al contenedor → el entrypoint arranca Xvfb a ese tamaño y escribe `local.cfg` a juego.
  Sin probar: que `window_scale=100` llene pantallas mayores (sí lo hace a 640x360) y el coste de
  render (GPU poco; con `renderer="cpu"` crece con los píxeles). Solo afecta con `render_enabled`.
