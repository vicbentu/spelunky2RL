# Plan — `dist_to_goal` correcto y robusto antes de reentrenar

Solo el objetivo en marcha. "Sigue el plan" es el primer paso no hecho. Al terminar, este fichero se
borra; lo siguiente está en `BACKLOG.md` → *Next* (el reentreno de `get_to_exit`).

> [2026-10-02 14:32] El reentreno de `get_to_exit` son horas de cómputo sobre una recompensa que hoy
> tiene fallos conocidos: `dist_to_goal` se calcula en la celda equivocada, arrastra el valor del
> episodio anterior, puede ser de otro mapa, y en dos casos límite el mod Lua muere dentro de
> `POST_UPDATE` y Python espera 60 s sin explicación. Arreglar eso primero, en `pathfinding.lua`,
> `session.lua` y `core.py`, sin cambiar el protocolo. Hecho cuando los tests unitarios y de
> integración pasan con los arreglos y una ejecución real confirma el 0 dentro de la puerta.
> Rama: `refactor/spelunky2rl`. Fuera de alcance: la capa trasera (bugs de `count_dead_enemies` y
> `pf_refresh` por capa en BACKLOG), el `reset` tras la pantalla de muerte, la UI de Overlunky en los
> frames.

---

## 1. Qué está mal hoy (`src/spelunky2rl/mod/lua/spelunky2rl/pathfinding.lua` en ffa87f4)

1. **Celda del jugador con `floor`** (`distance`, l. 124-125): `math.floor(x - left + 1)` y
   `math.floor(top - y + 1)`. Las entidades están centradas en enteros (el bloque `tx` va de `tx-0.5`
   a `tx+0.5`; el jugador de pie tiene `y = ty + 0.05`), así que al jugador se le asigna la fila de
   encima y, entre `tx+0.5` y `tx+1`, la columna anterior. Semilla 268: dentro de la puerta de salida
   (`x=7.22, y=94.05`, puerta en (7, 94)) `dist_to_goal` vale 1, no 0. `observations.map_info` sí
   redondea (`util.round`); los entornos lo compensan con `dist_to_goal <= 1`.
2. **`last_distance` sobrevive al `reset`** (l. 49): si la celda inicial no está en el campo, el
   primer `dist_to_goal` del episodio es el último del anterior, y la recompensa del primer paso
   (`(last - actual) * 0.1`) se calcula contra otro mapa.
3. **`refresh` sale sin reconstruir si el número de bloques no cambió** (l. 54): tras un `reset` o
   un nivel nuevo con el mismo recuento, `tile_ids`, el tablero, `distances` y la salida son del nivel
   anterior. `dirty` ya es la señal exacta; el filtro sobra. `tile_ids()` no limpia `dirty` (solo
   `distance()` lo hace) y hoy ese es el motivo de que exista el filtro.
4. **Una sola salida, y `nil` sin ninguna** (l. 92-99): `exits[1]` (1-4 tiene dos salidas: Jungla y
   Volcana); sin ninguna, `goal_x/goal_y` conservan el valor anterior (0,0 al arrancar) y
   `distance_field` hace `field[0][0]`, que es `nil`: error dentro de `POST_UPDATE`.
5. **Fila comprobada, columna no** (l. 127-128): jugador fuera del tablero por la izquierda o la
   derecha → `distances[row][column]` es `nil` y `nil > -1` es un error dentro de `POST_UPDATE`.
6. **Un error en Lua no llega a Python** (`session.lua`, `on_post_update`): `engine/protocol.py`
   l. 53 ya convierte `{"error": ...}` en `RuntimeError` y `docs/architecture.md` ("Lua Errors") dice
   que el mod lo manda, pero ningún módulo lo hace. Los puntos 4 y 5 hoy son "timeout a los 60 s".
7. **`_game_reset` acepta cualquier opción** (`engine/core.py`, l. 219 `**kwargs`): `bomb=3` en el
   constructor o en `reset()` se ignora en silencio y el episodio arranca con los valores por defecto.

**Medido en el juego real** [2026-10-02 22:07 @766e650], antes de tocar nada: `GetToExit` en 1-1,
`god_mode`, 31 semillas seguidas en un mismo entorno (268, 0..29) x 600 pasos de una política
aleatoria sin bombas, con una copia del mod que además envía el valor del campo en la celda que usa
el código y en la celda redondeada. Las cifras del punto 1 excluyen la semilla 29 (ver punto 3).
Los porcentajes dependen de la política (la aleatoria pasa mucho tiempo contra paredes); los
mecanismos no.

- Punto 1, confirmado. El código usa la celda `(floor(x), ceil(y))`: en 18 030 pasos no hay ni un caso
  que lo contradiga. Esa celda no es la del jugador en el 92 % de los pasos, y es sólida en el 38 %:
  ahí `dist_to_goal` es el valor anterior, congelado. El valor enviado difiere del correcto en el
  77 % de los pasos (de -5 a +6; en 2 o más, el 24 %). El 26 % del avance real ocurre con la
  distancia congelada y se cobra después de golpe (hasta 9 en un paso). Ejemplo: semilla 8, pasos
  577-582, andando bajo un techo: correcto 84 → 79, enviado 85 fijo, y luego 85 → 77 en un paso.
- Con `round`, la celda del jugador es alcanzable en todos los pasos y el invariante de abajo (§3,
  Tests) no falla nunca; con el código actual falla en el 28 % de los pasos.
- Bloques y salidas están en coordenadas enteras exactas (parte fraccionaria máxima 0): `floor` y
  `round` coinciden en ellos; el cambio ahí es solo robustez.
- Punto 3, reproducido: las semillas 28 y 29 tienen 1108 bloques las dos. `reset(29)` tras un
  episodio de la 28 no reconstruye: todo el episodio corre con `map_info`, tablero y salida de la
  28 (en el arranque, el centro de `map_info` es `FLOOR_GENERIC` y no la puerta de entrada; errores
  de hasta 35). 1 de los 30 `reset` que siguen a otro episodio. Con el punto 2 encima: el primer `dist_to_goal` de la 29 es 106, el
  último de la 28.
- Punto 2 solo, sin el 3: no visto en las 30 semillas restantes (la celda inicial siempre fue
  alcanzable para el código actual).

## 2. Lo que no cambia

- El protocolo (`PROTOCOL_VERSION = 1`): mismos mensajes, mismos campos, mismo formato de
  `dist_to_goal` (entero, -1 si nunca hubo celda alcanzable), `map_info` 11x21 y `entity_info`.
- `distance()` fuera de las celdas alcanzables sigue devolviendo la última distancia válida; el
  cambio es que "última" ahora es del episodio en curso.
- Cuándo se reconstruye el tablero: al aparecer o destruirse un bloque de suelo (`mark_dirty` desde
  `main.lua`). Quitar el filtro por recuento solo añade los casos en que el recuento coincide.
- El umbral `dist_to_goal <= 1` de los entornos (`envs/get_to_exit.py` l. 70, `default_environment.py`
  l. 177, `template_environment.py` l. 180) **se queda**: con la celda bien calculada significa "en la
  puerta o en una casilla contigua". Pasar a `== 0` (o usar `win`) es una decisión de diseño de la
  recompensa; va a `QUESTIONS.md` → *Para responder*, no se decide aquí.
- La imagen Docker lleva el mod copiado (`docker/Dockerfile` l. 32). No se reconstruye en este plan;
  los tests de integración usan `SPELUNKY2RL_DEV_MOD=src/spelunky2rl/mod/lua`. La imagen que se
  publique (BACKLOG → *Next*) se construye después de esto.

## 3. Diseño

**`pathfinding.lua`**

- `M.distance_field(board, goals)`: `goals` es una lista de `{x, y}`; todas entran en la cola con
  distancia 0 (BFS multi-fuente). Lista vacía → campo entero a -1. Una meta fuera del tablero se
  ignora. Los tres tests de `tests/unit/test_lua_pathfinding.py` se adaptan a la nueva firma.
- `refresh()`: sin `tile_count`. Coordenadas con `util.round` en los bloques (`tile.x`, `tile.y`), en
  las salidas y en el jugador (`distance`). Todas las salidas de `get_entities_by_type(FLOOR_DOOR_EXIT)`
  pasan a `goals`.
- `distance(x, y)`: `local cell = distances[row] and distances[row][column]`; si `cell` y `cell > -1`,
  `last_distance = cell`.
- `tile_ids()` pone `dirty = false` igual que `distance()`. Deja de haber dos semánticas.
- `M.reset()`: `last_distance = -1`, `dirty = true`. La llama `session.start()` al recibir `reset`
  (antes de `control.start_level`).

**`session.lua`**

- `M.on_post_update` envuelve su cuerpo en `xpcall(body, debug.traceback)`. Si falla:
  `protocol.send({error = traza})` dentro de un `pcall` (el socket puede estar roto) y `os.exit()`.
  Después de un error el estado del mod no es fiable; salir es lo que ya hace al perder la conexión,
  y Python ya levanta `RuntimeError` con el texto (`test_lua_error_is_raised`).

**`core.py`**

- `_game_reset` pierde `**kwargs`. En `__init__`, las `kwargs` que se guardan como `reset_options`
  se comprueban contra `inspect.signature(self._game_reset).parameters` y una desconocida es
  `TypeError` con los nombres sobrantes, en la construcción y no en el primer `reset`. Las
  de `reset(**kwargs)` fallan solas al llamar a `_game_reset`.

**Tests**

- Unitarios: `test_lua_pathfinding.py` (+ dos metas, + sin meta); `test_engine.py` (opción
  desconocida → `TypeError` que nombra `bomb`).
- Integración (`tests/integration/test_game.py`, con juego): `reset(B)` tras `reset(A)` + 50 pasos da
  el mismo `dist_to_goal` y `map_info` iniciales que `reset(B)` en un entorno recién creado. Es la
  prueba de que nada del episodio anterior sobrevive (puntos 2 y 3). A = 28, B = 29: con el mismo
  recuento de bloques (1108) el test falla hoy; con dos semillas cualesquiera pasaría sin el arreglo.
- Integración, invariante de celda (punto 1): en 1-1 (una salida), sin bombas, varias semillas y
  acciones fijas; con la celda `(floor(x + 0.5), floor(y + 0.5))` calculada en Python a partir de
  `basic_info`, entre dos pasos seguidos `|Δ dist_to_goal|` no supera el desplazamiento Manhattan de
  la celda y tiene su misma paridad (celda igual → distancia igual; celda contigua → ±1). Solo usa
  lo que el protocolo ya envía. Hoy falla; con `round` no.
- A mano, anotado en `RUN.md`: semilla 268 con `manual_control`, dentro de la puerta
  `dist_to_goal == 0`; y un `error("probe")` metido a mano en `on_post_update` (sin commitear) hace
  que `env.reset()` levante `RuntimeError` con la traza en segundos, no un timeout a los 60 s.

## 4. Pasos

### 1. `_game_reset` rechaza opciones desconocidas  ·  done [2026-10-03 14:05]
Criterio: `DefaultEnv(bomb=3)` y `env.reset(bomb=3)` levantan `TypeError` que nombra `bomb`; test
nuevo en `tests/unit/test_engine.py`; `python -m pytest` verde.

### 2. Los errores de Lua llegan a Python  ·  pending
Criterio: con un `error("probe")` provisional en `on_post_update`, `env.reset(seed=0)` levanta
`RuntimeError` cuyo mensaje contiene `probe` y una traza, en menos de 5 s. Comando y salida en
`RUN.md`. `tests/integration` verde con el mod sin la sonda. `docs/architecture.md` "Lua Errors" dice
de dónde sale el error.

### 3. BFS desde todas las salidas; columna comprobada  ·  pending
Criterio: `pytest tests/unit/test_lua_pathfinding.py` verde con dos tests nuevos: dos metas (cada
celda toma la más cercana) y lista vacía (todo -1). `grep -n "exits\[1\]" src/` no encuentra nada.

### 4. Coordenadas redondeadas  ·  pending
Criterio: semilla 268, jugador dentro de la puerta de salida: `dist_to_goal == 0` (hoy 1). Test de
integración nuevo con el invariante de celda (§3), rojo antes del cambio y verde después. Entrada en
`QUESTIONS.md` → *Para responder* sobre el umbral `<= 1`. `tests/integration` verde.

### 5. Nada del episodio anterior sobrevive al `reset`  ·  pending
Criterio: test de integración nuevo (`reset(29)` tras `reset(28)` + pasos == `reset(29)` en frío),
rojo antes del cambio y verde después;
`grep -n tile_count src/` no encuentra nada; `tests/integration` completo verde.

### 6. Cierre  ·  pending
Criterio: `docs/architecture.md` describe `pathfinding.lua` como queda (multi-salida, `reset`,
invalidación por `dirty`); `python -m pytest` y `tests/integration` verdes; este fichero borrado y
`BACKLOG.md` → *Next* sin cambios (lo siguiente es el reentreno).
