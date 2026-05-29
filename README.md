# GazeDash

Proyecto de la feria de ciencias 2026.  
Software de accesibilidad que permite controlar funciones de la computadora a través de gestos faciales y movimientos de cabeza.

## Estado actual

El repositorio contiene la estructura base para la aplicación principal, diseñada en Python, pero la mayoría de los módulos aún son *placeholders* (esqueleto sin funcionalidad final implementada).  
Actualmente incluye lo siguiente:

- **Estructura modular de carpetas**:  
  - `app/`: entrada principal de la aplicación
  - `core/`, `vision/`, `ui/`, `config/`, `storage/`, `utils/`
- **Primeros prototipos funcionales (muy básicos)** orientados a la integración con *CustomTkinter* y vista de la ventana principal.

## Roadmap próximo

- Desarrollo de lógica central en los módulos `core` y `vision`
- Implementación de la detección de gestos y movimientos de cabeza
- Sistema de configuración y almacenamiento de preferencias
- Interfaz de usuario accesible personalizada

## Ejecución de la aplicación base

```bash
python -m app.main
```

La aplicación abre la ventana principal en CustomTkinter con accesos a configuración y calibración.  
Por ahora, estas funcionalidades son limitadas o simuladas mientras se avanza el desarrollo.
