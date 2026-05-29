# Módulos y funciones del proyecto

Este documento resume qué hace cada módulo del repositorio y cuáles son sus funciones o clases públicas principales. Está pensado como mapa rápido del código actual.

## `app/`

### `app/main.py`
Punto de entrada de la aplicación principal.

Funciones:
- `main()`: crea `AppController` y ejecuta el loop principal.

### `app/app_controller.py`
Controlador principal de la app de escritorio.

Clases y funciones:
- `AppController.__init__()`: inicializa cámara, detector facial y detector de gestos.
- `AppController.run()`: lee frames, procesa la detección y dibuja la interfaz OpenCV.
- `AppController._draw_face_metrics()`: pinta métricas y estado de gestos sobre el frame.

## `core/`

### `core/system_state.py`
Representa el estado global simple del sistema.

Clases y funciones:
- `SystemState`: mantiene el estado `active` o `paused`.
- `SystemState.pause()`: cambia el estado a pausa.
- `SystemState.resume()`: vuelve al estado activo.

### `core/calibration/calibration_model.py`
Guarda puntos de calibración entre mirada y posición de pantalla.

Clases y funciones:
- `CalibrationModel`: contenedor de puntos de calibración.
- `CalibrationModel.add_point(gaze, screen_point)`: agrega una pareja de valores a la colección.

### `core/calibration/calibration_service.py`
Servicio base para orquestar calibración de mirada.

Clases y funciones:
- `CalibrationService`: servicio envoltorio para calibración.
- `CalibrationService.start()`: punto de inicio del flujo de calibración. Actualmente es placeholder.

### `core/cursor_control/cursor_mapper.py`
Convierte una mirada normalizada en coordenadas de pantalla.

Funciones:
- `map_gaze_to_cursor(gaze_point, screen_size)`: transforma `(x, y)` normalizado a píxeles.

### `core/cursor_control/smoothing.py`
Suavizado básico para señales del cursor.

Funciones:
- `simple_exponential_smoothing(prev, current, alpha=0.5)`: aplica media exponencial simple.

### `core/gesture_engine/gesture_detector.py`
Detector de gestos y mapeo de acciones.

Notas:
- La detección concreta de métricas y gestos se implementa en `vision/gesture_detection/facial_gestures.py` (calibración neutral, debounce y umbrales). El flujo en `app` consume ese detector.
- `core/gesture_engine/gesture_mapper.py` carga la configuración activa y resuelve nombres de gestos a acciones.
- `core/gesture_engine/hotkey_executor.py` ejecuta acciones del tipo `hotkey` enviando teclas al sistema con `pyautogui`.
- `core/gesture_engine/cooldown_manager.py` evita activaciones repetidas de la misma acción.

### `core/gesture_engine/gesture_mapper.py`
Mapeo simple de nombres de gestos a acciones.

Variables y funciones:
- `DEFAULT_GESTURE_MAP`: diccionario con mapeos por defecto.
- `map_gesture(gesture_name)`: devuelve la acción asociada al gesto.

### `core/gesture_engine/cooldown_manager.py`
Evita activaciones repetidas de un mismo gesto.

Clases y funciones:
- `CooldownManager`: gestor de cooldown por clave.
- `CooldownManager.allow(key)`: retorna `True` si ya pasó el tiempo mínimo desde la última activación.

## `vision/`

### `vision/camera/camera_stream.py`
Funciones de cámara y captura de frames.

Funciones:
- `open_camera(index=0, width=640, height=480)`: abre la cámara con OpenCV y configura tamaño.
- `read_frame(cap, flip=True)`: lee un frame, opcionalmente lo espeja.
- `close_camera(cap)`: libera el recurso de cámara.

### `vision/eye_tracking/eye_detector.py`
Detector de ojos, actualmente placeholder.

Funciones:
- `detect_eyes(frame)`: retorna una lista vacía.

### `vision/eye_tracking/gaze_estimator.py`
Estimador de mirada (placeholder en `vision/mouse_controller/gaze_estimator.py`).

Funciones:
- `estimate_gaze(eye_landmarks)`: devuelve un punto normalizado; actualmente es un placeholder que retorna `(0.5, 0.5)`.

### `vision/face_tracking/face_detector.py`
Wrapper principal de MediaPipe Face Landmarker para la app raíz.

Clases y funciones:
- `FaceLandmarks`: índices de landmarks faciales usados por el proyecto.
- `MediaPipeFaceDetector.__init__(...)`: inicializa el modelo, el modo de ejecución y el callback opcional.
- `MediaPipeFaceDetector.enqueue_frame(frame)`: envía un frame al pipeline en modo live stream.
- `MediaPipeFaceDetector.get_latest_result(frame=None)`: devuelve el último resultado y, si recibe `frame`, lo convierte a diccionario de métricas.
- `MediaPipeFaceDetector.detect(frame)`: procesa un frame y devuelve un diccionario con métricas faciales.
- `MediaPipeFaceDetector.close()`: cierra el detector.
- `detect_faces(frame)`: función de compatibilidad que crea un detector, procesa un frame y lo cierra.

Helpers internos relevantes:
- `_on_result(...)`: callback de MediaPipe para guardar el último resultado.
- `_detect_face(...)`: ejecuta la detección en modo `LIVE_STREAM` o `VIDEO`.
- `_extract_blendshapes(...)`: convierte las categorías de blendshapes a diccionario.
- `_select_blendshapes(...)`: filtra blendshapes de interés.
- `_top_blendshapes(...)`: ordena y devuelve las principales puntuaciones.
- `_draw_face_mesh(...)`, `_draw_delaunay_mesh(...)`, `_draw_key_landmarks(...)`: dibujo de overlays.

### `vision/gesture_detection/facial_gestures.py`
Convierte métricas faciales en gestos discretos para la app.

Clases y funciones:
- `FacialGestureThresholds`: valores umbral por defecto.
- `FacialGestureDetector.__init__(thresholds=None)`: carga umbrales desde memoria o desde la configuración fusionada de `config/default_config.json` y `config/user_settings.json`.
- `FacialGestureDetector.detect(face_data)`: decide si hay `mouth_pucker`, `mouth_open` o `brow_raise`.
- `detect_facial_gestures(face_data)`: atajo para crear el detector y ejecutar `detect()`.

## `ui/`

### `ui/main_window.py`
Ventana principal de la UI con CustomTkinter.

Funciones:
- `create_main_window()`: punto de entrada de la ventana principal.

### `ui/config_panel.py`
Panel de configuración con CustomTkinter.

Funciones:
- `open_config_panel()`: abre el panel de configuración.

### `ui/calibration_screen.py`
Pantalla de calibración con CustomTkinter.

Funciones:
- `show_calibration()`: muestra la pantalla de calibración.

### `ui/components/buttons.py`
Componentes reutilizables de botones.

Funciones:
- `create_button(parent, text, command)`: crea un botón reutilizable.

### `ui/components/sliders.py`
Componentes reutilizables de sliders.

Funciones:
- `create_slider(parent, from_, to, command=None)`: crea un slider reutilizable.

### `ui/tools/calibrate_gestures.py`
Herramienta interactiva para calibrar umbrales de gestos.

Funciones:
- `load_settings()`: carga `config/user_settings.json` o valores por defecto.
- `save_settings(settings)`: guarda umbrales en `config/user_settings.json`.
- `main()`: ejecuta la UI de calibración con cámara y teclado.

### `ui/tools/dump_blendshapes_camera.py`
Herramienta de diagnóstico para listar blendshapes detectadas por la cámara.

Funciones:
- `main()`: abre cámara, ejecuta Face Landmarker y imprime nombres y valores de blendshapes.

## `config/`

### `config/config_manager.py`
Gestión simple de configuración persistente en JSON.

Clases y funciones:
- `ConfigManager.__init__(path)`: define el archivo de configuración.
- `ConfigManager.load_defaults()`: carga `default_config.json` si existe.
- `ConfigManager.load()`: carga el JSON de usuario o devuelve `{}` si no existe.
- `ConfigManager.load_merged()`: fusiona defaults con overrides de usuario.
- `ConfigManager.get_profile(profile_name=None)`: devuelve el perfil activo o el solicitado.
- `ConfigManager.save(cfg)`: guarda la configuración en disco con codificación UTF-8.

## `utils/`

### `utils/filters.py`
Filtros básicos de señal.

Funciones:
- `moving_average(values, n=3)`: calcula una media móvil simple.

### `utils/math_utils.py`
Utilidades matemáticas pequeñas.

Funciones:
- `clamp(v, lo, hi)`: limita un valor dentro de un rango.

### `utils/logger.py`
Logger simple para el proyecto.

Funciones:
- `get_logger(name=__name__)`: crea o reutiliza un logger con `StreamHandler`.

## `Gazedash/` - demo FaceSnake

### `Gazedash/main.py`
Punto de entrada del juego FaceSnake.

Funciones:
- `parse_args()`: parsea argumentos de línea de comandos.
- `main()`: construye la configuración, ejecuta el controlador y cierra `pygame`.

### `Gazedash/core/config.py`
Configuración central del juego FaceSnake.

Clases y funciones:
- `Config`: dataclass con parámetros de ventana, cámara, juego, colores y umbrales.
- `Config.grid_cols`: propiedad con columnas del tablero.
- `Config.grid_rows`: propiedad con filas del tablero.
- `Config.face_landmarker_model_path`: propiedad con la ruta al modelo de MediaPipe.

### `Gazedash/core/controller.py`
Orquestador del juego FaceSnake.

Clases y funciones:
- `GameController.__init__(config)`: inicializa juego, renderer, mapper y detector.
- `GameController.run()`: loop principal de eventos, detección, lógica y render.
- `GameController._handle_events()`: procesa teclado y cierre de ventana.

### `Gazedash/face/detector.py`
Detector facial usado por FaceSnake.

Clases y funciones:
- `LM`: índices de landmarks usados por el juego.
- `FaceDetector.__init__(config)`: asegura el modelo, abre la cámara y crea el Face Landmarker.
- `FaceDetector._ensure_model_file(model_path)`: descarga el modelo si no existe.
- `FaceDetector.process_frame()`: lee un frame, extrae métricas faciales y devuelve `(frame, face_data)`.
- `FaceDetector._draw_landmarks(frame, face_landmarks, h, w)`: dibuja puntos clave sobre el frame.
- `FaceDetector.__del__()`: libera cámara y detector al destruirse.

### `Gazedash/face/gesture_mapper.py`
Mapea métricas faciales a direcciones del juego.

Clases y funciones:
- `GestureMapper.__init__(config)`: configura hold frames, EMA y estado de gestos.
- `GestureMapper.get_direction(face_data)`: decide una dirección a partir de métricas faciales.
- `GestureMapper.get_gesture_state()`: devuelve el estado actual de los gestos.
- `GestureMapper._reset_holds()`: reinicia contadores cuando no hay cara.

### `Gazedash/game/snake.py`
Lógica pura del Snake.

Clases y funciones:
- `Direction`: enum con `UP`, `DOWN`, `LEFT`, `RIGHT`.
- `Direction.opposite()`: devuelve la dirección opuesta.
- `GameState`: enum con `PLAYING`, `PAUSED`, `DEAD`, `WAITING`.
- `SnakeGame.__init__(config)`: inicializa el juego.
- `SnakeGame.reset()`: reinicia el tablero, la serpiente y la comida.
- `SnakeGame.set_direction(new_dir)`: cambia dirección evitando reversa directa.
- `SnakeGame.toggle_pause()`: alterna pausa/continuación.
- `SnakeGame.update()`: avanza una iteración del juego.
- `SnakeGame._die()`: marca el juego como muerto.
- `SnakeGame._spawn_food()`: genera una nueva posición de comida.
- `SnakeGame.head`: propiedad con la cabeza de la serpiente.
- `SnakeGame.length`: propiedad con la longitud actual.

### `Gazedash/game/renderer.py`
Renderizado del juego y de la UI de FaceSnake.

Clases y funciones:
- `Renderer.__init__(config)`: crea ventana, fuentes y posiciones de UI.
- `Renderer.draw(...)`: dibuja juego, preview de cámara, overlays y debug.
- `Renderer._draw_grid()`: dibuja la grilla.
- `Renderer._draw_snake(game)`: dibuja la serpiente.
- `Renderer._draw_food(game)`: dibuja la comida.
- `Renderer._draw_ui_bar(game, gesture_state)`: dibuja barra de estado y gestos.
- `Renderer._draw_cam_preview(cam_frame, face_data, gesture_state)`: dibuja la cámara.
- `Renderer._draw_overlay(title, subtitle="")`: dibuja overlays de pausa/game over.
- `Renderer._draw_debug(face_data, gesture_state)`: dibuja panel de depuración.

## `analogico-mouse/`

### `analogico-mouse/analogico.py`
Prototipo independiente de mouse asistivo controlado con nariz y parpadeos.

Funciones:
- `eye_ratio(top, bottom)`: calcula una métrica simple de apertura del ojo.

Comportamiento del script:
- Abre la cámara.
- Detecta landmarks con MediaPipe Face Mesh o Face Landmarker como fallback.
- Usa la nariz como joystick relativo.
- Ejecuta clicks izquierdo y derecho por cierre sostenido de ojos.
- Dibuja una interfaz de depuración en OpenCV.

## Notas generales

- Muchos módulos de la carpeta raíz son placeholders y todavía no tienen lógica completa.
- El flujo funcional más completo hoy está en `vision/`, `app/` y en el demo `Gazedash/`.
- La herramienta `ui/tools/calibrate_gestures.py` sigue siendo útil aunque la UI principal todavía no esté integrada.