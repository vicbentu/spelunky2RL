# Plan

Ordenado. Lo primero de *Now* es lo que significa "sigue el plan". Los temas grandes enlazan un
`plans/<slug>.md`; lo hecho se borra (git es el archivo). El plan de retoma original, con las fases ya
hechas, está en `git show 222ac52:plan.md`.

## Now
- Reorganizar el mod Lua en módulos, mismo comportamiento byte a byte → [plans/lua-modules.md](plans/lua-modules.md)

## Next
- Reentrenar `get_to_exit` con el contrato corregido (terminated/truncated, seed reproducible, entrada en `PRE_UPDATE`); el primer intento (`~/spelunkyrl-test/train_2026-09-28/`, 0 % de éxito a 2,6 M pasos, 333 pasos/s) se hizo antes de arreglar la entrada
- Comparar con los modelos de mayo de 2025: no están en esta máquina, hay que copiarlos desde el PC de Windows
- `examples/record_video.py` de punta a punta con un modelo entrenado (último pendiente de headless/render)
- Publicar la imagen del juego (tag `v<versión>` → `.github/workflows/docker.yml`); pendiente de push, ver `QUESTIONS.md` #2

## Later
- Protocolo binario (`string.pack` / `numpy.frombuffer`): techo estimado 15-25 % en entornos con `map_info`; hoy no compensa (ver `DECISIONS.md`, 2026-09-28 14:02)
- Render por memoria compartida con número de secuencia, solo si se quieren píxeles como observación (hoy `render()` lee el Xvfb con mss)
- Captura dentro del juego enganchando `IDXGISwapChain::Present`, mismo caso que el anterior; también quitaría la barra de Overlunky de los frames (ver `BACKLOG.md`)
