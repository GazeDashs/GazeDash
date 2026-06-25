# GazeDash

Software de accesibilidad que permite controlar la computadora mediante **gestos faciales**, **movimiento de nariz/cabeza** y **comandos de voz**, usando una cámara web estándar como único hardware adicional.

---

## Estado actual — versión 0.3

GazeDash es una **aplicación funcional** con UI completa, detección facial en tiempo real, mouse por nariz, clic por guiño, gestos configurables y módulo de voz integrado.

### Funcionalidades operativas

| Funcionalidad | Estado |
|---|---|
| App de escritorio (CustomTkinter) | ✅ Completo |
| Detección facial con MediaPipe (landmarks + blendshapes) | ✅ Completo |
| Gestos faciales: boca, sonrisa, cejas, guiño, nariz | ✅ Funcional (ajuste en curso) |
| Mapeo gesto → hotkey/clic/tecla sostenida por perfil | ✅ Completo |
| Mouse por nariz (joystick relativo, recalibrable) | ✅ Completo |
| Clic izquierdo/derecho por guiño | ✅ Funcional |
| Sistema de perfiles (gestos + umbrales + voz + mouse) | ✅ Completo |
| Perfiles base: Accesibilidad PC y Juego simple | ✅ Completo |
| Calibración de umbrales — vista embebida con sliders | ✅ Completo |
| Control de voz — arquitectura ML con máquina de estados | ✅ Integrado (requiere modelos) |
| Feedback visual de voz en tiempo real | ✅ Completo |
| Toggle de voz y mouse desde Configuración | ✅ Completo |
| UI rediseñada: sidebar + 4 vistas (Inicio/Config/Calibración/Voz) | ✅ Completo |
| Mini overlay al minimizar (gesto + estado de voz) | ✅ Completo |
| Diagnóstico de gestos crudos/ganadores/descartados | ✅ Completo |
| Logs JSONL de diagnóstico por sesión | ✅ Completo |
| Control por mirada estimada | 🔲 Pendiente |
| Tests automatizados | 🔲 Pendiente |

---

## Estructura del proyecto

```
GazeDash/
├── app/              # Punto de entrada (app.main)
│   ├── main.py
│   └── app_controller.py
├── core/             # Lógica de control
│   ├── gesture_engine/   # Cooldown, mapper, hotkey executor
│   ├── input/            # MouseController, BlinkClickController
│   ├── voice_control/    # VoiceCommandController (máquina de estados)
│   └── calibration/      # Servicios de calibración
├── vision/           # Visión por computadora
│   ├── camera/           # CameraStream
│   ├── face_tracking/    # MediaPipeFaceDetector
│   └── gesture_detection/# FacialGestureDetector (con calibración neutral)
├── ui/               # Interfaz gráfica
│   ├── main_window.py    # Ventana principal (~1900 líneas)
│   ├── settings_store.py # Acceso compartido a configuración
│   └── components/       # Widgets reutilizables
├── config/           # Configuración JSON
│   ├── default_config.json
│   └── user_settings.json
├── assets/
│   └── models/modelos_v2/  # Modelos ML de voz (.pkl)
└── Gazedash/         # Demo FaceSnake (prototipo independiente)
```

---

## Ejecutar

```bash
python -m app.main
```

Requiere Python ≥ 3.10 y las dependencias de `requirements.txt`.

---

## Dependencias principales

```
opencv-python, mediapipe, customtkinter, numpy
pyautogui, Pillow
librosa, sounddevice, soundfile       # voz
scikit-learn, xgboost, pandas, joblib # modelos ML de voz
imbalanced-learn
```

> **Nota**: El módulo de voz funciona solo si los modelos `.pkl` están en `assets/models/modelos_v2/` y las dependencias de audio están instaladas.

---

## Arquitectura de la UI (v0.3)

La ventana principal (`GazeDashApp`) usa una **sidebar fija** con navegación entre 4 vistas internas (sin ventanas secundarias para las vistas principales):

- **Inicio**: preview de cámara, badge de gesto, métricas faciales, panel de "Voz en vivo" (estado / módulo activo / último comando / advertencia de confianza baja)
- **Configuración**: tabs Gestos→Acciones / Perfiles / Mouse; toggle de voz; panel derecho con resumen de mouse y perfiles
- **Calibración**: sliders por gesto en grid 2-col, selector de perfil, auto-calibrar, guardar/restaurar
- **Voz**: módulos de activación, sliders de audio, diagnóstico de micrófono y modelos

El **mini overlay** (al minimizar) muestra preview de cámara, gesto detectado y estado del módulo de voz. Es arrastrable.

---

## Gestos más confiables

El flujo de gestos ahora tiene una capa intermedia:

```
FacialGestureDetector → GestureArbiter → GestureMapper → HotkeyExecutor
```

`GestureArbiter` reduce confusiones entre gestos parecidos antes de ejecutar acciones:

- Boca: elige entre `mouth_pucker`, `mouth_o` y `mouth_open`.
- Sonrisa: elige entre `smile`, `smile_left` y `smile_right`.
- Ojos: elige entre `eye_wide` y `eye_blink`.
- Cejas: elige entre `brow_raise` y `brow_frown`.

Además aplica estabilidad temporal configurable en `gesture_arbitration`: frames para activar y frames para soltar. Esto evita disparos dobles y parpadeos de un frame.

La configuración base está en `config/default_config.json`:

```json
"gesture_arbitration": {
  "enabled": true,
  "activation_frames": 2,
  "hold_activation_frames": 1,
  "release_frames": 2,
  "hold_release_frames": 1,
  "activation_frames_by_gesture": {
    "mouth_o": 3,
    "smile": 3,
    "brow_raise": 3,
    "brow_frown": 3,
    "eye_blink": 3
  }
}
```

Reglas prácticas para ajustar:

- Si un gesto se activa por accidente, subir su `activation_frames_by_gesture`.
- Si un gesto se corta por ruido, subir su `release_frames_by_gesture`.
- Si un gesto se siente lento, bajar sus frames, pero hacerlo de a 1.
- Para juegos simples, mantener `hold_activation_frames` y `hold_release_frames` bajos para no agregar latencia.
- Si dos gestos se confunden dentro de un grupo, ajustar `priorities` o directamente quitar acción al gesto menos confiable en ese perfil.

### Diagnóstico en vivo

La vista **Inicio** muestra una tarjeta de diagnóstico junto al gesto activo:

- `Ganador`: gesto filtrado que puede ejecutar una acción.
- `Crudos`: gestos que el detector facial vio antes del arbitraje.
- `Descartados`: gestos rechazados por competir con otro gesto del mismo grupo.

Uso recomendado:

- Si `Crudos` muestra varios gestos al hacer uno solo, hay confusión de detector o umbral.
- Si el gesto correcto aparece en `Crudos` pero no en `Ganador`, ajustar `priorities` o los frames de activación.
- Si aparece `esperando nombre 1/3`, el gesto está siendo confirmado; bajar frames si se siente lento, subirlos si dispara por accidente.
- Si un gesto aparece seguido en `Descartados`, conviene quitarle acción en ese perfil o endurecerlo.

### Logs de sesión

GazeDash guarda eventos de diagnóstico en JSONL para revisar confusiones después de usar la app:

```
logs/gesture_diagnostics/gesture_diagnostics_ui_YYYYMMDD_HHMMSS.jsonl
```

Cada línea contiene:

- `profile`: perfil activo.
- `detected_gesture`: gesto filtrado mostrado/ejecutable.
- `debug.raw_active`: gestos crudos antes del arbitraje.
- `debug.active`: gestos ganadores.
- `debug.groups`: candidatos, descartados y frames de activación/liberación por grupo.

La configuración está en `gesture_diagnostics`:

```json
"gesture_diagnostics": {
  "enabled": true,
  "log_dir": "logs/gesture_diagnostics",
  "min_interval_seconds": 0.25,
  "only_log_changes": true
}
```

Uso recomendado:

- Si un gesto aparece seguido en `raw_active` pero nunca en `active`, revisar prioridades o frames.
- Si dos gestos aparecen juntos muchas veces, ajustar el grupo conflictivo o eliminar uno del perfil.
- Si `candidate_frames` no llega al requerido, bajar frames o mejorar calibración.
- Si el log crece mucho, subir `min_interval_seconds` o dejar `only_log_changes` en `true`.

Próximos pasos recomendados:

1. Agregar puntajes/confianza por gesto, no solo booleanos.
2. Separar umbral de activación y liberación dentro del detector facial.
3. Calibrar con ejemplos negativos para aprender confusores.
4. Crear una herramienta que resuma los logs y sugiera cambios de perfil.

---

## Módulo de voz

Implementa una máquina de estados (`VoiceControlState`):

```
DISABLED → WAITING_MODULE → MODULE_ACTIVE → LISTENING_COMMAND
```

Módulos disponibles: **Web**, **Multimedia**, **Navegación**, **Accesibilidad**.  
Requiere modelo de activación + modelos de comando por módulo (`.pkl` en `assets/models/modelos_v2/`).

---

## Pendiente (backlog priorizado)

| Prioridad | Tarea |
|---|---|
| P0 | Validar carga de modelos de voz en entorno limpio |
| P0 | Suite mínima de tests (config, gestos, hotkeys) |
| P1 | Hacer configurable el umbral de clic por guiño desde perfil |
| P2 | Implementar o retirar `activation_word` de voz |
| P2 | Medición formal de latencia y consumo de CPU |
| P3 | Estimación de mirada real y calibración de pantalla |
