# Plan de retoma de SpelunkyRL

Fecha: 2026-09-27. Estado del repo: último commit de octubre de 2025, código funcional
solo en Windows, con ventana visible y una lista de bugs conocidos.

Objetivos de esta retoma, por orden de prioridad:

> **Estado (2026-09-27):** la viabilidad de Linux, headless, sin Steam y Docker está **probada** en la
> rama `test/ubuntu-and-headless-feasability` (ver `feasibility/RESULTS.md`). Las secciones 3 a 6
> reflejan el diseño resultante de esas pruebas; las secciones 1 y 2 son el estudio previo.

1. **Eliminar la dependencia de Windows** en tiempo de ejecución (Linux + Wine/Proton).
2. **Modo headless**: sin monitor, N instancias en paralelo en un servidor.
3. **Sin Steam ni modlunky2 en ejecución**: el usuario solo indica dónde tiene el juego.
4. **Setup trivial para un externo**: un comando nativo o un `docker run`.
5. Corregir los bugs de contrato y robustez encontrados en la auditoría.

---

## 1. Diagnóstico

### 1.1 Arquitectura actual

```
Python (SpelunkyRLEngine, gymnasium)  <--TCP JSON-lines 127.0.0.1-->  lua/main.lua (overlunky API, dentro de Spel2.exe)
```

- Python abre un socket en puerto aleatorio, lo publica en la variable de entorno
  `Spelunky_RL_Port`, lanza `playlunky_launcher.exe -exe_dir=<juego>`, y espera la conexión.
- Lua lee el puerto con `os.getenv`, conecta con luasocket (DLLs Win32 en `lua/luasocket/`),
  y en `ON.POST_UPDATE` intercambia un mensaje por paso: recibe `{command, input, frames, data_to_send}`
  y devuelve el estado del juego (`basic_info`, `map_info`, `dist_to_goal`, `entity_info`).
- La observación es **estado del juego, no píxeles**. Los píxeles solo se usan para `render()`.

### 1.2 Acoplamiento a Windows (todo en la capa Python)

| Punto | Fichero | Problema |
|---|---|---|
| Import global | `spelunkyRL/engine/core.py:7` | `import win32gui` a nivel de módulo: `import spelunkyRL` falla en Linux |
| Lanzamiento | `core.py:121-142`, `:166-170` | `playlunky_launcher.exe` directo; relanzamiento con `shell=True` |
| Proceso | `core.py:159-163` | busca hijos `Spel2*` con `children()`; bajo Proton la cadena reparenta |
| Ventana | `core.py:173` | `get_hwnd_for_pid` se llama **siempre**, aunque `render_enabled=False` |
| Frames | `engine/utils/frame_grabber.py` | PrintWindow/GDI via pywin32 y `ctypes.windll` |
| Ventana | `engine/utils/window_management.py` | pywin32 entero; `press_ctrlf4` importado y nunca usado |
| Packaging | `pyproject.toml:13` | `pywin32` incondicional |
| Docs/ejemplos | `examples/*.py`, `docs/*` | rutas `C:\...` hardcodeadas |

Lo que **no** hay que tocar: el protocolo, el Lua, luasocket (corre dentro del proceso
Windows, que bajo Wine sigue siendo Windows) y la variable de entorno (Wine propaga el
entorno del host al proceso).

### 1.3 Bugs encontrados en la auditoría (independientes de plataforma)

Contrato Python/Lua y RL:

- `lua/main.lua:48-54,284`: `safe(false, -1)` devuelve `-1`, así que `face_left` llega
  como `-1` y cae fuera de `Discrete(2)` en `default_environment.py:210` y `enemy_killer.py:398`.
- `environments/enemy_killer.py:382`: recompensa invertida (`last - current`); matar da negativo.
- `enemy_killer.py:338` vs `:388`: espacio declara `(1,11,21)` int32, la observación es `(11,21)` int64.
- Los cinco entornos devuelven `done or truncated` como `terminated`
  (`default_environment.py:183`, `get_to_exit.py:96`, `gold_grabber.py:256`,
  `enemy_killer.py:383`, `dummy_environment.py:558`). SB3 bootstrapea mal en truncamientos.
- `lua/main.lua:203`: `warp(world, level, world)` pasa `world` como *theme*; solo coincide en
  mundos 1-2 (mundo 3 abre Volcana en vez de Olmec).
- `core.py:198-199`: seed con `random.randint` en vez de `self.np_random`; no reproducible.
- `get_to_exit.py:88`: asume `frames_per_step=6` (`time / 6`, `900 -`).
- `get_to_exit.py:111`, `enemy_killer.py:389`: `char_state` sin clip a `[0,22]`.
- `gold_grabber.py`: docstring dice 30 s y `/1000`, código usa `60*90` y `/500`; `target_gold` sin uso;
  `done` nunca es `True`. `docs/environments.md:88` repite el `/1000`.
- `template_environment.py:442`: `self.custom_param` no existe.
- `examples/record_video.py:113,176`: `obs = env.reset()` guarda la tupla (patrón gym viejo);
  también en `manual_control.py` y `benchmark_performance.py`.
- `core.py:79`: `action.tolist()` falla con listas Python.
- Lua: globals accidentales `pf_tile_lookup`, `mask`, `info`, `serialized_data`.

Robustez:

- `core.py:224`: `recv(1024)` bloqueante sin timeout. Si el juego se cuelga, `step()` no retorna.
- `core.py:107-117`: `close()` no idempotente, envía por el socket sin `try`, y con
  `atexit.register` (`:172`) se llama dos veces. No cierra sockets, no termina el launcher,
  no para el `FrameGrabber`. Un `atexit` por instancia.
- `core.py:148-170`: bucle de arranque infinito, sin límite de intentos.
- `frame_grabber.py:28-40`: hilo `while True` sin bandera de parada, 100 % de una CPU.
- `lua/main.lua:468-475`: `update_state()` dentro de `ON.POST_UPDATE` vuelve a disparar
  `ON.POST_UPDATE`: **recursión de profundidad `state_updates`**. Es la causa real de
  "too high causes crashes" en `docs/architecture.md`.
- `lua/main.lua:440-442`: `set_speedhack(100)` nunca se revierte; `steal_input` nunca se libera.
- `lua/main.lua:425-426`: `err` ignorado, `json.decode(nil)` si Python muere.
- `core.py:39`: default mutable `log_info=["all"]`.

Packaging y DX:

- `pyproject.toml:40`: `include = ["spelunkyRL"]` no incluye `engine`, `environments`, `tools`.
  Debe ser `"spelunkyRL*"`. Falta `package-data` para `tools/entities-hierarchy.md`
  (lo lee `id2name.py`), así que una instalación no editable falla.
- Sin `requires-python` (el código usa `dict | dict`, necesita 3.9+), sin `readme`, `license`.
- Sin tests, sin CI, sin `gymnasium.register`.
- `core.py:127-129` escribe `spelunkyRL` en `load_order.txt` pero el repo se llama
  `spelunky2RL`; la documentación no avisa de renombrar la carpeta.
- `examples/` vive dentro del paquete instalable.
- `train_get_to_exit.py:317`: `device="cuda"` fijo.

---

## 2. Investigación: viabilidad en Linux y headless

Resumen de lo confirmado en fuentes (septiembre 2026). Los puntos marcados **[inferencia]**
no están confirmados y hay que validarlos en la Fase 2.

### 2.1 Linux

- **modlunky2 2.1.1 (agosto 2026)** tiene build nativo Linux y lanza Playlunky/overlunky dentro
  del prefijo Proton de Steam. Confirma que **la inyección de DLL de Playlunky funciona bajo Proton**.
  Playlunky usa `DetourCreateProcessWithDlls`; overlunky cambió a ese método en el PR #283
  precisamente "para arreglar problemas de Linux y Proton".
  - <https://github.com/spelunky-fyi/modlunky2> (README, sección Linux)
  - <https://github.com/spelunky-fyi/modlunky2/issues/1367>
  - <https://github.com/spelunky-fyi/overlunky/pull/283>
- Receta de lanzamiento de modlunky2 (a replicar en Python si se usa Steam):
  `<Proton>/proton run playlunky_launcher.exe --exe_dir=<dir>` con
  `STEAM_COMPAT_DATA_PATH`, `STEAM_COMPAT_CLIENT_INSTALL_PATH`, `SteamAppId=418530`,
  `SteamGameId`, `STEAM_COMPAT_APP_ID`. cwd = directorio del exe.
- Flags reales de `playlunky_launcher`: solo `--exe_dir`, `--console`, `--overlunky`.
  Nada de ventana ni resolución. `playlunky.ini` tampoco.
- Roturas conocidas: colores oscuros sin DXVK (usar siempre DXVK, no wined3d:
  overlunky #206, #281); `MSVCP140_CODECVT_IDS.dll` no encontrada al cargar desde
  subcarpeta (overlunky #256, solución: mover las DLL junto al exe).
- Wine pasa el entorno del host al proceso Windows: `Spelunky_RL_Port` llega a `os.getenv`.
  Playlunky además copia `GetEnvironmentStrings()` al hijo.
- TCP a 127.0.0.1: Wine y pressure-vessel comparten pila de red con el host **[inferencia, alta confianza]**.
- luasocket (`socket_core.dll` sobre ws2_32) funciona bajo Wine **[inferencia]**. Precedente
  directo: warcraftsim hace TCP a Python desde una DLL inyectada bajo Wine.
- psutil ve el proceso como `Spel2.exe` (Linux devuelve `/proc/*/comm`; modlunky2 lo busca así).
  Escanear todos los procesos por nombre, no `children()`.
- pywin32 no sirve: el HWND vive dentro de Wine. Alternativa: capturar la ventana X11.

### 2.2 Sin Steam

- Spelunky 2 no tiene DRM propio ("doesn't use Steam CEG and doesn't use any third-party DRM",
  según el desarrollador). Solo inicializa la Steam API para logros y rankings.
  <https://steamcommunity.com/app/418530/discussions/0/3006682619663044001/>
- overlunky y Playlunky recomiendan una **copia aparte del juego con Goldberg Emulator**
  (`steam_api64.dll` de Goldberg + `steam_appid.txt` con `418530`). Es la práctica estándar
  de la comunidad de modding. <https://github.com/spelunky-fyi/overlunky#readme>
- Consecuencia: Steam solo hace falta **una vez para descargar el juego**. Ni Steam ni modlunky2
  son necesarios en ejecución. Playlunky nightly se descarga como zip de GitHub Releases.
- El juego escribe `savegame.sav`, `settings.cfg`, `input.cfg`, `local.cfg` en su cwd
  (junto a `Spel2.exe`). Para N instancias hacen falta N copias (o reflinks) del directorio.
- Multi-instancia: no se documenta ningún mutex de instancia única **[inferencia, validar]**.
- Restricciones: no redistribuir el juego (ni en la imagen Docker). Goldberg anula logros y
  rankings. Fijar una versión concreta de Goldberg (fork mantenido: gbe_fork).

### 2.3 Headless

API Lua de overlunky relevante (<https://spelunky-fyi.github.io/overlunky/>):

- **Saltar el render**: `set_pre_render_screen` o `ON.RENDER_PRE_GAME` devolviendo `true`.
- `set_frametime_unfocused(0)`: **crítico**. Sin foco el juego baja a 33 FPS, y en Xvfb nunca
  tiene foco. `set_frametime(0)` para quitar el límite (sigue capado por VSync/GPU).
- `set_setting(GAME_SETTING.X, v)`: `VSYNC=0`, `RESOLUTIONX/Y`, `WINDOW_MODE`, `MASTER_ENABLED=0`
  (audio), `SOUND_ENABLED`, `MUSIC_ENABLED`. Lista completa en `docs/game_data/game_settings.txt`
  del repo de overlunky.
- `update_state()`: simula un frame lógico; "puede llamarse miles de veces". Pero desde
  `ON.POST_UPDATE` provoca reentrada (ver bug 1.3). Hay que protegerlo con una bandera.
- `pause` API (`pause.pause`, `pause.skip`) y `ON.PRE_UPDATE` devolviendo `true` congela el motor.
- No existe captura de framebuffer desde Lua.

Runtime gráfico:

- DXVK 2.x necesita Vulkan 1.3, DXVK 3.x Vulkan 1.4. No necesita X acelerado, solo un WSI X11:
  **Xvfb + GPU real + DXVK** funciona.
- Sin GPU: **Xvfb + lavapipe** (Mesa 24 o superior). DXVK corre sobre lavapipe con edge cases
  (doitsujin/dxvk #3876). Forzar con `VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.x86_64.json`.
  CPU-bound: varios cores por instancia.
- Xorg dummy (`xf86-video-dummy`, receta de xpra) como alternativa a Xvfb.
- gamescope `--backend headless` inmaduro. Descartado.
- Proton sin Steam: **umu-launcher** (`umu-run`, `PROTON_VERB=run` para varias instancias).
  En Docker necesita user namespaces o `--security-opt seccomp=unconfined`.
  Alternativa más simple en contenedor: Wine 10 + DXVK copiando DLLs (`WINEDLLOVERRIDES="d3d11,dxgi=n"`).
- Audio: `HKCU\Software\Wine\Drivers` `"Audio"=""`, o `WINEDLLOVERRIDES="winepulse.drv,winealsa.drv=d"`,
  más `MASTER_ENABLED=0` desde Lua.
- Captura de vídeo en Linux: `xdotool search --pid` para la geometría, `mss(display=":N")` o
  `ffmpeg -f x11grab`. Una `DISPLAY` por instancia.
- Windows headless (display virtual, GPU-P, PrintWindow con ventanas minimizadas): frágil y una VM
  por instancia. Solo como plan B si Wine falla.

Prior art: <https://github.com/RobinKa/warcraftsim> (Warcraft III bajo Wine + Xvfb, DLL inyectada,
TCP a Python, observaciones desde el script del juego, 16-24 instancias, ~4600 steps/s).
Imágenes base: <https://github.com/benjymous/docker-wine-headless>,
<https://github.com/Steam-Headless/docker-steam-headless>, <https://github.com/selkies-project/docker-selkies-egl-desktop>.

### 2.4 Máquina de desarrollo (esta)

Ubuntu 26.04, RTX 3060 (driver 595, ICD Vulkan NVIDIA y lavapipe presentes), Xvfb y Docker
instalados. **Sin** Steam, Wine, Proton ni el juego. Python del sistema 3.14: para entrenar,
usar un venv con 3.11 o 3.12 hasta confirmar soporte de torch y SB3.

---

## 3. Decisiones de diseño

1. **Steam solo para adquirir el juego.** Ejecución con Goldberg (gbe_fork) en lugar de
   `steam_api64.dll`. Sin Steam ni modlunky2 en ejecución.
2. **La librería solo depende de Gymnasium.** Cada instancia de `SpelunkyEnv` arranca su propio juego
   en `__init__` y lo libera en `close()`. Cómo paralelizar y entrenar lo decide el usuario
   (`gymnasium.vector`, SB3, RLlib, bucle propio). SB3 solo aparece en ejemplos, como extra opcional.
3. **El código Python corre fuera del contenedor**, en el entorno del usuario. Docker solo contiene
   el juego ejecutable: Wine, prefijo con DXVK, Playlunky, Goldberg, Overlunky, plantillas de ini y el mod Lua.
4. **Un contenedor efímero por instancia.** `SpelunkyEnv.__init__` lanza `docker run --rm`,
   `close()` lo mata. Nada corre en segundo plano cuando no se usa. Sin gestor de larga vida.
   `--network host` para que el Lua conecte a `127.0.0.1` del host con el protocolo actual.
   Cada contenedor tiene su propio prefijo de Wine (copia en escritura de la imagen) y su propio Xvfb
   con número de display único, porque con host network los sockets abstractos de X se comparten.
5. **La imagen no contiene el juego.** El usuario monta su carpeta en `/game:ro`. Todo lo demás viene
   en la imagen; no hay paso de "copiar mod, Playlunky, Goldberg" por parte del usuario.
6. **Directorio del juego por instancia = granja de enlaces simbólicos**, no overlay. Enlaces a
   `/game/*`, ficheros reales para lo nuestro (`steam_api64.dll` de Goldberg, ini, `steam_appid.txt`)
   y escritura del juego en el propio directorio. Mismo rendimiento que overlay y sin privilegios
   (overlay exige `SYS_ADMIN`, AppArmor desactivado y/o `/dev/fuse`).
7. **Caché de Playlunky (`Mods/Packs/.db`) compartida y escribible**, en un volumen por versión del
   juego. Playlunky la construye solo en el primer arranque. Para evitar la carrera cuando varias
   instancias arrancan a la vez con la caché vacía o desactualizada (hash de `Spel2.exe` distinto),
   la librería lo gestiona sola: la primera instancia toma un bloqueo exclusivo sobre un fichero del
   volumen, arranca hasta que el Lua conecta y lo suelta; las demás esperan ese bloqueo. Con la caché
   válida no se bloquea nada. Sin paso manual. Baja el arranque de ~12 s a ~8 s y ahorra 825 MB por
   instancia. No puede ser de solo lectura.
8. **El pack del mod solo contiene `lua/`.** Playlunky escribe dentro de la carpeta del mod y se
   cuelga si es de solo lectura y encuentra imágenes que convertir (`docs/*.png`).
9. **Scripts `unsafe` vía Overlunky.** Playlunky siempre arranca desactivados los scripts con
   `meta.unsafe`; se lanza con `--overlunky` y `overlunky.ini` con `autorun_scripts = ["main.lua"]`,
   `script_dir = "Mods/Packs/spelunky2rl/lua"` y `enable_unsafe_scripts = 1`.
10. **Renderer elegible**: `renderer="auto" | "gpu" | "cpu"`. `auto` pasa `--gpus all` si hay GPU
    NVIDIA disponible; sin ella DXVK cae solo a lavapipe. `gpu` falla si no hay GPU; `cpu` fuerza lavapipe
    (`VK_ICD_FILENAMES`). La imagen incluye `nvidia_icd.json`, que el runtime de NVIDIA no inyecta.
11. **Versión del protocolo**: al conectar, el Lua envía primero `{"hello": {"protocol": N, "mod": "x.y.z"}}`;
    Python lo compara con su constante y falla con un error que indica la imagen necesaria. La etiqueta
    de la imagen coincide con la versión del paquete (`spelunky2rl-game:<versión>`) y es la que el paquete
    usa por defecto. Lua y Python viven en el mismo repo.
12. **Modo desarrollo**: opción (p. ej. `SPELUNKY2RL_DEV_MOD=/ruta/repo/src/spelunky2rl/mod/lua`) que monta el Lua local sobre
    el de la imagen. Cambios de Lua y de Python sin rebuild; solo se reconstruye si cambian Dockerfile o entrypoint.
13. **Lanzadores en Python**, detrás de una interfaz común:
    - `DockerLauncher` (Linux, camino principal y el de servidor).
    - `WineLauncher` (Linux sin Docker, útil para desarrollo; mismo ensamblado de directorio).
    - `WindowsLauncher` (Windows nativo, sin Docker: Docker Desktop no tiene GPU ni host network reales).
    El proceso propio se identifica por el puerto (`Spelunky_RL_Port` en su entorno) o por el nombre
    del contenedor, nunca por nombre de proceso.
14. **Headless desde Lua**: `main.lua` recibe en `reset` opciones de salto de render,
    `set_frametime_unfocused(0)`, VSync off, audio off y resolución. Ocultar la interfaz de Overlunky
    (`menu_ui = 0`) para que no salga en frames ni vídeo.

## 3.1 Estructura del repo y nombre del paquete

El paquete pasa a llamarse **`spelunky2rl`** (distribución pip e import), en minúsculas y coherente
con el nombre del repo. El pack del mod dentro del juego también se llama `spelunky2rl`.
Hoy la raíz del repo es el pack del mod (se clonaba en `Mods/Packs/`); con el nuevo diseño deja de
serlo, porque Playlunky escribe dentro de la carpeta del mod y reorganizaría `docs/` y el resto.

```
spelunky2RL/
├── pyproject.toml                  # name = "spelunky2rl"
├── README.md
├── src/spelunky2rl/                # paquete pip (layout src)
│   ├── __init__.py                 # registra los ids en gymnasium
│   ├── engine/
│   │   ├── core.py                 # SpelunkyRLEngine (gym.Env)
│   │   ├── protocol.py             # framing, handshake, PROTOCOL_VERSION
│   │   ├── assemble.py             # granja de enlaces (para WineLauncher y WindowsLauncher)
│   │   ├── launchers/              # base.py, docker.py, wine.py, windows.py
│   │   └── frames/                 # base.py, x11.py, win32.py, null.py
│   ├── envs/                       # dummy, get_to_exit, gold_grabber, enemy_killer, template
│   ├── mod/                        # EL pack del mod, datos del paquete
│   │   └── lua/                    # main.lua, luasocket/, jumper/
│   ├── tools/                      # id2name.py + entities-hierarchy.md como datos
│   └── cli.py                      # comando `spelunky2rl`: doctor, pull
├── docker/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── versions.env                # versiones fijadas de Wine, DXVK, Playlunky, Overlunky, gbe_fork
│   └── config/                     # overlunky.ini, playlunky.ini, nvidia_icd.json
├── examples/                       # fuera del paquete: random_agent, train_sb3, record_video, manual_control
├── tests/
│   ├── unit/                       # con un Lua falso en Python, sin juego
│   └── integration/                # marcados, necesitan juego y Docker
├── docs/
└── .github/workflows/              # ci.yml (lint + unit), docker.yml (imagen en cada tag)
```

Decisiones:

- **El Lua vive dentro del paquete Python** (`src/spelunky2rl/mod/lua`) y es la única fuente: el
  Dockerfile lo copia desde ahí, `WineLauncher` y `WindowsLauncher` ensamblan el pack desde el paquete
  instalado, y el modo desarrollo monta esa misma carpeta. Python y Lua salen siempre en la misma versión.
- **Layout `src/`**: los tests corren contra el paquete instalado, lo que detecta errores de
  empaquetado como el actual `include = ["spelunkyRL"]`.
- **`examples/` fuera del paquete**; SB3 y torch solo como extras de los ejemplos.
- **`cli.py`**: comando de terminal `spelunky2rl` instalado con el paquete (`[project.scripts]`).
  `doctor` comprueba Docker, GPU, versión de imagen y ruta del juego; `pull` descarga la imagen de la
  versión correcta. La caché de Playlunky no necesita comando: se construye sola (decisión 7).
- **`feasibility/` no se fusiona en `main`**: se queda en la rama `test/ubuntu-and-headless-feasability`
  como registro. Su contenido útil se reescribe limpio en `docker/` y `engine/launchers/`.
- `environments/` pasa a `envs/`; `engine/utils/` desaparece (su contenido va a `frames/`).

### Migración (primer paso, antes de tocar lógica) — HECHA

Rama `refactor/spelunky2rl`, commit "Move to src layout and rename package to spelunky2rl".
Verificado: `pip install .` en venv limpio incluye `mod/lua` y las DLL; el Lua movido carga
`luasocket` y `jumper` dentro del juego (contenedor de pruebas, ~1.440 pasos/s).

En una rama sobre `main`, commit solo de estructura para que el diff sea revisable:

1. `git mv spelunkyRL src/spelunky2rl`, `git mv src/spelunky2rl/environments src/spelunky2rl/envs`,
   `git mv lua src/spelunky2rl/mod/lua`, `git mv src/spelunky2rl/examples examples`.
2. Cambiar todos los imports y nombres de la lista siguiente.
3. `pyproject.toml`: `name = "spelunky2rl"`, `[tool.setuptools.packages.find] where = ["src"]`,
   `package-data` para `mod/**` y `tools/*.md`, `[project.scripts] spelunky2rl = "spelunky2rl.cli:main"`.
4. Verificar en un venv limpio: `pip install .`, `python -c "import spelunky2rl"` y que
   `mod/lua/main.lua` y las DLL de luasocket están dentro del paquete instalado.
5. Verificar en el juego (con el lanzador de Wine de la rama de pruebas) que `main.lua` sigue
   encontrando `luasocket` y `jumper`: hoy usa `package.path = "lua/?.lua;..."`, relativo.

### Sitios a cambiar por el renombrado

Imports de Python (`spelunkyRL` → `spelunky2rl`, `environments` → `envs`):

| Fichero (ruta actual) | Línea | Cambio |
|---|---|---|
| `spelunkyRL/environments/default_environment.py` | 29 | `from spelunky2rl import SpelunkyRLEngine` |
| `spelunkyRL/environments/dummy_environment.py` | 31 | idem |
| `spelunkyRL/environments/enemy_killer.py` | 29 | idem |
| `spelunkyRL/environments/get_to_exit.py` | 25 | idem |
| `spelunkyRL/environments/gold_grabber.py` | 29 | idem |
| `spelunkyRL/environments/template_environment.py` | 13 | idem |
| `spelunkyRL/examples/evaluate_model.py` | 31 | `from spelunky2rl.envs.get_to_exit import SpelunkyEnv` |
| `spelunkyRL/examples/record_video.py` | 32 | idem |
| `spelunkyRL/examples/train_get_to_exit.py` | 36 | idem |
| `spelunkyRL/examples/manual_control.py` | 23 | `from spelunky2rl.envs.dummy_environment import SpelunkyEnv` |
| `spelunkyRL/examples/benchmark_performance.py` | 41-44 | cadenas `'spelunky2rl.envs.<entorno>'` |
| `spelunkyRL/__init__.py` | 2 | `from .envs import *` (y exportar la función `id2name`, no el módulo) |

Los imports relativos de `engine/core.py` (`.utils.frame_grabber`, `.utils.window_management`,
`..tools.id2name`), `engine/__init__.py` y `tools/__init__.py` siguen valiendo tras mover el paquete;
los de `utils` cambian en la Fase 1 al pasar a `frames/`.

Nombres que no son imports:

| Fichero | Cambio |
|---|---|
| `pyproject.toml:6,40` | `name = "spelunky2rl"`, búsqueda en `src` |
| `spelunkyRL/engine/core.py:129` | `load_order.txt` con `spelunky2rl` (pack del mod) |
| `overlunky.ini` (plantilla en `docker/config/`) | `script_dir = "Mods/Packs/spelunky2rl/lua"` |
| `readme.md` (6 menciones), `docs/getting-started.md` (14), `docs/environments.md` (13), `docs/architecture.md` (12), `examples/README.md` (11) | imports, rutas `spelunkyRL/...` e instrucciones de instalación |

Se mantiene el nombre de la clase `SpelunkyRLEngine` (no es el nombre del paquete).
`lua/main.lua` no referencia el nombre del paquete.

---

## 4. Fases

### Fase 0. Saneamiento (1-2 días, sin cambiar plataforma)

Todo verificable en Windows con el setup actual, o con tests unitarios sin juego.

- [ ] `pyproject.toml` (tras la migración de la sección 3.1): `package-data` para `mod/**` y el `.md` de `id2name`,
      `pywin32; sys_platform == 'win32'`, `requires-python >= 3.9`, `readme`, `license`.
- [ ] Separar `terminated` y `truncated` en los cinco entornos.
- [ ] `enemy_killer.py`: invertir signo de la recompensa; arreglar shape y dtype de `map_info`.
- [ ] `main.lua:284`: `face_left and 1 or 0`. Idem en `get_info` para el jugador si aplica.
- [ ] `main.lua:203`: mapear `world` a `THEME` correctamente en `warp`.
- [ ] Seed con `self.np_random.integers(0, 2**32)`.
- [ ] `close()` idempotente: `try/except`, cerrar `server` y `server_socket`, terminar launcher
      y árbol de procesos, parar `FrameGrabber`, `atexit.unregister`.
- [ ] `settimeout` configurable en el socket de datos; límite de intentos y timeout en el arranque.
- [ ] `FrameGrabber` con bandera de parada y sin `copy()` por iteración.
- [ ] Clip de `char_state`, quitar `press_ctrlf4` y `self.custom_param`, `obs, _ = env.reset()`
      en los ejemplos, `time / self.frames_per_step` en `get_to_exit`, sincronizar docstrings de
      `gold_grabber`, `action = np.asarray(action).tolist()`.
- [ ] Lua: `local` en las globals accidentales; comprobar `err` en `client:receive`;
      revertir `set_speedhack` y liberar `steal_input` en `reset`/`close`.
- [ ] (Resuelto por la sección 3.1: el pack del mod se llama `spelunky2rl` y ya no depende del nombre del repo.)
- [ ] Tests unitarios con un Lua falso (servidor TCP en Python que responde JSON): protocolo,
      `gamestate_to_observation` contra `observation_space` (usar `observation_space.contains`),
      `reward_function` con estados sintéticos.
- [ ] CI (GitHub Actions) con lint y tests, sin juego.

### Fase 1. Capa de abstracción y lanzadores

- [ ] `spelunkyRL/engine/launcher/`: interfaz común y `WindowsLauncher`, `WineLauncher`, `DockerLauncher`.
      `core.py` deja de conocer `.exe`, pywin32 y psutil directamente.
- [ ] Imports perezosos: `import spelunky2rl` funciona en Linux sin pywin32 ni `ctypes.windll`
      (hoy fallan `core.py`, `window_management.py` y `frame_grabber.py`). Comprobado en CI.
- [ ] `spelunkyRL/engine/frames/`: `Win32FrameSource`, `X11FrameSource` (xdotool + mss), `NullFrameSource`.
      Solo se instancia si `render_enabled`.
- [ ] Handshake de versión (decisión 11) en `main.lua` y en `core.py`.
- [ ] Parámetro `renderer` (decisión 10).
- [ ] Ejemplos y docs sin rutas `C:\`; ruta del juego por parámetro o variable de entorno.

### Fase 2. Validación de viabilidad — HECHA

Resultados en `feasibility/RESULTS.md` (rama `test/ubuntu-and-headless-feasability`):
Wine 10 + DXVK 3.1.1 en Xvfb, sin Steam, luasocket OK, sin mutex de instancia única,
~1.500 pasos/s por instancia, 4 instancias en paralelo, lavapipe OK, contenedor efímero OK
con GPU y sin ella, granja de enlaces elegida frente a overlay. Entornos reales (`dummy`,
`get_to_exit`, `default_environment`) probados con un `_game_init` sustituido.

### Fase 3. Imagen Docker del juego

- [ ] Pasar `feasibility/docker/` a `docker/` limpio: versiones fijadas de Wine, DXVK, Playlunky,
      Overlunky y gbe_fork; descarga en el build (sin binarios en el repo); `nvidia_icd.json`.
- [ ] Entrypoint: ensamblar granja de enlaces, arrancar Xvfb, lanzar Playlunky con `--overlunky`,
      esperar con `wineserver -w`, audio desactivado en el registro de Wine.
- [ ] Mod empaquetado en la imagen como pack con solo `lua/`; montaje de desarrollo encima.
- [ ] Volumen de caché de Playlunky por hash de `Spel2.exe`, con el bloqueo automático de la decisión 7.
- [ ] Publicar la imagen con etiqueta igual a la versión del paquete.

### Fase 4. Headless fino y paralelismo

- [ ] `main.lua`: opciones headless en `reset` (decisión 14).
- [ ] Arreglar la reentrada de `update_state()` con bandera; documentar la semántica de
      `state_updates` ("N frames lógicos por frame renderizado").
- [ ] Retrasar o desactivar el fantasma si hace falta (a partir de 3 min de juego cae a ~250 pasos/s).
- [ ] Reducir la espera fija de 60 frames tras cada reset (pesa en episodios cortos).
- [ ] Medir escalado con 1, 4, 8 y 16 contenedores: pasos/s, CPU y RAM por instancia.
- [ ] `render()` y `record_video.py` funcionando con `X11FrameSource` dentro del contenedor.
- [ ] Documentar en `docs/getting-started.md` los caminos Docker (Linux) y nativo (Windows).
      Aviso legal: el usuario aporta su copia; la imagen no incluye el juego.

### Fase 5. Retomar el entrenamiento

- [ ] Reentrenar `get_to_exit` con el contrato corregido (terminated/truncated, seed reproducible).
- [ ] Comparar con los modelos de mayo de 2025.
- [ ] `gymnasium.register` para los entornos y `device="auto"`.

### Fase 6. Comunicación Python-Lua más eficiente (después de tener todo funcionando)

Estado actual: TCP a `127.0.0.1`, una línea JSON por mensaje, un viaje de ida y vuelta por paso.
En Linux no es cuello de botella (~1.500 pasos/s, menos de 1 ms por paso), pero en Windows lo fue
y con render lo será. De menos a más trabajo:

- [ ] **Medir primero** cuánto del tiempo por paso es socket + JSON frente a simulación, en Linux y en Windows.
- [ ] `TCP_NODELAY` en ambos lados (Nagle + ACK retardado puede meter ~40 ms en Windows) y lectura
      por líneas con buffer en Python (`makefile().readline()`) en vez del bucle `recv(1024)` que concatena.
- [ ] Formato binario en vez de JSON: `map_info` y `entity_info` empaquetados con `string.pack` en Lua
      y `numpy.frombuffer` en Python. Mantener JSON para mensajes de control.
- [ ] Render sin píxeles por el socket: el frame va a memoria compartida (`/dev/shm` montado entre
      contenedor y host) y Python lo lee como array de numpy sin copias; el socket solo lleva un número
      de secuencia para garantizar que frame y estado corresponden al mismo paso.
- [ ] Opción más precisa para render: capturar el frame dentro del juego enganchando la presentación
      (`IDXGISwapChain::Present`) desde una DLL inyectada y escribirlo directamente en la memoria compartida.
      Evita Xvfb como intermediario y la desincronización. Bastante más trabajo.

---

## 5. Riesgos e incógnitas

Resueltos por las pruebas: luasocket bajo Wine (funciona), mutex de instancia única (no existe),
Wine puro frente a Proton (Wine 10 de Ubuntu basta), DXVK sobre lavapipe (funciona, ~15 % más lento
con `state_updates` alto).

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Error Lua con prefijo de Wine compartido (1 de 4 instancias) | Menor: con un contenedor por instancia no se comparte prefijo | Solo relevante para `WineLauncher`; un prefijo por instancia |
| Carrera al construir la caché de Playlunky compartida | Fallo en el primer arranque en paralelo | Bloqueo automático por fichero en la librería (decisión 7) |
| Coste de arranque (~8 s por instancia) | Lento para muchas instancias o reinicios frecuentes | Arranques en paralelo; mantener instancias vivas entre episodios |
| Docker Desktop en Windows sin GPU ni host network | Externos en Windows | Camino nativo `WindowsLauncher` |
| Actualización del juego o de Overlunky rompe offsets | Playlunky/Overlunky no cargan | Versiones fijadas en la imagen; comprobar versión de `Spel2.exe` al arrancar |
| Captura de frames desincronizada con el estado | Observaciones con imágenes erróneas | Ver Fase 6; número de secuencia por frame |
| Consumo de RAM/CPU por instancia desconocido | Límite de paralelismo | Medir en Fase 4 |
| torch y SB3 sin soporte de Python 3.14 | Entrenamiento | venv con 3.11 o 3.12 |

---

## 6. Orden recomendado

1. Migración de estructura y nombre (sección 3.1), commit solo de estructura.
2. Fase 0 (saneamiento, sin juego) y Fase 1 (lanzadores e imports) sobre `main`.
3. Fase 3 (imagen limpia) en paralelo con la Fase 1: comparten el ensamblado del directorio.
4. Fase 4 (headless fino, escalado y render).
5. Fase 5 (reentrenar) en cuanto Fases 1 y 3 funcionen.
6. Fase 6 (comunicación) solo cuando se quiera render como observación o se vea cuello de botella.
