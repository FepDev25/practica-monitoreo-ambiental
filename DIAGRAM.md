# Diagramas del Sistema de Monitoreo Ambiental Urbano (Cuenca)

Este documento contiene dos vistas del sistema:

1. **Diagrama de clases** — las clases del proyecto, sus atributos/métodos y relaciones.
2. **Diagrama de arquitectura** — las capas del sistema y el flujo de datos en tiempo de ejecución.

> Los diagramas usan [Mermaid](https://mermaid.js.org/). GitHub los renderiza automáticamente.

---

## 1. Diagrama de clases

```mermaid
classDiagram
    direction LR

    %% ===================== CAPA DOMINIO / CONFIG =====================
    class VariableConfig {
        +str nombre
        +str unidad
        +float media
        +float desviacion
        +float|None umbral_min
        +float|None umbral_max
        +float peso
        +riesgo(valor) float
    }

    class es_alerta {
        <<function>>
        +es_alerta(variable, valor) tuple~bool,str,float~
    }

    %% ===================== MODELOS DE DATOS =====================
    class Medicion {
        <<frozen dataclass>>
        +str estacion_id
        +str estacion_nombre
        +str zona
        +str variable
        +float valor
        +int ciclo
        +float tiempo
    }

    class AlertaAmbiental {
        <<frozen dataclass>>
        +str estacion_id
        +str zona
        +str variable
        +float valor
        +float umbral
        +str tipo
        +float severidad
        +int ciclo
        +float tiempo
    }

    class EstadisticasVariable {
        <<dataclass>>
        +str variable
        +float promedio
        +float maximo
        +float minimo
        +float desviacion
        +int total_mediciones
    }

    class ResultadoEjecucion {
        <<dataclass>>
        +str modo
        +int num_estaciones
        +int num_ciclos
        +int intensidad
        +float tiempo_total
        +float tiempo_promedio_ciclo
        +list tiempos_por_ciclo
        +int total_mediciones
        +float mediciones_por_segundo
        +int total_alertas
        +str|None zona_mayor_riesgo
        +dict indice_ambiental
        +dict estadisticas
    }

    %% ===================== GENERACION =====================
    class EstacionAmbiental {
        +str id
        +str nombre
        +str zona
        +tuple variables
        -Random _rng
        +int contador_mediciones
        +generar_medicion(variable, ciclo) Medicion
        +generar_ciclo(ciclo) list~Medicion~
    }

    %% ===================== PROCESAMIENTO =====================
    class AnalizadorDatos {
        +int intensidad
        +int ventana
        -Callable _mapper
        -int _n_particiones
        -dict _series
        -dict _riesgo_acum_zona
        -list _todas
        +procesar_ciclo(mediciones, ciclo) dict
        +configurar_paralelismo(mapper, n) void
        +resumen() dict
        -_indice_ambiental_compuesto(mediciones) dict
        -_suavizar(filas) list
        -_medias_moviles() dict
    }

    %% ===================== ORQUESTACION (CONTROLADORES) =====================
    class ControladorMonitoreo {
        +str MODO = "secuencial"
        +int num_estaciones
        +int num_ciclos
        +int intensidad
        +int ventana
        +list~EstacionAmbiental~ estaciones
        +AnalizadorDatos analizador
        +list~AlertaAmbiental~ alertas
        +list tiempos_por_ciclo
        +Callable on_evento
        +ejecutar() ResultadoEjecucion
        -_evaluar_alertas(mediciones, ciclo) void
        -_construir_resultado(t_total) ResultadoEjecucion
        -_emitir(evento) void
    }

    class ControladorHilos {
        +str MODO = "hilos"
        +ejecutar() ResultadoEjecucion
        %% usa Lock, Event, Barrier x2
    }

    class ControladorProcesos {
        +str MODO = "procesos"
        +ejecutar() ResultadoEjecucion
        %% usa Queue, Barrier x2, Event, Pool
    }

    %% ===================== EVENTOS =====================
    class EventoInicio {
        <<frozen dataclass>>
        +str modo
        +int num_estaciones
        +int num_ciclos
        +int intensidad
        +list estaciones
    }
    class EventoEstadoEstacion {
        <<frozen dataclass>>
        +str estacion_id
        +str estado
        +int ciclo
    }
    class EventoMedicion {
        <<frozen dataclass>>
        +str estacion_id
        +str zona
        +str variable
        +float valor
        +int ciclo
    }
    class EventoAlerta {
        <<frozen dataclass>>
        +str estacion_id
        +str zona
        +str variable
        +float valor
        +float umbral
        +str tipo
        +float severidad
        +int ciclo
    }
    class EventoCicloFin {
        <<frozen dataclass>>
        +int ciclo
        +float tiempo_ciclo
        +int mediciones_ciclo
        +int alertas_ciclo
        +dict indice_zona
    }
    class EventoFinSimulacion {
        <<frozen dataclass>>
        +float tiempo_total
        +int total_mediciones
        +int total_alertas
        +float mediciones_por_segundo
        +str|None zona_mayor_riesgo
        +dict indice_ambiental
    }

    %% ===================== BENCHMARK =====================
    class EjecucionRaw {
        <<dataclass>>
        +str configuracion
        +str modo
        +int repeticion
        +float tiempo_total
        +int total_mediciones
        +int total_alertas
    }
    class ResumenConfig {
        <<dataclass>>
        +str configuracion
        +float Ts
        +float Tthread
        +float Tprocess
        +float Sthread
        +float Sprocess
    }

    %% ===================== GUI =====================
    class WorkerSimulacion {
        <<QThread>>
        -type _clase
        -Event _stop
        +pyqtSignal medicion
        +pyqtSignal alerta
        +pyqtSignal ciclo_fin
        +pyqtSignal fin_simulacion
        +run() void
        +detener() void
        -_emitir(evento) void
    }

    class VentanaPrincipal {
        <<QMainWindow>>
        -WorkerSimulacion _worker
        -dict _controladores
        +_iniciar() void
        +_detener() void
        -_on_medicion(ev) void
        -_on_alerta(ev) void
        -_on_fin(ev) void
    }

    %% ===================== RELACIONES =====================
    ControladorHilos --|> ControladorMonitoreo : hereda
    ControladorProcesos --|> ControladorMonitoreo : hereda

    ControladorMonitoreo "1" *-- "N" EstacionAmbiental : compone
    ControladorMonitoreo "1" *-- "1" AnalizadorDatos : compone
    ControladorMonitoreo ..> AlertaAmbiental : crea
    ControladorMonitoreo ..> ResultadoEjecucion : produce
    ControladorMonitoreo ..> EventoMedicion : emite
    ControladorMonitoreo ..> EventoAlerta : emite
    ControladorMonitoreo ..> EventoCicloFin : emite
    ControladorMonitoreo ..> EventoFinSimulacion : emite

    EstacionAmbiental ..> Medicion : genera
    EstacionAmbiental ..> VariableConfig : usa

    AnalizadorDatos ..> Medicion : consume
    AnalizadorDatos ..> EstadisticasVariable : calcula
    AnalizadorDatos ..> VariableConfig : usa

    ControladorMonitoreo ..> es_alerta : invoca
    es_alerta ..> VariableConfig : consulta

    VentanaPrincipal "1" *-- "1" WorkerSimulacion : crea/gestiona
    WorkerSimulacion ..> ControladorMonitoreo : ejecuta
    WorkerSimulacion ..> EventoMedicion : reemite como señal

    ResumenConfig ..> EjecucionRaw : resume
```

### Notas del diagrama de clases

- **Herencia:** `ControladorHilos` y `ControladorProcesos` extienden a `ControladorMonitoreo` (que es a la vez la versión secuencial y la clase base). Solo redefinen `MODO` y `ejecutar()`; reutilizan `_evaluar_alertas`, `_construir_resultado` y `_emitir`.
- **Composición (`*--`):** el controlador *posee* sus estaciones y su analizador (su ciclo de vida depende de él).
- **Dependencia (`..>`):** "usa / crea / consume" sin poseer. Las estaciones *crean* mediciones, el analizador las *consume*, etc.
- **`<<frozen dataclass>>`:** objetos inmutables y picklables — clave para cruzar fronteras de hilos/procesos sin condiciones de carrera.

---

## 2. Diagrama de arquitectura

```mermaid
flowchart TB
    subgraph PRES["🖥️ Capa de Presentación (hilo principal / GUI)"]
        VP["VentanaPrincipal<br/>(QMainWindow)<br/>tabla, alertas, stats, entorno, cronómetro"]
    end

    subgraph PUENTE["🔌 Capa Puente (hilo worker)"]
        WS["WorkerSimulacion (QThread)<br/>ejecuta la simulación en 2.º plano<br/>traduce Evento → señal Qt"]
    end

    subgraph ORQ["🎛️ Capa de Orquestación (3 estrategias)"]
        CM["ControladorMonitoreo<br/>SECUENCIAL (línea base Ts)"]
        CH["ControladorHilos<br/>Lock · Event · Barrier×2<br/>(limitado por el GIL)"]
        CP["ControladorProcesos<br/>Queue · Barrier×2 · Event · Pool<br/>(paraleliza de verdad)"]
    end

    subgraph DOM["⚙️ Capa de Dominio (lógica de simulación)"]
        EST["EstacionAmbiental ×N<br/>genera mediciones (RNG aislado)"]
        AN["AnalizadorDatos<br/>media móvil + índice compuesto<br/>(SUAVIZADO = carga de CPU)"]
    end

    subgraph DATOS["📦 Capa de Datos / Dominio base"]
        CFG["config.py<br/>VariableConfig · umbrales · zonas<br/>riesgo() · es_alerta()"]
        MOD["modelos.py<br/>Medicion · AlertaAmbiental<br/>EstadisticasVariable · ResultadoEjecucion"]
        EV["eventos.py<br/>6 Eventos (frozen, picklables)"]
    end

    subgraph INFRA["🧰 Infraestructura / Medición"]
        ENT["entorno.py<br/>Python · SO · núcleos · GIL"]
        BENCH["benchmark/runner.py<br/>3 configs × 3 modos × 3 reps<br/>Ts, Tthread, Tprocess, Sthread, Sprocess"]
        CSV[("resultados/*.csv<br/>ejecuciones · resumen · entorno")]
    end

    %% Flujo principal GUI
    VP -- "1. Iniciar(modo, N, ciclos)" --> WS
    WS -- "2. ejecutar() con on_evento" --> CM
    WS -.-> CH
    WS -.-> CP

    %% Herencia conceptual
    CH -. hereda .-> CM
    CP -. hereda .-> CM

    %% Orquestación usa dominio
    CM -- "genera por ciclo" --> EST
    CM -- "procesar_ciclo()" --> AN
    EST -- "Medicion" --> CM

    %% Procesos: Pool e IPC
    CP == "Pool.map (suavizado en paralelo)" ==> AN
    CP == "Queue (IPC)" ==> EST

    %% Dominio usa datos base
    EST --> CFG
    EST --> MOD
    AN --> CFG
    AN --> MOD

    %% Eventos de vuelta hacia la GUI
    CM == "Evento (radio)" ==> WS
    WS == "señal Qt (thread-safe)" ==> VP
    EV -.-> CM

    %% Camino de medición (sin GUI)
    BENCH -- "ejecuta en silencio (on_evento=None)" --> CM
    BENCH --> ENT
    BENCH --> CSV
    VP --> ENT

    classDef pres fill:#E3F2FD,stroke:#1565C0,color:#0D47A1;
    classDef puente fill:#FFF3E0,stroke:#E65100,color:#BF360C;
    classDef orq fill:#F3E5F5,stroke:#6A1B9A,color:#4A148C;
    classDef dom fill:#E8F5E9,stroke:#2E7D32,color:#1B5E20;
    classDef datos fill:#FCE4EC,stroke:#AD1457,color:#880E4F;
    classDef infra fill:#ECEFF1,stroke:#455A64,color:#263238;

    class VP pres;
    class WS puente;
    class CM,CH,CP orq;
    class EST,AN dom;
    class CFG,MOD,EV datos;
    class ENT,BENCH,CSV infra;
```

### Flujo de ejecución (resumen)

1. **Inicio:** el usuario elige modo/parámetros en `VentanaPrincipal` y pulsa *Iniciar*.
2. **Aislamiento de hilo:** se lanza `WorkerSimulacion` (un `QThread`) para no congelar la interfaz; este instancia el controlador del modo elegido con `on_evento=self._emitir`.
3. **Simulación por ciclos:** el controlador coordina las `EstacionAmbiental` (generación) y el `AnalizadorDatos` (procesamiento con carga de CPU).
   - **Hilos:** estaciones en `Thread`, buffer compartido protegido con `Lock`, sincronización con `Barrier`/`Event`. El GIL impide acelerar el cómputo.
   - **Procesos:** estaciones en `Process` que envían datos por `Queue`; el suavizado pesado se reparte en un `Pool` → **aceleramiento real (~4×)**.
4. **Eventos de vuelta:** cada hecho relevante viaja como `Evento` → el worker lo convierte en **señal Qt thread-safe** → los handlers actualizan los widgets **solo en el hilo principal**.
5. **Medición (paralela al uso interactivo):** `benchmark/runner.py` ejecuta los controladores **sin GUI** (`on_evento=None`), calcula `Ts / Tthread / Tprocess` y los aceleramientos, y los persiste en `resultados/*.csv`.
