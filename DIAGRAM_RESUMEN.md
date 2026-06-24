# Diagrama de clases (resumido)

Versión compacta sin atributos, pensada para captura en el informe y la presentación.

```mermaid
classDiagram
    direction TB

    %% Controladores (orquestación)
    class ControladorMonitoreo {
        +ejecutar()
    }
    class ControladorHilos {
        +ejecutar()
    }
    class ControladorProcesos {
        +ejecutar()
    }

    %% Dominio
    class EstacionAmbiental {
        +generar_ciclo()
    }
    class AnalizadorDatos {
        +procesar_ciclo()
        +resumen()
    }
    class VariableConfig {
        +riesgo()
    }

    %% Modelos de datos
    class Medicion
    class AlertaAmbiental
    class EstadisticasVariable
    class ResultadoEjecucion

    %% Eventos
    class Evento

    %% GUI
    class VentanaPrincipal {
        +iniciar()
    }
    class WorkerSimulacion {
        +run()
    }

    %% Herencia
    ControladorHilos --|> ControladorMonitoreo
    ControladorProcesos --|> ControladorMonitoreo

    %% Composición
    ControladorMonitoreo "1" *-- "N" EstacionAmbiental
    ControladorMonitoreo "1" *-- "1" AnalizadorDatos
    VentanaPrincipal "1" *-- "1" WorkerSimulacion

    %% Dependencias
    EstacionAmbiental ..> Medicion : genera
    EstacionAmbiental ..> VariableConfig : usa
    AnalizadorDatos ..> EstadisticasVariable : calcula
    ControladorMonitoreo ..> AlertaAmbiental : crea
    ControladorMonitoreo ..> ResultadoEjecucion : produce
    ControladorMonitoreo ..> Evento : emite
    WorkerSimulacion ..> ControladorMonitoreo : ejecuta
    WorkerSimulacion ..> Evento : reemite como señal
```

**Leyenda:** `--|>` herencia · `*--` composición · `..>` dependencia (crea/usa/emite).
