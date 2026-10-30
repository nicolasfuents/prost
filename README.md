# Pipeline Cuantitativo de Morfometría y Biomarcadores en RM de Próstata

**Institución:** Fundación INTECNUS — Maestría en Física Médica  
**Asignatura:** Taller de Informática Médica  
**Modalidad:** Proyecto Integrador  
**Duración:** 4 semanas  
**Equipamiento y Datos:** Resonador 3.0T GE SIGNA PET/MR - SIGNA PRIME (Cohorte de datos locales anonimizados)  

---

## 1. Contexto Clínico y Objetivo del Proyecto

El objetivo del proyecto es desarrollar el **núcleo computacional (Core CLI)** en Python para el procesamiento, análisis morfométrico y generación de reportes clínicos cuantitativos de Resonancia Magnética Multiparamétrica de próstata adquirida en el equipo **GE SIGNA PRIME (3.0T)** sin bobina endorrectal (antena de superficie pelviana), bajo el estándar internacional **PI-RADS v2.1**.

### Confidencialidad y Anonimización de Datos
Todos los estudios del servicio provistos para este trabajo integrador se encuentran estrictamente anonimizados (desprovistos de nombre, DNI, número de historia clínica y número de acceso) y son identificados únicamente mediante códigos institucionales tipo `CASO_01`, `ESTUDIO_002`, etc. Ningún dato filiatorio real debe ser incorporado al repositorio ni a los reportes generados.

El repositorio contiene la arquitectura modular del sistema y los archivos esqueleto (*scaffolds*) con sus interfaces y especificaciones físicas. **Los alumnos deben implementar el código correspondiente a cada módulo**, guiándose por las fórmulas analíticas, los criterios de física médica y la estructura observada en los informes clínicos del servicio.

---

## 2. Estructura del Repositorio

```text
prostate-mri-pipeline/
├── .gitignore
├── requirements.txt        # Dependencias de Python necesarias
├── README.md               # Esta guía técnica detallada
├── run_pipeline.py         # Orquestador general por línea de comandos (CLI)
├── src/
│   ├── __init__.py
│   ├── ingest_dicom.py     # [Módulo 1] Ingesta, filtrado de series, escala ADC y corregistro
│   ├── segmentation.py     # [Módulo 2] Inferencia de segmentación zonal con MONAI
│   ├── morphometry.py      # [Módulo 3] Volumetría 3D, elipsoide clínico, PSAD y análisis de difusión
│   └── report_generator.py # [Módulo 4] Reporte clínico multipanel y exportación CSV
└── data/                   # Directorio local para colocar estudios de prueba
    └── .gitkeep
```

---

## 3. Especificaciones Técnicas y Fórmulas por Módulo

### Módulo 1: Ingesta DICOM, Filtrado y Corregistro (`src/ingest_dicom.py`)

1. **Clasificación Determinista de Series:**
   - **T2W Axial:** Secuencia anatómica de alta resolución. Validar orientación axial mediante el producto vectorial de los cosenos directores en `ImageOrientationPatient (0020,0037)`:
     $$\vec{n} = \vec{r}_{\text{row}} \times \vec{r}_{\text{col}}$$
     Si $|n_z| > 0.80$, la serie es axial.
   - **Mapa ADC:** Identificar series con `"adc"` en `SeriesDescription`, ignorando capturas secundarias RGB (`"color"`, `"fusion"`, `"eadc"`).
   - **DWI de Alto Valor $b$ ($b \ge 1400\text{ s/mm}^2$):** Identificar series de difusión (`"dw_synthetic"`, `"focus"`). En el GE SIGNA PRIME, la serie sintética apila múltiples adquisiciones por corte anatómico (ej. 64 instancias para 32 posiciones de corte). Deben agrupar las instancias por `ImagePositionPatient (0020,0032)` y seleccionar el corte correspondiente al mayor valor $b$.

2. **Lectura de Tags de Difusión:**
   - Tag estándar DICOM: `(0018, 9087)` (*Diffusion b-value*).
   - Tag privado GE: `(0043, 1039)` $\rightarrow$ el valor $b$ se extrae del primer entero módulo 10000.

3. **Armonización de Unidades Físicas de ADC:**
   El estándar PI-RADS v2.1 y los informes de INTECNUS expresan el ADC en $[10^{-6}\text{ mm}^2/\text{s}]$. Según el fabricante o exportador, el mapa crudo puede venir en:
   - $\text{mm}^2/\text{s}$ (mediana $\sim 0.0012$) $\rightarrow$ multiplicar por $10^6$.
   - $10^{-3}\text{ mm}^2/\text{s}$ (mediana $\sim 1.2$) $\rightarrow$ multiplicar por $10^3$.
   - $10^{-6}\text{ mm}^2/\text{s}$ (mediana $\sim 1200$) $\rightarrow$ escala nativa (factor $1.0$).
   - $10^{-9}\text{ mm}^2/\text{s}$ (mediana $\sim 1200000$) $\rightarrow$ multiplicar por $10^{-3}$.

4. **Corregistro Geométrico Inter-Secuencia (`SimpleITK`):**
   Las secuencias de difusión focalizada (`Ax FOCUS`) tienen un FOV reducido respecto al T2W axial. Deben proyectar el mapa ADC y el DWI a la grilla geométrica exacta del T2W axial utilizando `sitk.ResampleImageFilter` (interpolación lineal para imágenes continuas y default pixel value = 0.0).

---

### Módulo 2: Segmentación Zonal con Deep Learning (`src/segmentation.py`)

1. **Modelo Preentrenado:**
   - Emplear el bundle oficial **`prostate_mri_anatomy`** del Model Zoo de MONAI:
     ```python
     import monai.bundle
     monai.bundle.download(name="prostate_mri_anatomy", bundle_dir="./models")
     ```
2. **Inferencia:**
   - Cargar la red neuronal y las transformaciones predefinidas en `inference.json` o `inference.yaml`.
   - Ejecutar inferencia sobre el volumen NIfTI `t2w_axial.nii.gz`.
   - Conmutar dinámicamente entre GPU (`cuda`) y CPU según la memoria VRAM disponible (en workstations con $<4\text{ GB}$ de VRAM libres, forzar CPU para evitar fallos de memoria).
3. **Salida y Etiquetas Anatómicas:**
   - Generar `prostate_mask.nii.gz` con la misma orientación, origen y espaciado que el T2W axial.
   - **Etiqueta 1:** Zona Central / Transición (TZ).
   - **Etiqueta 2:** Zona Periférica (PZ).
   - **Etiqueta 0:** Fondo periprostático.

---

### Módulo 3: Morfometría 3D, Biomarcadores y Difusión (`src/morphometry.py`)

1. **Volumen Real por Conteo de Vóxeles 3D:**
   $$V_{\text{vóxel}} = N_{\text{vóxeles}} \times (\Delta x \cdot \Delta y \cdot \Delta z) \times 10^{-3}\text{ [cc o cm}^3\text{]}$$
   Calcular:
   - Volumen de la Zona de Transición ($V_{\text{TZ}}$).
   - Volumen de la Zona Periférica ($V_{\text{PZ}}$).
   - Volumen total de la glándula ($V_{\text{total}} = V_{\text{TZ}} + V_{\text{PZ}}$).
   - Índice de Hiperplasia Benigna ($V_{\text{TZ}} / V_{\text{total}}$).

2. **Diámetros Ortogonales y Auditoría del Elipsoide Clínico:**
   Extraer los tres diámetros máximos de la máscara total prostática:
   - $\text{DAP}$: Diámetro Antero-Posterior (Eje Y, en mm).
   - $\text{DT}$: Diámetro Transverso (Eje X, en mm).
   - $\text{DCC}$: Diámetro Cráneo-Caudal (Eje Z, en mm).
   
   Calcular el volumen aproximado por la fórmula del elipsoide utilizada en la consola de INTECNUS:
   $$V_{\text{elipsoide}} = \text{DAP} \times \text{DT} \times \text{DCC} \times \frac{\pi}{6} \times 10^{-3}\text{ [cc]}$$
   
   Cuantificar la discrepancia porcentual respecto a la volumetría 3D real:
   $$\Delta\% = \frac{|V_{\text{vóxel}} - V_{\text{elipsoide}}|}{V_{\text{vóxel}}} \times 100\%$$

3. **Densidad de PSA ($\text{PSAD}$):**
   $$\text{PSAD} = \frac{\text{PSA [ng/mL]}}{V_{\text{total}}\text{ [cc]}}$$
   - Normal: $\text{PSAD} < 0.15\text{ ng/mL/cc}$.
   - Alerta clínica: $\text{PSAD} \ge 0.15\text{ ng/mL/cc}$ (alta probabilidad de lesión clínicamente significativa).

4. **Detección y Topografía de Focos en Zona Periférica (PZ):**
   - Enmascarar el volumen `adc_in_t2w.nii.gz` dentro de la región anatómica de la Zona Periférica ($\text{máscara} == 2$).
   - Umbralizar vóxeles con restricción marcada: $50 < \text{ADC} < 800\text{ }[\times 10^{-6}\text{ mm}^2/\text{s}]$.
   - Aplicar apertura y cierre morfológico 3D (`scipy.ndimage`) para eliminar ruido espiculado y rellenar vacíos.
   - Etiquetar componentes conexas 3D (`scipy.ndimage.label`) y descartar clusters con volumen $< 0.15\text{ cc}$ ($150\text{ mm}^3$).
   - Para el hallazgo dominante, calcular:
     - Dimensiones 3D y diámetro máximo (mm).
     - Estadísticas de ADC: media, mediana, percentil 10 ($\text{ADC}_{\text{P10}}$).
     - Localización topográfica según la convención observada en los informes de INTECNUS:
       * **Cráneo-Caudal:** Ápex / Región Media / Base.
       * **Lateral:** Línea Media / Derecha / Izquierda.
       * **Antero-Posterior:** Anterior / Posterolateral.

---

### Módulo 4: Generación de Reporte Clínico Multipanel (`src/report_generator.py`)

Diseñar una figura de una página en Matplotlib con `GridSpec` (3 filas $\times$ 4 columnas) con estética PACS:
1. **Header Institucional:** Banner de Fundación INTECNUS, ID del paciente, datos del resonador GE SIGNA PRIME 3.0T, valor de PSA y badge visual de alerta de PSAD.
2. **Paneles Anatómicos (T2W):**
   - Axial, Sagital y Coronal centrados en el ROI prostático (recorte automático con margen de $\sim 18\text{ mm}$).
   - **Corrección de aspect ratio físico:** en cortes sagitales y coronales, fijar $\text{aspect} = \Delta z / \Delta x$ para evitar distorsión vertical.
   - Superposición de contornos zonales: TZ en cian, PZ en verde y lesión sospechosa en rojo.
3. **Paneles Funcionales y Cuantitativos:**
   - Mapa térmico de ADC (`magma`) con barra de color en $[10^{-6}\text{ mm}^2/\text{s}]$.
   - Corte de DWI de alto $b$ ($b \ge 1400$) mostrando la hiperintensidad focal.
   - Histograma cuantitativo comparando las distribuciones de ADC en PZ normal vs. TZ vs. foco tumoral, con línea vertical punteada en el umbral 800.
4. **Informe Estructurado Institucional (Columna Derecha):**
   Emular el formato textual de los informes de Fundación INTECNUS:
   ```text
   1. TAMAÑO Y VOLUMETRÍA GLANDULAR
    • Tamaño: [DAP]mm DAP × [DT]mmDT × [DCC]mmDCC
    • Vol. Elipsoide: [V_elip] cc
    • Vol. Vóxel (MONAI): [V_vóxel] cc (TZ: [V_tz]cc, PZ: [V_pz]cc)
    • Discrepancia Elip vs Real: [Delta]%
    • Índice Hiperplasia TZ: [Indice]

   2. BIOMARCADOR PSA / DENSIDAD
    • Motivo/PSA: [PSA] ng/mL
    • Densidad PSA: [PSAD] ng/mL/cc  [NORMAL < 0.15 | ALERTA >= 0.15]

   3. EVALUACIÓN ZONAL (PI-RADS v2.1)
    • Zona Periférica: [Descripción topográfica, ADC medio, P10, dimensiones, Cat T2, Cat DWI-ADC, PI-RADS]
    • Zona Transicional: Heterogénea habitual. Cat T2: 2 | Cat DWI-ADC: 2 | PI-RADS: 2

   4. IMPRESIÓN DIAGNÓSTICA (INTECNUS)
    • Vol Próstata: [V_elip]cc (Elip) / [V_vóxel]cc (3D)
    • Densidad PSA: [PSAD] ng/mL/cc
    • Conclusión: [Categoría sugerida PI-RADS]
   ```
5. **Exportaciones Requeridas:**
   - `clinical_report.png` (resolución $\ge 200\text{ dpi}$).
   - `clinical_report.pdf` (vectorial de una página para incorporación a historia clínica).
   - `morphometry_metrics.csv` (tabla plana con todas las métricas cuantitativas para análisis estadístico).

---

## 4. Modos de Ejecución desde la CLI (`run_pipeline.py`)

El script principal [`run_pipeline.py`](run_pipeline.py) orquesta la ejecución completa:

### Opción A: Ingesta Manual de Series (Recomendado durante el desarrollo)
Permite especificar manualmente las tres rutas de entrada (pueden ser volúmenes `.nii.gz` o carpetas con archivos DICOM individuales):
```bash
python run_pipeline.py \
  --manual \
  --t2w /ruta/al/T2_AXIAL.nii.gz \
  --adc /ruta/al/ADC.nii.gz \
  --dwi /ruta/al/DWI_b1400.nii.gz \
  --psa 22.5 \
  --study_id "INTECNUS_CASO_01" \
  --output_dir ./output_caso01
```

### Opción B: Escaneo y Clasificación Automática de Estudio DICOM
Procesa una carpeta completa de un estudio exportado del PACS:
```bash
python run_pipeline.py \
  --dicom_dir /ruta/al/estudio_dicom_completo \
  --psa 4.6 \
  --study_id "INTECNUS_CASO_02" \
  --output_dir ./output_caso02 \
  --device auto
```

---

## 5. Cronograma de Entregas Sugerido (4 Semanas)

* **Semana 1: Entorno, Lectura DICOM y Corregistro Espacial**
  - Configurar el entorno virtual con `requirements.txt`.
  - Implementar en `src/ingest_dicom.py` la lectura de tags, ordenamiento de cortes, separación del valor $b$ sintético de GE, armonización de escala de ADC y el remuestreo hacia T2W con SimpleITK.
* **Semana 2: Segmentación con Deep Learning (MONAI) y Volumetría 3D**
  - Implementar en `src/segmentation.py` la inferencia con el bundle `prostate_mri_anatomy`.
  - Implementar en `src/morphometry.py` el cálculo de volumen real por integración de vóxeles y la extracción de diámetros DAP, DT, DCC con el volumen del elipsoide.
* **Semana 3: Física de Difusión y Detección en Zona Periférica**
  - Implementar en `src/morphometry.py` el enmascaramiento en PZ, la umbralización de ADC ($< 800$), el filtrado morfológico 3D y la localización topográfica.
  - Validar los resultados sobre al menos 5 casos locales anonimizados de Fundación INTECNUS.
* **Semana 4: Reporte Clínico Multipanel y Presentación Final**
  - Implementar en `src/report_generator.py` la figura en Matplotlib (GridSpec), los cortes con zoom al ROI, el histograma y la exportación en PDF/PNG y CSV.
  - Procesar la cohorte completa de evaluación, tabular la discrepancia elipsoide vs. vóxel y presentar las conclusiones.
