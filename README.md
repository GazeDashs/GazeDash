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
