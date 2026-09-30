# Backlog

Cosas encontradas fuera del alcance de la tarea en curso: `- [ts @sha] contexto suficiente para retomarlo
en frío`. El sha es el commit en que estaba el código al verlo (`git show <sha>:<ruta>`). Secciones según
cuánto se sabe: Bugs (algo está mal), Improvements (se sabe exactamente qué hacer, solo falta el cuándo),
Ideas (vale la pena mirarlo; aún no se sabe si ni cómo). Se borran al hacerlas o descartarlas (git es el
archivo). Si se decide hacer una, pasa a `PLAN.md`.

## Bugs

- [2026-09-28 13:53 @ce9dcf6] La interfaz de Overlunky (barra de menú + línea de contadores
  "FRAME/START/TOTAL…", ~40 px arriba) sale en los frames de `render()`. Probado sin éxito:
  `draw_hud/draw_hotbar/draw_script_messages = 0` y `tabs_open = []` en `overlunky.ini`; un `imgui.ini`
  propio; F11 (`hide_ui`) con `xdotool windowfocus key F11`; `imgui_playlunky.ini` con la ventana en
  `Pos=-5000,-5000` y `Collapsed=1` hace que el juego caiga con un page fault. `hide_ui` solo se cambia
  con la tecla (`src/injected/ui.cpp` de overlunky). Vías sin probar: recortar las filas superiores en
  `X11FrameSource`, pedir upstream una opción de ini, o capturar dentro del juego (Fase 6 del plan
  antiguo, ver `Later` en `PLAN.md`).
- [2026-09-30 00:17 @222ac52] `main.lua`: `last_distance` no se reinicia en `reset`, así que el primer
  `dist_to_goal` de un episodio puede ser el último del anterior si la celda inicial no está en el campo
  de distancias. No se toca durante [plans/lua-modules.md](plans/lua-modules.md) para que la traza de
  referencia siga valiendo.
- [2026-09-30 00:17 @222ac52] `main.lua`: `count_dead_enemies` solo mira la capa frontal (enemigos
  muertos en la capa trasera no cuentan). Mismo motivo para no tocarlo durante la reorganización del Lua.
- [2026-10-01 01:03 @22d4d83] Las opciones de `reset` desconocidas se ignoran sin avisar: `_game_reset`
  (`engine/core.py`) acaba en `**kwargs`, así que un `bomb=3` (por `bombs=3`) en `reset_options` o en
  `env.reset(...)` no da error y el episodio arranca con los valores por defecto. Arreglo: quitar
  `**kwargs` o lanzar `TypeError` con los nombres sobrantes. Independiente del rediseño del contrato
  (ver Ideas).

## Improvements

- [2026-09-28 12:53 @abf1a96] Comprobar la versión de `Spel2.exe` al arrancar y fallar con un mensaje
  claro si no es la que soportan las versiones fijadas de Playlunky/Overlunky (hoy una actualización del
  juego rompe los offsets y el síntoma es que el mod no carga: timeout sin explicación). `spelunky2rl
  doctor` ya calcula el hash de build (`15a31692700c3c94` en esta máquina): guardar la lista de hashes
  soportados junto a las versiones fijadas de la imagen, comprobarla antes de lanzar y en `doctor`, y
  decir en el error qué build tiene el usuario y cuál espera la imagen. Venía de la tabla de riesgos
  del plan de retoma.
- [2026-09-28 15:38 @9f537a6] Resolución de `render()` configurable (hoy fija en 640x360). La deciden dos
  cosas que deben coincidir: el tamaño de pantalla de Xvfb (`docker/entrypoint.sh` y `WineLauncher`,
  `640x360x24`) y `local.cfg` (`engine/launchers/config/local.cfg`: ventana `window_mode=2` al
  `window_scale=100` % de la pantalla; `resolutionx/y`). Propuesta: parámetro `render_resolution=(w, h)`
  → variable `RESOLUTION` al contenedor → el entrypoint arranca Xvfb a ese tamaño y escribe `local.cfg`
  a juego. Sin probar: que `window_scale=100` llene pantallas mayores (sí lo hace a 640x360) y el coste
  de render (GPU poco; con `renderer="cpu"` crece con los píxeles). Solo afecta con `render_enabled`.
- [2026-09-30 22:59 @df58df3] Ruta del juego permanente y configurable desde el CLI. Hoy solo existe
  `game_dir=` o `SPELUNKY2RL_GAME_DIR` (resuelto en `make_launcher`, `engine/launchers/__init__.py`); no
  hay fichero de configuración y el `export` se pierde al cerrar la terminal (`docs/getting-started.md`
  dice "once", lo que es engañoso). Propuesta: `spelunky2rl config set game-dir <ruta>` (valida
  `Spel2.exe` como `doctor`) que escribe `~/.config/spelunky2rl/config.toml` (`XDG_CONFIG_HOME`),
  `config get/show`, y `make_launcher`/`doctor` lo leen como último recurso: `game_dir=` > variable de
  entorno > fichero. Podría cubrir también `launcher`, `image` y `renderer`. Actualizar la guía y
  `doctor` (que diga de dónde sale cada valor).

## Ideas

- [2026-09-28 13:53 @ce9dcf6] Con `renderer="cpu"` (lavapipe) cada contenedor usa ~2,8 GiB de RAM frente
  a ~1 GiB con GPU: con 16 instancias, ~45 GiB frente a ~16, lo que limita cuántas caben en una máquina
  sin GPU. Mirar de dónde sale (hilos de llvmpipe por contenedor, `LP_NUM_THREADS`; cachés de shaders de
  DXVK/Mesa) y si se puede bajar sin perder pasos/s. Sin investigar.
- [2026-10-01 00:53 @4cdc78a] Revisar el mecanismo de velocidad (`speedup` + `state_updates`), hecho a
  mano en su día. Hoy: `set_speedhack(100)` y, en cada `POST_UPDATE` del motor, `update_state()`
  `state_updates` veces (`main.lua`, final del callback; solo con `speedup=True`). La idea es amortizar
  el coste fijo de cada frame del motor (`Present` de DXVK, UI de Overlunky, bucle de Wine), que
  `render=False` no quita: solo evita dibujar nivel y HUD (+18 % a `state_updates=0`). Sin medir:
  pasos/s con `render=False` y `state_updates` = 0/10/50/200, ni si hay una vía mejor (p. ej. un
  bucle propio de `update_state()` mientras Python manda pasos, sin volver al motor, o quitar el
  speedhack si `state_updates` ya lo cubre). Si `state_updates` alto es siempre mejor, quizá no debería
  ser un parámetro del usuario.
- [2026-10-01 00:55 @7ce4428] Estandarizar el contrato de datos Python ↔ Lua (opciones y observación).
  Después de [plans/lua-modules.md](plans/lua-modules.md), que no permite cambiar comportamiento; es
  un cambio de protocolo (subir `PROTOCOL_VERSION`). Hoy: las opciones de `reset` son una lista fija
  en `_game_reset` (`engine/core.py`; los nombres desconocidos, ver Bugs); `data_to_send` es una lista
  de strings sin validar (`map_info`, `entity_info`, `dist_to_goal`, y `custom_info`, que siempre manda
  `""`); `step` lo lee con `getattr(self, "data_to_send", [])` y `reset` con `self.data_to_send`;
  `basic_info` va entero en cada paso aunque el entorno no lo use; formatos fijos (`map_info` 11x21,
  `entity_info` de 7 campos) sin parámetros ni descripción formal. Ideas: esquema único de opciones y
  campos (con valores por defecto y validación en Python), pedir solo los campos que usa la
  observación, tamaños configurables, documentar el formato. Medir antes: coste por campo en Lua
  (`map_info` +150 µs/paso, `entity_info` +110 µs, `dist_to_goal` ~0) y en `json.encode`.
  Relacionado: protocolo binario en `Later` de `PLAN.md`.
