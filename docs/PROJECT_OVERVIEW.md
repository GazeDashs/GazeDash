# GazeDash - Documentacion del proyecto

Este documento describe el estado actual del repositorio para poder reorganizarlo con criterio mas adelante. La idea es separar que existe hoy, que esta funcionando, que es placeholder y que conviene mover o fusionar.

## Objetivo del proyecto

GazeDash apunta a ser una herramienta de accesibilidad para controlar funciones de la computadora mediante mirada, gestos faciales y movimientos de cabeza.

Actualmente el repositorio contiene tres lineas de trabajo:

- `app/`, `core/`, `vision/`, `ui/`, `config/`, `storage/`, `utils/`: estructura base modular para la aplicacion principal GazeDash. La mayoria de estos archivos son placeholders o implementaciones minimas.
- `Gazedash/`: subproyecto funcional llamado FaceSnake, un juego Snake controlado con gestos faciales y teclado como fallback.
- `analogico-mouse/`: prototipo independiente de joystick/mouse asistivo controlado con nariz y parpadeos.

## Estado actual por zona

### Aplicacion principal en raiz

Punto de entrada:

- `app/main.py`: crea `AppController` y llama a `run()`.
- `app/app_controller.py`: controlador principal placeholder; por ahora solo imprime `AppController running`.

Modulos de dominio:

- `core/system_state.py`: maneja estados simples `active` y `paused`.
- `core/calibration/calibration_model.py`: guarda pares `(gaze, screen_point)` para calibracion.
- `core/calibration/calibration_service.py`: servicio de calibracion sin implementar.
- `core/cursor_control/cursor_mapper.py`: convierte un punto normalizado `(x, y)` a coordenadas de pantalla.
- `core/cursor_control/smoothing.py`: suavizado exponencial simple.
- `core/gesture_engine/gesture_detector.py`: placeholder para detectar gestos.
- `core/gesture_engine/gesture_mapper.py`: mapea nombres de gestos a acciones. Actualmente `blink -> click`.
- `core/gesture_engine/cooldown_manager.py`: evita activaciones repetidas usando cooldown por clave.

Vision:

- `vision/camera/camera_stream.py`: manejo de cámara y captura de frames con OpenCV.
- `vision/mouse_controller/gaze_estimator.py`: estimador de mirada placeholder (devuelve punto fijo `(0.5, 0.5)`).
- `vision/face_tracking/face_detector.py`: wrapper de MediaPipe Face Landmarker que extrae métricas faciales y dibuja overlays.
- `vision/gesture_detection/facial_gestures.py`: detector de gestos faciales con calibración neutral y debounce; implementa detección de gestos como `smile`, `mouth_open`, `brow_raise`, `eye_blink`, `eye_wide`, `nose_sneer`, etc.

Nota: hay múltiples implementaciones prototipo en carpetas diferentes (p. ej. `vision/mouse_controller` y `analogico-mouse`). Revisa la ruta concreta del módulo cuando integres o muevas código.

UI:

- `ui/main_window.py`: ventana principal en CustomTkinter con accesos a configuracion y calibracion.
- `ui/config_panel.py`: panel de configuracion en CustomTkinter.
- `ui/calibration_screen.py`: pantalla de calibracion en CustomTkinter.
- `ui/components/buttons.py`: helper reutilizable para botones.
- `ui/components/sliders.py`: helper reutilizable para sliders.

Configuracion y persistencia:

- `config/default_config.json`: configuracion base con el perfil activo por defecto `navegacion`, valores de `smoothing_alpha`, `gesture_cooldown`, `camera_index` y el bloque de acciones/umbrales del perfil `Navegación`.
- `config/config_manager.py`: carga y guarda JSON, y permite fusionar la configuracion base con overrides de usuario.
- `config/user_settings.json`: configuracion del usuario, actualmente usada como override de umbrales o perfil activo.
Nota sobre ejecución de acciones: el mapeo de gestos a acciones se realiza mediante `core/gesture_engine/gesture_mapper.py` y las acciones tipo `hotkey` se envían al sistema usando `core/gesture_engine/hotkey_executor.py` (usa `pyautogui`). Esto significa que las teclas producidas por gestos llegan a la ventana que tenga foco — las aplicaciones/juegos deben tener foco para recibirlas.

Utilidades:

- `utils/filters.py`: media movil.
- `utils/math_utils.py`: `clamp`.
- `utils/logger.py`: logger simple con `logging`.

### FaceSnake en `Gazedash/`

Este subproyecto si contiene una aplicacion ejecutable.

Punto de entrada:

- `Gazedash/main.py`: parsea argumentos, crea `Config`, inicializa `GameController` y cierra `pygame` al finalizar.

Flujo principal:

1. `GameController` procesa eventos de teclado y ventana.
2. `FaceDetector` captura un frame de camara y calcula metricas faciales.
3. `GestureMapper` convierte metricas faciales en una direccion del juego.
4. `SnakeGame` actualiza estado, colisiones, comida y puntaje.
5. `Renderer` dibuja tablero, camara, UI, overlays y debug.

Componentes:

- `Gazedash/core/config.py`: dataclass con parametros del juego, camara, umbrales y colores.
- `Gazedash/core/controller.py`: orquestador del loop.
- `Gazedash/face/detector.py`: usa OpenCV y MediaPipe Face Landmarker. Calcula `yaw`, `brow_ratio`, `mouth_ratio` y dibuja puntos clave.
- `Gazedash/face/gesture_mapper.py`: traduce giro de cabeza, cejas y boca a direcciones.
- `Gazedash/game/snake.py`: logica pura del Snake, sin `pygame`.
- `Gazedash/game/renderer.py`: render con `pygame` y preview de camara con OpenCV.
- `Gazedash/assets/face_landmarker.task`: modelo de MediaPipe usado por el detector.

Comandos utiles:

```bash
cd Gazedash
python main.py --no-cam
python main.py --debug
python main.py --cam 1
```

Dependencias:

- `mediapipe`
- `opencv-python`
- `pygame`
- `numpy`

### Prototipo de mouse en `analogico-mouse/`

Este prototipo es un script independiente.

Archivo principal:

- `analogico-mouse/analogico.py`

Responsabilidades actuales:

- Abre la camara con OpenCV.
- Detecta landmarks faciales con MediaPipe Face Mesh o Face Landmarker como fallback.
- Usa la nariz como joystick relativo.
- Mueve el cursor con `pyautogui.moveRel`.
- Detecta cierre de ojo izquierdo para click izquierdo.
- Detecta cierre de ojo derecho para click derecho.
- Muestra ventana de debug con OpenCV.

Dependencias:

- `mediapipe`
- `opencv-python`
- `numpy`
- `pyautogui`

Notas:

- La logica esta concentrada en un solo archivo.
- Tiene configuracion global al inicio del script.
- Para integrarlo a GazeDash conviene separarlo en servicios: camara, landmarks, joystick facial, clicks y salida de cursor.

## Dependencias observadas

Dependencias del `requirements.txt` raiz:

- `opencv-python`
- `numpy`

Dependencias adicionales usadas por subproyectos:

- `mediapipe`
- `pygame`
- `pyautogui`

Cuando se unifique el proyecto, conviene consolidar un solo `requirements.txt` o pasar a un archivo `pyproject.toml`.

## Riesgos antes de reestructurar

- Hay carpetas con nombres muy parecidos: `GazeDash` como repo, `Gazedash/` como subproyecto. Esto puede confundir imports y rutas.
- El paquete raiz no tiene `__init__.py` en varias carpetas, mientras `Gazedash/` si usa imports internos simples como `from core.config import Config`.
- `Gazedash/` depende de correr desde su propia carpeta o de tener el path correcto; al moverlo pueden romperse imports relativos.
- `analogico-mouse/analogico.py` ejecuta el loop al importar el archivo porque no tiene guard `if __name__ == "__main__"`.
- Hay artefactos locales como `.venv/` y caches de Python en el workspace. No deberian formar parte de la arquitectura del proyecto.
- No se observaron tests automatizados.

## Convenciones recomendadas antes de mover codigo

- Definir una sola aplicacion principal.
- Evitar mezclar prototipos ejecutables con modulos importables.
- Separar dominio puro de integraciones externas:
  - Dominio: calibracion, mapeo, gestos, estados.
  - Infraestructura: camara, MediaPipe, `pyautogui`, archivos.
  - UI: ventanas, paneles y visualizacion.
- Encapsular scripts ejecutables en funciones `main()`.
- Agregar tests primero para logica pura: mapeo de gestos, cooldowns, smoothing, Snake.

