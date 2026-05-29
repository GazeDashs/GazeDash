# Control de mouse por mirada y rostro

Este documento explica qué se hizo y cómo funciona cada parte de la integración de control de mouse en el proyecto.

## Objetivo

El objetivo es usar la detección de rostro y landmarks faciales para mover el cursor del mouse de forma asistida, con suavizado y una zona muerta para evitar movimientos involuntarios.

## Módulos principales

### `core/input/mouse_driver.py`

- Proporciona una capa centralizada sobre `pyautogui`.
- Evita que todos los módulos importen `pyautogui` directamente.
- Importa `pyautogui` bajo demanda la primera vez que se necesita.
- Maneja errores de dependencia con un mensaje claro si `pyautogui` no está instalado.
- Métodos disponibles:
  - `move_rel(dx, dy)` — mueve el cursor relativo a su posición actual.
  - `move_to(x, y)` — mueve el cursor a una posición absoluta en pantalla.
  - `position()` — devuelve la posición actual del cursor.
  - `size()` — devuelve el tamaño de la pantalla.
  - `click()` — clic izquierdo.
  - `right_click()` — clic derecho.

### `core/input/mouse_controller.py`

- Implementa un controlador de tipo "joystick" que recibe coordenadas de referencia en píxeles.
- Funciona en modo relativo: el movimiento real del mouse depende de la distancia desde el centro de control.
- Parámetros:
  - `dead_zone` — radio en píxeles donde no se mueve el cursor.
  - `max_speed` — velocidad máxima de movimiento.
  - `smoothing` — cantidad de suavizado al aplicar el desplazamiento.
- Comportamiento:
  1. Si no hay centro calibrado, usa la primera posición como centro neutral.
  2. Calcula `dx`, `dy` respecto a ese centro.
  3. Si la distancia es mayor que `dead_zone`, calcula dirección y velocidad.
  4. Aplica suavizado exponencial a `move_x` y `move_y`.
  5. Llama a `MouseDriver.move_rel(...)` para mover el cursor.
- Métodos útiles:
  - `update(x, y)` — actualiza el control con una nueva coordenada de entrada.
  - `recalibrate(x, y)` — recalibra el centro.
  - `reset_center()` — borra la referencia central y el suavizado.

### `core/cursor_control/smoothing.py`

- Define la función `simple_exponential_smoothing(prev, current, alpha)`.
- Si no hay valor anterior, retorna el valor actual.
- Formula:
  - `prev * (1 - alpha) + current * alpha`
- Sirve para suavizar movimientos de mouse y reducir saltos bruscos.

### `core/cursor_control/cursor_mapper.py`

- Contiene la función `map_gaze_to_cursor(gaze_point, screen_size)`.
- Está diseñada para transformar un punto de mirada normalizado `(x, y)` en coordenadas absolutas de pantalla.
- Actualmente es un placeholder simple:
  - `x_pixel = gaze_point[0] * width`
  - `y_pixel = gaze_point[1] * height`
- Puede ampliarse con calibración y corrección de distorsión.

### `vision/face_tracking/face_detector.py`

- Usa MediaPipe Face Landmarker para detectar rostros y landmarks faciales.
- Devuelve métricas faciales en `detect(frame)`.
- Entre los datos devueltos ahora están:
  - `nose_tip`: coordenadas de la punta de la nariz en píxeles.
  - `face_center`: centro del rostro calculado entre mejillas.
- Esto permite usar `nose_tip` como entrada para el movimiento del cursor o como referencia para gestos.

## Flujo de trabajo esperado

1. Capturar un frame de la cámara.
2. Pasar el frame a `MediaPipeFaceDetector.detect(frame)`.
3. Obtener `face_data` y extraer `nose_tip`.
4. Llamar a `MouseController.update(nose_x, nose_y)`.
5. `MouseController` calcula el desplazamiento relativo y lo envía a `MouseDriver`.
6. `MouseDriver` usa `pyautogui` para aplicar el movimiento real.

## Qué se hizo

En el proyecto se creó/ajustó la arquitectura de control de mouse para que sea modular y reutilizable:

- `MouseDriver` centraliza el acceso a `pyautogui`.
- `MouseController` encapsula la lógica de joystick, dead zone y suavizado.
- `simple_exponential_smoothing` hace el movimiento más suave.
- `cursor_mapper` ofrece una base para convertir mirada normalizada a coordenadas de pantalla.
- `FaceDetector` suministra el punto de la nariz y otras métricas al flujo de entrada.

## Cómo utilizarlo

- Si quieres usar el mouse relativo con la nariz, debes tener un módulo que:
  - detecte `nose_tip`
  - llame a `MouseController.update(nose_x, nose_y)`
- Si quieres usar mirada absoluta, puedes combinar `cursor_mapper` con `MouseDriver.move_to(...)`.

## Recomendaciones

- Para un demo independiente debes ejecutar desde el directorio raíz del proyecto, de modo que `vision` y `core` estén en el `PYTHONPATH`.
- Si se añade una interfaz visual (overlay), se puede usar `Overlay` para mostrar el vector de movimiento y la dead zone.

---

Este archivo documenta la capa de control de mouse y los componentes principales que se construyeron o ajustaron para que el movimiento del cursor funcione dentro del proyecto general.
