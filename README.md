# GazeDash

Software de accesibilidad para utilizar funciones de la computadora a traves de gestos faciales, movimientos de cabeza y mirada.

## Estado actual

El repositorio contiene una estructura base para la aplicacion principal y dos prototipos funcionales:

- `app/`, `core/`, `vision/`, `ui/`, `config/`, `storage/`, `utils/`: base modular de GazeDash, todavia mayormente placeholder.
- `Gazedash/`: demo FaceSnake, un Snake controlado con gestos faciales.
- `analogico-mouse/`: prototipo de mouse/joystick asistivo con nariz y parpadeos.

## Documentacion

- [Mapa del proyecto](docs/PROJECT_OVERVIEW.md)
- [Plan de reestructuracion](docs/RESTRUCTURING_PLAN.md)

## Ejecutar aplicacion base

```bash
python -m app.main
```

La aplicacion base abre la ventana principal en CustomTkinter con accesos a configuracion y calibracion.

## Ejecutar FaceSnake

```bash
cd Gazedash
python main.py --no-cam
python main.py --debug
```

## Dependencias

El `requirements.txt` raiz incluye dependencias minimas. Los prototipos tienen sus propios `requirements.txt`; antes de reestructurar conviene consolidarlos.
