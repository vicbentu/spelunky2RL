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
