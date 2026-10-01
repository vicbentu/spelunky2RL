# Preguntas — para ti

Nada de lo que hay aquí bloquea el trabajo. *Para responder*: no lo decidí; lo que depende de ello está
aparcado y el resto sigue. *Decidido sin ti*: lo elegí y lo apliqué; se mantiene salvo que digas otra
cosa, y cada entrada da cómo deshacerlo. Respondes en el chat o con una línea `**Answer:** …` bajo la
entrada; las respondidas se aplican y se borran, el porqué va en un párrafo `Decided:` del commit que las
aplica. `@sha` es el commit en que estaba el código al escribir la entrada.

## Para responder

## Decidido sin ti

### 1. [2026-09-28 12:55 @4a53a57] Sin campo `license` en `pyproject.toml`

No he puesto licencia: el repo no tiene fichero LICENSE y elegirla es cosa tuya.

Coste: PyPI y los usuarios no saben bajo qué términos pueden usar el código. `luasocket/` trae su
propia licencia (MIT) y `entities-hierarchy.md` viene de overlunky (MIT).

Para cambiarlo: añadir `LICENSE` y `license = "MIT"` (o la que elijas) en `[project]`.

### 2. [2026-09-28 13:18 @4a2a9cf] La imagen del juego no está publicada

El nombre por defecto es `ghcr.io/vicbentu/spelunky2rl-game:<versión>` y `.github/workflows/docker.yml`
la publica al crear un tag `v<versión>`. No he hecho push ni creado tags (es una acción externa).
Mientras tanto, `spelunky2rl pull` falla y hay que construirla en local
(`docker build -f docker/Dockerfile -t ghcr.io/vicbentu/spelunky2rl-game:0.1.0 .`); así la he probado yo.

Coste: un externo no tiene todavía el "un comando" del objetivo de setup trivial. Tras el primer push
en GHCR hay que marcar el paquete como público en la configuración del paquete en GitHub.

Para cambiarlo: otro registro (Docker Hub) = cambiar `DEFAULT_IMAGE` en `engine/launchers/docker.py` y
el login del workflow.

### 3. [2026-09-28 13:18 @4a2a9cf] Overlunky: build "whip" fijada por hash, no por versión

Overlunky solo publica una build continua (`whip`) que se reemplaza en el mismo URL.
`docker/versions.env` fija su sha256 (build del 2026-09-16). Cuando upstream la cambie, el build de la
imagen fallará en el checksum a propósito.

Coste: reconstruir la imagen en el futuro exige actualizar el hash (y probar). Las imágenes ya publicadas
no se ven afectadas.

Para cambiarlo: alojar una copia del zip (release propia en este repo) y apuntar `OVERLUNKY_URL` ahí.

### 5. [2026-09-28 13:18 @4a2a9cf] El modo `wine` copia el prefijo por instancia (~1,2 GB cada uno)

`WineLauncher` reserva "slots" con un bloqueo y copia el prefijo base la primera vez
(`cp --reflink=auto`, gratis en btrfs/xfs). Con un prefijo compartido, 1 de 4 instancias fallaba.

Coste: disco la primera vez en ext4. Solo afecta al modo sin Docker.

Para cambiarlo: borrar `~/.local/share/spelunky2rl/wine/prefixes/`; o investigar el fallo con prefijo
compartido.

### 6. [2026-10-01 21:51 @d1b3d70] La traza de referencia del mod Lua no se guarda en git

`tests/integration/golden.py record` deja la traza (24 episodios, 4853 mensajes, 0,8 MB comprimida) en
`tests/integration/data/golden_trace.jsonl.gz`, y `tests/integration/data/` está en `.gitignore`.

Elegí no versionarla: solo vale para un build del juego (`15a31692700c3c94`) y un build de Overlunky,
así que a otra máquina no le sirve, y cada cambio de comportamiento buscado (los Bugs del backlog sobre
`main.lua`) obliga a regrabarla: 0,8 MB binarios más en el historial cada vez.

Descartado:
- Versionarla en `tests/integration/data/`: quien clone tiene la referencia sin regrabar y el fichero
  queda ligado al commit del mod que la generó; a cambio, binarios en el historial y una traza que
  falla sin motivo con otro build del juego.
- Fuera del repo (`~/.cache/spelunky2rl/`): no ensucia el árbol, pero es más fácil perderla de vista.

Coste si me equivoco: si se borra el fichero hay que regrabarlo desde el commit de referencia (~25 s):
`git worktree add <dir> d1b3d70` y `golden.py record --mod <dir>/src/spelunky2rl/mod/lua`.

Para cambiarlo: quitar la línea `tests/integration/data/` de `.gitignore` y `git add` del fichero.
