# Gestos soportados (resumen actual)

El detector principal se encuentra en `vision/gesture_detection/facial_gestures.py`. Los gestos que el sistema reconoce y exporta como booleanos son:

- `mouth_pucker` — fruncir labios / pucherito.
- `mouth_open` — boca abierta.
- `mouth_o` — embocadura tipo “O” (mouth funnel).
- `smile_left` — sonrisa lado izquierdo.
- `smile_right` — sonrisa lado derecho.
- `smile` — sonrisa bilateral (ambos lados).
- `brow_raise` — cejas levantadas.
- `brow_frown` — fruncir cejas.
- `eye_blink` — parpadeo / guiño de un ojo.
- `eye_wide` — ojos muy abiertos.
- `nose_sneer` — arrugar la nariz.

Notas:
- Los gestos usan una línea base neutral (calibración automática al inicio) y requieren un número mínimo de frames consecutivos para activarse (debounce).
- Los nombres de gesto se usan para mapear acciones en la configuración (`gesture_actions`).
- Actualmente las acciones tipo `hotkey` se envían al sistema con `pyautogui` (módulo `core/gesture_engine/hotkey_executor.py`), por lo que la ventana objetivo debe tener foco para recibir las teclas.
- Para juegos/demos locales puede ser más conveniente mapear gestos a eventos internos en lugar de hotkeys; esa capa interna no está añadida por defecto y debería implementarse si se desea.

