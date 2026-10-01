# Run — Reorganizar el mod Lua en módulos (`PLAN.md`, fases 0-6)  ·  started [2026-10-01 21:12 @d1b3d70]

## Log

- [2026-10-01 21:12] Arranque. Sin `RUN.md` previo; `QUESTIONS.md` sin respuestas pendientes. El plan no
  toca nada irreversible ni externo (commits locales en `refactor/lua`; la Fase 6 reconstruye la imagen
  local `ghcr.io/vicbentu/spelunky2rl-game:0.1.0`). Verificación: `tests/unit`, `tests/integration` con
  `SPELUNKY2RL_GAME_DIR=~/spelunkyrl-test/gamero`, y la traza de referencia de la Fase 0.
- [2026-10-01 21:51] Fase 0 hecha. `tests/integration/golden.py` (`record` / `compare`): 24 episodios
  seguidos en una instancia, 4853 mensajes crudos capturados en el socket del motor. Tres cosas que no
  estaban en el plan: (1) la primera versión seguía dando pasos tras la muerte y los episodios
  siguientes salían congelados (`time` fijo): un `reset` desde la pantalla de muerte atasca el juego →
  BACKLOG, y los episodios se cortan 60 frames después de morir. (2) Dos grabaciones del mismo mod
  diferían solo en el orden de las claves JSON (orden interno de las tablas Lua, distinto en cada
  proceso), así que la comparación es por campos y valores, con los números como texto, no byte a
  byte. (3) Con acciones aleatorias nunca se llegaba a la salida: una búsqueda por haz con repetición
  desde el reset encontró una secuencia fija (semilla 268, tres bombas hacia abajo y puerta) que da
  `win=1` y sigue en 1-2; va como episodio `exit_and_next_level`. Verificado: `record` + dos
  `compare` → `OK: 24 episodes, 4853 messages, all identical`; un mod con `frames = 61` en `reset`
  falla en los 24. `require("spelunky2rl.probe")` carga en el juego (lo resuelve el `require` de
  Overlunky, relativo al script; la línea `package.path` no hace falta para eso). La traza queda en
  `tests/integration/data/` sin versionar → Q6.
- [2026-10-01 21:55] Fase 1 hecha: fuera `jumper/` (12 ficheros) y `pf_grid`/`pf_finder`, las variables sin uso
  (`tiles`, `map_info`, `dist_to_goal`, `pos_type_matrix`), las medidas con `get_performance_counter` y
  el bloque comentado de `back_type`; `destroy_entities`, `count_dead_enemies`, `get_entities_info` y
  `math.round` (ahora `round`) pasan a locales. Nada se mueve de sitio todavía, para que el diff se lea
  solo como borrado. Verificado: `luac -p`, y `golden.py compare` → `OK: 24 episodes, 4853 messages, all
  identical`.
