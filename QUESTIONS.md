# Preguntas abiertas

Decisiones que he tomado durante la implementación de `plan.md` y que quizá quieras revertir.
**Nada de lo que hay aquí bloquea el trabajo; si no hay respuesta, la decisión se mantiene.**

Formato: qué decidí, por qué, qué cuesta y el cambio que lo deshace.

---

## 1. Sin campo `license` en `pyproject.toml`

- **Decisión**: no he puesto licencia. El repo no tiene fichero LICENSE y elegirla es cosa tuya.
- **Coste**: PyPI y los usuarios no saben bajo qué términos pueden usar el código. `jumper/` y
  `luasocket/` traen sus propias licencias (MIT) y `entities-hierarchy.md` viene de overlunky (MIT).
- **Para cambiarlo**: añadir `LICENSE` y `license = "MIT"` (o la que elijas) en `[project]`.

## 2. La imagen del juego no está publicada

- **Decisión**: el nombre por defecto es `ghcr.io/vicbentu/spelunky2rl-game:<versión>` y
  `.github/workflows/docker.yml` la publica al crear un tag `v<versión>`. No he hecho push ni creado
  tags (es una acción externa). Mientras tanto, `spelunky2rl pull` falla y hay que construirla en
  local (`docker build -f docker/Dockerfile -t ghcr.io/vicbentu/spelunky2rl-game:0.1.0 .`); así la he
  probado yo.
- **Coste**: un externo no tiene todavía el "un comando" del objetivo 4. Tras el primer push en GHCR
  hay que marcar el paquete como público en la configuración del paquete en GitHub.
- **Para cambiarlo**: otro registro (Docker Hub) = cambiar `DEFAULT_IMAGE` en
  `engine/launchers/docker.py` y el login del workflow.

## 3. Overlunky: build "whip" fijada por hash, no por versión

- **Decisión**: Overlunky solo publica una build continua (`whip`) que se reemplaza en el mismo URL.
  `docker/versions.env` fija su sha256 (build del 2026-09-16). Cuando upstream la cambie, el build de la
  imagen fallará en el checksum a propósito.
- **Coste**: reconstruir la imagen en el futuro exige actualizar el hash (y probar). Las imágenes ya
  publicadas no se ven afectadas.
- **Para cambiarlo**: alojar una copia del zip (release propia en este repo) y apuntar `OVERLUNKY_URL` ahí.

## 5. El modo `wine` copia el prefijo por instancia (~1,2 GB cada uno)

- **Decisión**: `WineLauncher` reserva "slots" con un bloqueo y copia el prefijo base la primera vez
  (`cp --reflink=auto`, gratis en btrfs/xfs). Con un prefijo compartido, 1 de 4 instancias fallaba.
- **Coste**: disco la primera vez en ext4. Solo afecta al modo sin Docker.
- **Para cambiarlo**: borrar `~/.local/share/spelunky2rl/wine/prefixes/`; o investigar el fallo con prefijo compartido.
