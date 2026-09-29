# Decisiones

Solo se añade al final. `## [ts] título`: qué se decidió, por qué, qué se descartó. Nunca se edita una
entrada pasada; una marcha atrás es una entrada nueva que cita la anterior.

Las entradas del 2026-09-28 vienen del plan de retoma (`plan.md` en la raíz, hasta el commit `222ac52`)
y llevan la hora del commit que las registró. El estudio previo completo (diagnóstico de Windows, bugs de
la auditoría, investigación de Linux/headless con fuentes) está en `git show 222ac52:plan.md`, secciones
1 y 2; los resultados de las pruebas, en `feasibility/RESULTS.md` de la rama
`test/ubuntu-and-headless-feasability`.

## [2026-09-28 12:53] Linux vía Wine + DXVK en Xvfb, sin Steam en ejecución

Probado en la rama `test/ubuntu-and-headless-feasability`: Wine 10 de Ubuntu + DXVK 3.1.1 en Xvfb,
luasocket funciona bajo Wine, no hay mutex de instancia única, ~1.500 pasos/s por instancia, lavapipe
funciona sin GPU (~15 % más lento con `state_updates` alto). Steam solo hace falta para descargar el juego:
en ejecución se usa Goldberg (gbe_fork) en lugar de `steam_api64.dll` (el juego no tiene DRM propio). Ni
Steam ni modlunky2 en ejecución. Descartados: Proton/umu-launcher (Wine puro basta), gamescope headless
(inmaduro), Windows headless con displays virtuales (una VM por instancia, frágil).

## [2026-09-28 12:53] La librería solo depende de Gymnasium; Python fuera del contenedor

Cada `SpelunkyEnv` arranca su propio juego en `__init__` y lo libera en `close()`. Cómo paralelizar y
entrenar lo decide el usuario (`gymnasium.vector`, SB3, RLlib…); SB3 solo aparece en ejemplos como extra.
El código Python corre en el entorno del usuario; Docker solo contiene el juego ejecutable (Wine, prefijo
con DXVK, Playlunky, Goldberg, Overlunky, plantillas de ini y el mod Lua).

## [2026-09-28 12:53] Un contenedor efímero por instancia, con host network

`SpelunkyEnv.__init__` lanza `docker run --rm` y `close()` lo mata: nada corre en segundo plano, sin
gestor de larga vida. `--network host` para que el Lua conecte a `127.0.0.1` del host con el protocolo
actual. Cada contenedor tiene su propio prefijo de Wine y su propio Xvfb con número de display único,
porque con host network los sockets abstractos de X se comparten.

## [2026-09-28 12:53] La imagen no contiene el juego; directorio por instancia = granja de enlaces

El usuario monta su carpeta en `/game:ro` (el juego no se puede redistribuir). El directorio de cada
instancia son enlaces simbólicos a `/game/*` más ficheros reales para lo nuestro (`steam_api64.dll` de
Goldberg, ini, `steam_appid.txt`) y lo que escribe el juego. Descartado overlayfs: mismo rendimiento pero
exige `SYS_ADMIN`, AppArmor desactivado y/o `/dev/fuse`.

## [2026-09-28 12:53] Caché de Playlunky compartida, escribible y con bloqueo automático

`Mods/Packs/.db` en un volumen por imagen y hash de `Spel2.exe` (`~/.cache/spelunky2rl`). La primera
instancia toma un bloqueo exclusivo, arranca hasta que el Lua conecta y lo suelta; las demás esperan. Con
la caché válida no se bloquea nada ni hay paso manual. Baja el arranque de ~12 s a ~8 s y ahorra 825 MB
por instancia. No puede ser de solo lectura. Verificado con 4 arranques en frío en paralelo.

## [2026-09-28 12:53] El pack del mod solo contiene `lua/`; scripts `unsafe` vía Overlunky

Playlunky escribe dentro de la carpeta del mod y se cuelga si es de solo lectura y encuentra imágenes que
convertir (`docs/*.png`). Playlunky arranca siempre desactivados los scripts con `meta.unsafe`, así que se
lanza con `--overlunky` y `overlunky.ini` con `autorun_scripts = ["main.lua"]`,
`script_dir = "Mods/Packs/spelunky2rl/lua"` y `enable_unsafe_scripts = 1`.

## [2026-09-28 12:53] Renderer elegible: `renderer="auto" | "gpu" | "cpu"`

`auto` pasa `--gpus all` si hay GPU NVIDIA; sin ella DXVK cae solo a lavapipe. `gpu` falla si no hay GPU;
`cpu` fuerza lavapipe (`VK_ICD_FILENAMES`). La imagen incluye `nvidia_icd.json`, que el runtime de NVIDIA
no inyecta.

## [2026-09-28 12:53] Handshake de versión del protocolo y modo desarrollo del Lua

Al conectar, el Lua envía `{"hello": {"protocol": N, "mod": "x.y.z"}}`; Python lo compara con su
constante y falla indicando la imagen necesaria. La etiqueta de la imagen coincide con la versión del
paquete (`spelunky2rl-game:<versión>`). `SPELUNKY2RL_DEV_MOD=<repo>/src/spelunky2rl/mod/lua` monta el Lua
local sobre el de la imagen: cambios de Lua y Python sin rebuild.

## [2026-09-28 12:53] Paquete `spelunky2rl`, layout `src/`, el Lua dentro del paquete

Distribución e import en minúsculas, coherente con el repo; el pack del mod también se llama
`spelunky2rl`. El Lua vive en `src/spelunky2rl/mod/lua` y es la única fuente (Dockerfile, `WineLauncher` y
modo desarrollo salen de ahí), así Python y Lua van siempre en la misma versión. Layout `src/` para que
los tests corran contra el paquete instalado. `examples/` fuera del paquete; SB3 y torch solo como extras.
`environments/` pasó a `envs/`. `feasibility/` no se fusiona en `main`: se queda en su rama como registro.
Se mantiene el nombre de clase `SpelunkyRLEngine`.

## [2026-09-28 12:53] Lanzadores en Python detrás de una interfaz común

`DockerLauncher` (camino principal y de servidor) y `WineLauncher` (Linux sin Docker, para desarrollo;
mismo ensamblado de directorio). El proceso propio se identifica por el puerto (`Spelunky_RL_Port`) o por
el nombre del contenedor, nunca por nombre de proceso. Las plantillas `overlunky.ini`/`playlunky.ini`
viven en `src/spelunky2rl/engine/launchers/config/` (no en `docker/config/`) porque también las usa
`WineLauncher`; el Dockerfile las copia desde ahí.

## [2026-09-28 13:53] Headless desde Lua; `set_frametime(0)` y la espera tras `reset` se quedan como estaban

Con `render_enabled=False` no se dibuja nivel ni HUD (+18 % a `state_updates=0`); VSync y audio
desactivados. `set_frametime(0)` no mejora sobre el speedhack (medido): no se usa. La espera de 60 frames
tras el reset no es el coste (el reset cuesta ~45 ms de generar el nivel; con 5 frames tarda igual;
saltarse `play_adventure` ahorra 5 ms): se deja. Opción `time_ghost` porque sin ella, a los 300 s de
juego, cae de ~1.800 a ~200 pasos/s. `render()` necesita un `local.cfg` propio en ventana: a pantalla
completa la superficie Vulkan queda en 1x1 y todo sale negro.

## [2026-09-28 14:02] El protocolo se queda en JSON por TCP; `TCP_NODELAY` en ambos lados

Medido (Linux, `state_updates=200`, 1 instancia): ~92 % del paso es esperar al juego; Python (JSON +
observación) es < 10 % (`get_to_exit`: 14 µs de `json.loads` y 63 µs del resto sobre 940 µs). En el juego:
~200-250 µs fijos por intercambio y ~80-100 µs por frame lógico; `map_info` +150 µs/paso, `entity_info`
+110 µs, `dist_to_goal` ~0. Un formato binario (`string.pack` / `numpy.frombuffer`) ganaría como mucho
15-25 % en entornos con `map_info`: no compensa todavía. `TCP_NODELAY` no cambia nada medible en Linux;
se deja por Windows. Al escalar, el cuello de botella es el paso síncrono de los vector envs
(`AsyncVectorEnv` se queda en ~3k pasos/s con 16 entornos frente a 14,3k del juego): entrenar con recogida
asíncrona rinde más que cualquier mejora del protocolo.

## [2026-09-28 15:35] Windows nativo fuera por ahora

Se eliminaron `WindowsLauncher`, `Win32FrameSource`, pywin32 y los parámetros `console`/`playlunky_dir`;
`launcher="windows"` y ejecutar en Windows lanzan `NotImplementedError`. Anula la parte de Windows de la
entrada "Lanzadores en Python" (Docker Desktop en Windows no tiene GPU ni host network reales, así que el
camino previsto era un lanzador nativo).

## [2026-09-28 16:14] La entrada del agente se escribe en `PRE_UPDATE`, no con `steal_input`

`steal_input` ignoraba la entrada del agente en ~40 % de los episodios (también con el Lua original de
`main`) y hacía los episodios no reproducibles; fue la causa del primer reentrenamiento fallido (0 % de
éxito a 2,6 M pasos). Ahora se escribe `state.player_inputs` en `PRE_UPDATE`; 20/20 semillas idénticas.

## [2026-09-30 00:17] Notas de trabajo en `notes/`

`plan.md`, `lua_plan.md`, `BACKLOG.md` y `QUESTIONS.md` se movieron a `notes/` con el formato común
(`PLAN.md` con Now/Next/Later, `plans/<slug>.md`, `DECISIONS.md`). Del plan de retoma solo queda lo
pendiente; las fases hechas y el estudio previo están en git (`git show 222ac52:plan.md`).
