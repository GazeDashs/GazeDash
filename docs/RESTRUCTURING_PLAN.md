# Plan de reestructuracion propuesto

Este plan propone ordenar el proyecto sin romper todo de una vez. La estrategia es documentar, estabilizar y migrar por partes.

## Objetivo de la nueva estructura

Separar claramente:

- La aplicacion principal GazeDash.
- Los modulos reutilizables de vision, gestos, cursor y calibracion.
- Los prototipos o demos como FaceSnake y el mouse analogico.
- Los assets, configuracion, tests y documentacion.

## Estructura objetivo sugerida

```text
GazeDash/
├── gazedash/
│   ├── app/
│   │   ├── main.py
│   │   └── controller.py
│   ├── core/
│   │   ├── state.py
│   │   ├── calibration/
│   │   ├── cursor/
│   │   └── gestures/
│   ├── vision/
│   │   ├── camera/
│   │   ├── face/
│   │   └── eyes/
│   ├── ui/
│   ├── config/
│   ├── storage/
│   └── utils/
├── demos/
│   ├── face_snake/
│   └── analog_mouse/
├── assets/
│   └── models/
├── tests/
├── docs/
├── requirements.txt
└── README.md
```

## Mapeo desde la estructura actual

| Actual | Destino sugerido | Motivo |
| --- | --- | --- |
| `app/` | `gazedash/app/` | Punto de entrada y controlador principal. |
| `core/` | `gazedash/core/` | Logica de dominio e interaccion. |
| `vision/` | `gazedash/vision/` | Captura y procesamiento visual. |
| `ui/` | `gazedash/ui/` | Interfaz de usuario. |
| `config/` | `gazedash/config/` o `config/` | Configuracion versionada. |
| `storage/` | `gazedash/storage/` o directorio de datos local | Configuracion de usuario y persistencia. |
| `utils/` | `gazedash/utils/` | Helpers compartidos. |
| `Gazedash/` | `demos/face_snake/` | Demo funcional, separada de la app principal. |
| `analogico-mouse/` | `demos/analog_mouse/` | Prototipo funcional independiente. |
| `Gazedash/assets/face_landmarker.task` | `assets/models/face_landmarker.task` | Modelo compartido por vision. |

## Fases sugeridas

### Fase 1 - Preparar el terreno

- Agregar `__init__.py` donde haga falta para convertir carpetas en paquetes importables.
- Agregar `.gitignore` para `.venv/`, `__pycache__/`, `.pytest_cache/` y archivos locales.
- Consolidar dependencias en un unico archivo.
- Agregar tests de logica pura antes de mover archivos.

### Fase 2 - Aislar demos

- Mover `Gazedash/` a `demos/face_snake/`.
- Mover `analogico-mouse/` a `demos/analog_mouse/`.
- Ajustar imports de FaceSnake para que sean relativos o para que usen su paquete demo.
- Encapsular `analogico.py` con `main()` y `if __name__ == "__main__"`.

### Fase 3 - Crear paquete principal

- Crear `gazedash/`.
- Mover los modulos raiz actuales dentro de `gazedash/`.
- Cambiar `app/main.py` por un entrypoint claro, por ejemplo `python -m gazedash.app.main`.
- Mantener wrappers temporales si se necesita compatibilidad.

### Fase 4 - Reutilizar codigo de prototipos

- Extraer de FaceSnake:
  - Detector MediaPipe reutilizable.
  - Calculo de metricas faciales.
  - Mapper de gestos faciales.
- Extraer de analog mouse:
  - Joystick facial basado en nariz.
  - Deteccion de clicks por parpadeo.
  - Adaptador de salida a `pyautogui`.

### Fase 5 - Integrar la aplicacion principal

- `AppController` deberia coordinar:
  - Captura de camara.
  - Deteccion de cara/ojos/gestos.
  - Calibracion.
  - Mapeo a cursor o acciones.
  - UI y configuracion.
- La UI deberia consumir estado del sistema, no calcular vision directamente.

## Orden recomendado de implementacion

1. Agregar `.gitignore` y tests iniciales.
2. Proteger `analogico.py` para que no ejecute al importar.
3. Convertir FaceSnake en demo importable con imports limpios.
4. Crear paquete `gazedash/`.
5. Mover modulos placeholder al paquete.
6. Extraer servicios reutilizables desde demos.
7. Conectar la app principal con los servicios reales.

## Checks despues de cada movimiento

Ejecutar estos chequeos despues de cada fase:

```bash
python -m compileall app core vision ui config utils
python -m compileall Gazedash
python -m compileall analogico-mouse
```

Cuando existan tests:

```bash
pytest
```

Para FaceSnake:

```bash
cd Gazedash
python main.py --no-cam
```

## Decisiones pendientes

- Si GazeDash sera una app de escritorio, un servicio en background o ambas cosas.
- Si la configuracion de usuario debe vivir dentro del repo o en una carpeta del sistema.
- Si FaceSnake queda como demo permanente o solo como experimento historico.
- Si se usara `requirements.txt` o `pyproject.toml`.
- Si MediaPipe sera la unica base de vision o habra adaptadores alternativos.
 - Si las acciones derivadas de gestos deben enviarse como hotkeys al sistema (`pyautogui`) o como eventos internos del proceso. Actualmente el proyecto envía `hotkey`s por defecto; considerar añadir un `event_bus` interno si se quieren consumir gestos directamente dentro de demos/juegos sin depender del foco de ventana.

