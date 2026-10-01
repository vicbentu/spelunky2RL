# Plan — Reorganizar el mod Lua en módulos

Solo el objetivo en marcha. "Sigue el plan" es la primera fase no hecha (sección 5). Al terminar, este
fichero se borra; lo siguiente está en `BACKLOG.md` → *Next*. El plan de retoma original, con las fases
ya hechas, está en `git show 222ac52:plan.md`.

> [2026-09-28 16:31] Mismo comportamiento, observable byte a byte, con `src/spelunky2rl/mod/lua/main.lua`
> (537 líneas) repartido en módulos con una responsabilidad cada uno, más `jumper/` (que se elimina).
> No es una tarea de funcionalidad nueva; lo único que cambia a propósito es quitar trabajo inútil
> (jumper) y código muerto. Rama: `refactor/lua`. Red de seguridad: una traza de referencia grabada con el
> mod actual y comparada mensaje a mensaje tras cada paso (sección 4.1).

---

## 1. Diagnóstico del `main.lua` actual

Todo en un fichero, en este orden: conexión y hello → ~20 variables de estado a nivel de módulo →
pathfinding → auxiliares → control del juego → extracción de observaciones → un callback
`POST_UPDATE` que lo coordina todo → callbacks pequeños (transición, headless, entrada del agente).

Problemas:

- **Estado compartido difuso.** Una sola línea declara 17 variables del jugador
  (`x, y, vel_x, …, pos_type_matrix, char_state, can_jump`) que `get_info` rellena y lee. Hay
  variables sin uso: `tiles`, `map_info`, `dist_to_goal`, `pos_type_matrix`.
- **Globales accidentales** (visibles para Overlunky y otros scripts): `destroy_entities`,
  `count_dead_enemies`, `get_entities_info`, `math.round` (modifica la tabla `math` compartida).
- **`jumper` no se usa.** `pf_refresh` construye `Grid(pf_board)` y `Pathfinder(pf_grid, "ASTAR", 0)`
  cada vez que cambia el número de bloques de suelo, pero `pf_distance` usa una BFS propia
  (`pf_build_distance_field`). `pf_grid`/`pf_finder` no se consultan nunca.
- **Código muerto de depuración**: medidas con `get_performance_counter` cuyo resultado se descarta,
  bloques comentados (`back_type`), `local type = entity.type.search_flags` sin uso.
- **Un callback que hace todo.** `POST_UPDATE` desactiva la pausa, cuenta frames, serializa y envía,
  recibe y decodifica, interpreta `reset`/`step`/`close`, aplica opciones y hace el bucle de
  `state_updates`. Es la zona donde estaba la recursión y donde un cambio de orden rompe el protocolo.
- **Nombres y comentarios mezclados** (`COMUNICATION`, comentarios en español e inglés).

## 2. Comportamientos sutiles que hay que conservar

La reorganización no debe cambiar ninguno. Se documentan aquí para revisarlos uno a uno:

1. **Protocolo.** El mod manda el hello nada más conectar. Después, en el frame en que el contador
   `frames` llega a 0: si el último comando fue `step` o `reset`, envía el estado; luego **bloquea**
   en `receive`. Si recibe `reset`, espera 60 frames; si recibe `step`, `frames` frames.
   Con `close` sale del juego. Si se pierde la conexión, sale del juego.
2. **Orden en `reset`**: `destroy_entities` y `set_start_values` se aplican en el frame en que se
   envía el estado inicial (60 frames después del `warp`), no al recibir el comando.
3. **Bucle de `state_updates`**: cada `update_state()` vuelve a disparar `POST_UPDATE` (y
   `PRE_UPDATE`), que ejecuta el protocolo; la bandera `fast_forwarding` evita bucles anidados.
   El protocolo **tiene** que seguir corriendo dentro de los frames simulados.
4. **Pausa desactivada** en cada frame (bit 19 de `level_flags`).
5. **`win`**: `ON.TRANSITION` pone `transition = 1`; `get_info` lo informa una vez y lo vuelve a 0.
6. **Sin jugador** (`#players == 0`): `health = 0` y el resto de campos conserva el último valor;
   un `step` sin jugador no actualiza la entrada.
7. **Distancia a la salida**: si la celda actual no está en el campo de distancias, devuelve la
   última distancia válida (`last_distance`, que empieza en -1).
8. **`map_info` y `pf_dirty`**: `get_map_info` refresca la tabla de bloques si `pf_dirty` pero no
   lo pone a `false` (lo hace `pf_distance`). Cambiarlo cambia cuándo se reconstruye la tabla.
9. **`pf_dirty`** se activa al aparecer o destruirse cualquier bloque de suelo
   (`set_post_entity_spawn` + `set_pre_destroy`).
10. **Entrada del agente**: se escribe en `PRE_UPDATE` en `buttons_gameplay` y `buttons` hasta el
    siguiente `step`; `nil` tras `reset` y `close`.
11. **Formato de cada campo** de `basic_info`, `map_info` (11x21, filas de arriba abajo),
    `entity_info` (`[dx, dy, vx, vy, tipo, face_left 0/1, tipo sostenido]`) y `dist_to_goal`.

Posibles bugs vistos (`last_distance` sin reiniciar en `reset`, `count_dead_enemies` solo en la capa
frontal) están en `notes/BACKLOG.md`: **no** se tocan aquí para que la comparación byte a byte siga valiendo.

## 3. Estructura propuesta

```
src/spelunky2rl/mod/lua/
├── main.lua                  # meta, package.path, conecta los callbacks; nada de lógica
├── spelunky2rl/              # namespace propio: require("spelunky2rl.x") no choca con otros scripts
│   ├── protocol.lua          # conexión, hello, send(tbl), receive() -> tbl | sale si se corta
│   ├── session.lua           # el antiguo POST_UPDATE: contador de frames, comandos, state_updates
│   ├── control.lua           # warp + temas, valores iniciales, destruir entidades, opciones de reset
│   ├── input.lua             # acción de Python -> INPUTS, callback PRE_UPDATE
│   ├── observations.lua      # basic_info, map_info, entity_info, dead_enemies, powerups
│   ├── pathfinding.lua       # tabla de bloques, campo de distancias BFS, pf_dirty
│   └── util.lua              # round, safe
└── luasocket/                # sin cambios
```

Reglas:

- Cada módulo devuelve una tabla (`local M = {} … return M`); **ningún global**.
- El estado vive dentro del módulo que lo posee (`pathfinding` su tabla de bloques, `session` el
  contador y el último comando, `observations` los últimos valores del jugador).
- Los callbacks de Overlunky se registran **solo** en `main.lua`, en el mismo orden que hoy, llamando
  a funciones de los módulos. Así se ve de un vistazo qué engancha el mod al juego.
- `jumper/` desaparece.
- `PROTOCOL_VERSION` y `MOD_VERSION` pasan a `protocol.lua`; el test que los compara con Python
  (`tests/unit/test_startup.py`) se actualiza a la nueva ruta.

Comprobado en la fase 0 con un submódulo de prueba: `require("spelunky2rl.x")` resuelve dentro del
juego, y lo hace incluso antes de la línea `package.path = "lua/?.lua;…"`: lo resuelve el `require`
propio de Overlunky, relativo a la carpeta del script. Dos `require` devuelven la misma tabla y
`package.loaded` no se toca (caché propia por script), así que un nombre no puede chocar con otro script.

## 4. Pruebas

### 4.1 Traza de referencia (la red principal)

Script `tests/integration/golden.py` con dos modos:

- `record`: con el mod **actual**, ejecuta un conjunto fijo de episodios y guarda **cada mensaje
  crudo** que envía el Lua (el JSON tal cual, antes de convertirlo en observación) en
  `tests/integration/data/golden_trace.jsonl.gz` (0,8 MB, ignorado por git: `QUESTIONS.md` #6).
- `compare`: ejecuta lo mismo con el mod nuevo (`--mod`, por defecto el del repo, montado vía
  `SPELUNKY2RL_DEV_MOD` sin reconstruir la imagen) y exige los **mismos campos con los mismos
  valores** mensaje a mensaje, con los números comparados como el texto que escribió el Lua. Si
  difiere, informa del episodio, paso y campo.

[2026-10-01 21:51] No se compara el orden de las claves: `json.encode` sigue el orden interno de la
tabla Lua, que cambia de un proceso del juego a otro (dos grabaciones del mismo mod ya diferían en eso
y en nada más). Todos los episodios van seguidos en una sola instancia, así que lo que el mod arrastra
de un episodio al siguiente (`last_distance`, la tabla de bloques) también queda en la traza.

Episodios (todos con `default_environment`, que pide `map_info`, `entity_info` y `dist_to_goal`):

| Caso | Qué cubre |
|---|---|
| semillas 0-4, 1-1, 300 pasos, acciones pseudoaleatorias con semilla fija | caso general, muertes (`god_mode=False`) |
| mismas semillas con `god_mode=True` | episodios largos sin muerte |
| `world=2,3,4,6` (+ `level=4` en 6) y `theme=3` | `warp` y temas |
| `hp=8, bombs=1, ropes=0, gold=500` | `set_start_values` |
| `ent_types_to_destroy` de `get_to_exit` | `destroy_entities` |
| `state_updates=0` y `200` | que el bucle de frames simulados no cambia nada |
| `frames_per_step=1` y `12` | contador de frames |
| usar bombas y cuerdas (acciones del espacio completo) | `pf_dirty` al destruir y crear bloques |
| `speedup=False`, 60 pasos | el mod sin bucle de frames simulados |
| semilla 268 con acciones fijas: baja con bombas a la salida, entra y sigue en 1-2 | `win`, pantalla de transición, tabla de bloques de un segundo nivel |

[2026-10-01 21:51] Los episodios sin `god_mode` se cortan 60 frames después de morir: seguir dando
pasos hasta la pantalla de muerte y resetear desde ahí deja el juego atascado (`BACKLOG.md`, Bugs).

La reproducibilidad ya está comprobada (20/20 semillas idénticas tras arreglar la entrada), así que
cualquier diferencia es un cambio de comportamiento. Antes de nada, `record` se ejecuta **dos veces**
con el mod actual y se compara consigo mismo: si ya difiere, hay no determinismo que resolver antes.

### 4.2 Lo que ya existe y debe seguir pasando

- `tests/unit` (62 tests, incluido que `PROTOCOL_VERSION`/`MOD_VERSION` coinciden con Python).
- `tests/integration/test_game.py`: episodio y limpieza, movimiento + determinismo, semillas,
  4 entornos en paralelo, `render()`.
- La comprobación de temas de la Fase 0 (1-1, 2-1, 3-1, 2-1 Volcana, 4-1, 6-4) queda dentro de la traza.

### 4.3 Rendimiento

`scratch`/benchmark de la Fase 4 (pasos/s con `state_updates` 0, 50, 200 y con/sin `map_info` y
`entity_info`) antes y después. Criterio: no más de un 5 % peor. Quitar jumper debería mejorar algo
cuando cambian los bloques (bombas, cuerdas).

### 4.4 Opcional: tests del pathfinding sin juego

Si `pathfinding.lua` separa la parte pura (tablero → campo de distancias BFS) de la lectura de
entidades, esa parte se puede probar con un intérprete `lua5.4` del sistema desde pytest (tableros
pequeños con distancias conocidas). Solo si el intérprete está disponible en CI; si no, se omite.

[2026-10-01 21:59] Hecho en la fase 2: `pathfinding.distance_field(board, goal_x, goal_y)` no toca la API del
juego y `tests/unit/test_lua_pathfinding.py` la prueba con el `lua` del sistema (3 tableros). Sin
intérprete los tests se saltan; el CI no instala Lua (`QUESTIONS.md` #7).

## 5. Fases (commits pequeños, cada una pasa la traza)

Riesgo principal: el orden de las operaciones dentro de `POST_UPDATE` (sección 2, puntos 1-3); la traza
lo detecta. Estimación: 1-2 horas.

**Criterio común (fases 1-5).** `golden.py compare` contra la traza grabada en la fase 0 da igualdad
exacta en todos los episodios de la sección 4.1, con el mod nuevo montado vía `SPELUNKY2RL_DEV_MOD`.

### Fase 0 — Traza de referencia  ·  status: done [2026-10-01 21:51]

Escribir `tests/integration/golden.py`, grabar dos veces con el mod actual y comprobar que coinciden.
Comprobar que `require("spelunky2rl.protocol")` resuelve dentro del juego con el `package.path` actual.

**Criterio.** Las dos grabaciones con el mod actual son idénticas; un submódulo de prueba carga en el juego.

**Verificado con:** `SPELUNKY2RL_GAME_DIR=~/spelunkyrl-test/gamero python tests/integration/golden.py record`
y dos veces `… golden.py compare` → `OK: 24 episodes, 4853 messages, all identical`. Con un mod alterado
(`data["frames"] = 61` en `reset`) → `FAILED: 24 of 24 episodes differ`, primer campo `basic_info.time`.
La traza se grabó con el `main.lua` de d1b3d70; para regrabarla, `git worktree add <dir> d1b3d70` y
`golden.py record --mod <dir>/src/spelunky2rl/mod/lua`.

### Fase 1 — Limpieza sin mover nada  ·  status: done [2026-10-01 21:55]

Quitar jumper y `pf_grid`/`pf_finder`, variables sin uso, medidas de tiempo y comentarios muertos;
convertir las globales accidentales en locales.

### Fase 2 — `util.lua` y `pathfinding.lua`  ·  status: done [2026-10-01 21:59]

[2026-10-01 20:59] Al mover el estado `pf_*`, renombrar los límites verticales: hoy `pf_ymin` guarda la
`y` más alta del nivel (fila 1 del tablero) y `pf_ymax` la más baja. Pasan a `top` y `bottom`; solo
cambian los nombres, no los valores ni las fórmulas.

### Fase 3 — `observations.lua` (con los últimos valores del jugador dentro)  ·  status: pending

### Fase 4 — `control.lua` e `input.lua`  ·  status: pending

### Fase 5 — `protocol.lua` y `session.lua`  ·  status: pending

`main.lua` queda solo con el registro de callbacks.

[2026-10-01 20:59] En `session.lua`, separar las dos cosas que hoy hace la tabla `data`: el último
mensaje recibido (`command`, de solo lectura) y el contador de frames (`frames_left`, un local que se
carga con `command.frames`, o 60 en `reset`, y se decrementa en cada `POST_UPDATE`). Valores iniciales
iguales a los de hoy: contador 0 y comando `"pass"`.

### Fase 6 — Imagen, tests, benchmark y docs  ·  status: pending

Reconstruir la imagen; actualizar `docs/architecture.md` (sección del Lua) y la ruta de
`PROTOCOL_VERSION` en el comentario de `engine/protocol.py`.

**Criterio.** `tests/unit` y `tests/integration` pasan con la imagen reconstruida; benchmark de la
sección 4.3 no más de un 5 % peor que antes.
