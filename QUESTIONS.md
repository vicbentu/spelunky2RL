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
