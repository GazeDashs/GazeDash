# GazeDash

Software de accesibilidad para utilizar funciones de la computadora a traves de gestos faciales y movimientos de cabeza.

## Estado actual

El repositorio contiene una estructura base para la aplicacion principal y dos prototipos funcionales:

- `app/`, `core/`, `vision/`, `ui/`, `config/`, `storage/`, `utils/`: base modular de GazeDash, todavia mayormente placeholder.

## Documentacion

- [Mapa del proyecto](docs/PROJECT_OVERVIEW.md)
- [Plan de reestructuracion](docs/RESTRUCTURING_PLAN.md)

## Ejecutar aplicacion base

```bash
python -m app.main
```

La aplicacion base abre la ventana principal en CustomTkinter con accesos a configuracion y calibracion.
