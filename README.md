# Pipeline Cuantitativo de Morfometría y Biomarcadores en RM de Próstata

**Institución:** Fundación INTECNUS — Maestría en Física Médica  
**Proyecto:** Procesamiento Cuantitativo de RM Multiparamétrica (PI-RADS v2.1)  
**Equipamiento:** Resonadores GE SIGNA PET/MR (1.5T) y GE SIGNA PRIME (3.0T)

---

## 1. Contexto Clínico y Objetivo del Proyecto

El objetivo del trabajo integrador es desarrollar el **núcleo computacional (Core CLI)** en Python para el procesamiento automático, análisis morfométrico y generación de reportes cuantitativos de Resonancia Magnética Multiparamétrica (mpMRI) de próstata, bajo el estándar internacional **PI-RADS v2.1**.

### Organización del Dataset Provisto
Para cada uno de los 10 casos clínicos anonimizados (`PR15T01` a `PR15T05` adquiridos en 1.5T y `PR3T01` a `PR3T05` adquiridos en 3.0T), las series requeridas se encuentran pre-seleccionadas y organizadas en carpetas estandarizadas:

* `01_T2_Axial/`: Serie anatómica axial de alta resolución (cortes de 3 mm). Base espacial y volumétrica del estudio.
* `02_T2_Sagital/`: Serie anatómica sagital (cortes de 3 mm). Empleada para medir la altura o diámetro cráneo-caudal (DCC).
* `03_ADC/`: Mapa paramétrico de coeficiente de difusión aparente (`[10⁻⁶ mm²/s]`).
* `04_DWI/`: Serie axial de difusión de alto gradiente (`b ≥ 1400 s/mm²`).
* `datos_admision.json`: Parámetros clínicos de ingreso del paciente (PSA sérico de entrada en ng/mL, edad y motivo de consulta).
* `INFORME_CLINICO.pdf`: Reporte médico oficial emitido por el especialista. Se utiliza exclusivamente como **Ground Truth** para validar y contrastar los resultados del software.
* `_OPCIONALES/`: Secuencias complementarias (fase post-contraste DCE, coronal T2, T1 pélvico) para análisis extendido si el grupo dispone de tiempo.

---

## 2. Arquitectura del Pipeline y Flujo DICOM $\rightarrow$ NIfTI

El procesamiento clínico involucra dos formatos estándar complementarios:
1. **Entrada Clínica (DICOM):** Las imágenes médicas provienen del resonador como conjuntos de archivos DICOM (`.dcm`) organizados por serie.
2. **Procesamiento y Deep Learning (NIfTI):** Las redes neuronales (como MONAI) y las librerías de análisis 3D requieren volúmenes continuos en formato NIfTI (`.nii.gz`), donde el espaciado físico, origen y matriz de orientación espacial se encuentran unificados en un único encabezado.

```text
prostate-mri-pipeline/
├── requirements.txt        # Dependencias de Python necesarias
├── README.md               # Esta especificación técnica
├── run_pipeline.py         # Orquestador general por línea de comandos (CLI)
├── src/
│   ├── ingest_dicom.py     # [Módulo 1] Ingesta DICOM -> NIfTI, escala ADC y corregistro
│   ├── segmentation.py     # [Módulo 2] Segmentación zonal profunda con MONAI
│   ├── morphometry.py      # [Módulo 3] Volumetría 3D, elipsoide clínico, PSAD y análisis de difusión
│   └── report_generator.py # [Módulo 4] Reporte visual multipanel, plantilla médica y DICOM SEG
└── data/                   # Directorio local para colocar estudios de prueba
```

### Flujo de Trabajo en 4 Módulos Consecutivos:

```text
[Carpetas DICOM] + [datos_admision.json]
       │
       ▼
[Módulo 1: ingest_dicom.py] ────────► Genera volúmenes NIfTI corregistrados:
                                       • t2w_axial.nii.gz
                                       • t2w_sagital.nii.gz
                                       • adc_in_t2w.nii.gz
                                       • dwi_high_b_in_t2w.nii.gz
       │
       ▼
[Módulo 2: segmentation.py] ────────► MONAI (prostate_mri_anatomy)
                                       • prostate_mask.nii.gz (TZ, PZ, fondo)
       │
       ▼
[Módulo 3: morphometry.py]  ────────► Planimetría vóxel vs. Elipsoide, PSAD y Focos ADC
                                       • morphometry_results.json
                                       • lesion_mask.nii.gz
       │
       ▼
[Módulo 4: report_generator.py] ────► Reportes Clínicos y PACS:
                                       • clinical_report.pdf / .png
                                       • clinical_report_template.txt
                                       • prostate_seg.dcm (DICOM SEG)
```

---

## 3. Especificaciones Técnicas por Módulo

### Módulo 1: Ingesta DICOM, Escala ADC y Corregistro (`src/ingest_dicom.py`)

1. **Lectura y Conversión a NIfTI con `SimpleITK`:**
   Leer las carpetas de entrada (`01_T2_Axial`, `02_T2_Sagital`, `03_ADC`, `04_DWI`) utilizando `sitk.ImageSeriesReader()` y exportar los volúmenes en formato NIfTI (`.nii.gz`):
   - `t2w_axial.nii.gz`: Volumen anatómico axial de referencia.
   - `t2w_sagital.nii.gz`: Volumen sagital empleado para la medición cráneo-caudal.

2. **Armonización de Unidades Físicas de ADC:**
   El estándar PI-RADS v2.1 y la práctica asistencial expresan el ADC en `[10⁻⁶ mm²/s]`.
   - Verificar la escala de los vóxeles de difusión del mapa ADC. En tejido sano, los valores típicos rondan entre 1000 y 1600 × 10⁻⁶ mm²/s.
   - Si los valores vienen en mm²/s (orden de 0.001) o en 10⁻³ mm²/s (orden de 1.2), multiplicar por el factor correspondiente para armonizar a la escala estándar (10⁶ o 10³).

3. **Corregistro Espacial sobre la Grilla T2 (`sitk.ResampleImageFilter`):**
   Las series funcionales (ADC y DWI) suelen tener una matriz de adquisición menor que el T2 axial.
   - Proyectar el mapa ADC y la serie DWI a la grilla geométrica exacta de `t2w_axial.nii.gz` mediante interpolación lineal.
   - Guardar como `adc_in_t2w.nii.gz` y `dwi_high_b_in_t2w.nii.gz`.

---

### Módulo 2: Segmentación Zonal con Deep Learning (`src/segmentation.py`)

1. **Modelo Preentrenado:**
   - Emplear el bundle oficial **`prostate_mri_anatomy`** del Model Zoo de MONAI:
     ```python
     import monai.bundle
     monai.bundle.download(name="prostate_mri_anatomy", bundle_dir="./models")
     ```
2. **Inferencia y Salida:**
   - Ejecutar la inferencia sobre `t2w_axial.nii.gz`.
   - Generar `prostate_mask.nii.gz` preservando estrictamente la matriz de dirección, origen y espaciado de vóxel del volumen T2W.
   - **Etiqueta 1:** Zona de Transición / Central (TZ).
   - **Etiqueta 2:** Zona Periférica (PZ).
   - **Etiqueta 0:** Fondo periprostático.

---

### Módulo 3: Morfometría 3D, Biomarcadores y Difusión (`src/morphometry.py`)

#### 1. Planimetría Automática 3D (Volumetría Real por Conteo de Vóxeles):
El volumen real anatómico se obtiene integrando los vóxeles etiquetados:

```text
V_vóxel = Σ vóxeles × (PixelSpacing_x × PixelSpacing_y × SliceThickness) × 10⁻³  [cc]
```

donde `PixelSpacing_x`, `PixelSpacing_y` y `SliceThickness` corresponden al espaciado físico en mm.
* `V_total = V_TZ + V_PZ`
* `V_TZ`: Volumen de la Zona de Transición / adenoma.
* `V_PZ`: Volumen de la Zona Periférica.
* **Relación Transición / Periférica:** `Ratio_TZ/PZ = V_TZ / V_PZ`
* **Índice de Hiperplasia Benigna:** `V_TZ / V_total`

#### 2. Diámetros Clínicos en Planos Anatómicos Estrictos:
Para que las mediciones sean directamente comparables con los calipers colocados manualmente por el médico en la estación de trabajo:
* **Plano Axial T2 (`01_T2_Axial`):**
  - `DT`: Diámetro Transverso máximo (Eje X, izquierda a derecha en mm).
  - `DAP`: Diámetro Antero-Posterior máximo (Eje Y, ventral a dorsal en mm).
* **Plano Sagital T2 (`02_T2_Sagital`):**
  - `DCC`: Diámetro Cráneo-Caudal máximo (Eje Z, base vesical al ápex prostático en mm).

Calcular el volumen del elipsoide clínico estándar:
```text
V_elipsoide = DAP × DT × DCC × (π / 6) × 10⁻³  [cc] ≈ DAP × DT × DCC × 0.5236 × 10⁻³  [cc]
```

Cuantificar la discrepancia porcentual respecto a la planimetría real:
```text
Δ% = (|V_vóxel - V_elipsoide| / V_vóxel) × 100%
```

#### 3. Biomarcadores de PSA:
Tomando el valor provisto al ingreso en `datos_admision.json` (o argumento `--psa`):
* **Densidad de PSA Global (`PSAD`):**
  ```text
  PSAD = PSA [ng/mL] / V_total [cc]
  ```
  - Normal: `PSAD < 0.15 ng/mL/cc`.
  - Alerta clínica: `PSAD ≥ 0.15 ng/mL/cc` (sospecha de neoplasia clínicamente significativa).
* **Densidad de PSA en Zona de Transición (`PSAD_TZ`):**
  ```text
  PSAD_TZ = PSA [ng/mL] / V_TZ [cc]
  ```
  Biomarcador diferencial: un PSA elevado acompañado de un `PSAD_TZ` bajo orienta a adenoma benigno voluminoso y no a patología maligna oculta.

#### 4. Detección Focalizada de Candidatos en Difusión (b ≥ 1400 s/mm² y ADC):
El promedio global de ADC en toda la zona periférica no aporta valor diagnóstico suficiente. El software debe individualizar los focos sospechosos para que el médico los confirme visualmente:
* Cruzar la hiperintensidad en difusión de alto b (`b ≥ 1400 s/mm²`) con la restricción marcada en el mapa ADC (`50 < ADC < 800 × 10⁻⁶ mm²/s`) enmascarado en la Zona Periférica.
* Aplicar filtrado morfológico 3D (`scipy.ndimage`) y segmentar componentes conexas con volumen `≥ 0.15 cc` (`150 mm³`).
* Por cada candidato detectado (`FOCO_1`, `FOCO_2`), reportar:
  * Volumen focal (cc) y diámetro máximo (mm).
  * ADC medio puntual y percentil 10 (`ADC_P10` en `10⁻⁶ mm²/s`).
  * Localización topográfica 3D (Ápex / Región Media / Base, Derecha / Izquierda / Línea Media, Anterior / Posterolateral).

#### 5. Criterio de Desempate PI-RADS v2.1 con Contraste Dinámico (DCE) [Opcional]:
En la Zona Periférica (PZ), la secuencia dominante es DWI/ADC:
* Si un foco presenta score DWI/ADC = 3:
  * Si DCE es **positivo** (realce precoz focal): categoría final **PI-RADS 4**.
  * Si DCE es **negativo** o **no realizado** (estudio biparamétrico bpMRI sin contraste): se mantiene en **PI-RADS 3**.

---

## 4. Módulo 4: Reporte Clínico Multipanel e Informe Estructurado (`src/report_generator.py`)

1. **Figura Multipanel (`clinical_report.png` / `.pdf`):**
   Diseñar una figura de una página en Matplotlib con `GridSpec` (3 filas × 4 columnas) con estética PACS:
   - Header Institucional con ID del paciente, resonador, valor de PSA y badge de alerta de PSAD.
   - Paneles anatómicos T2W (Axial, Sagital, Coronal con recorte de próstata y contornos de segmentación).
   - Mapa térmico de ADC (`magma`) con barra en `[10⁻⁶ mm²/s]` y corte de DWI de alto b.
   - Histograma de distribución de ADC en PZ normal vs. foco tumoral con umbral de corte en 800.

2. **Informe Estructurado y Salida Copy-Paste (`clinical_report_template.txt`):**
   ```text
   1. TAMAÑO Y VOLUMETRÍA GLANDULAR (PLANIMETRÍA 3D)
    • Diámetros: [DT]mm DT (axial) × [DAP]mm DAP (axial) × [DCC]mm DCC (sagital)
    • Vol. Elipsoide Clínico: [V_elip] cc
    • Vol. Real (Planimetría Vóxel): [V_vóxel] cc
      - Zona de Transición (TZ): [V_tz] cc
      - Zona Periférica (PZ): [V_pz] cc
      - Relación Transición / Periférica: [Ratio_TZ_PZ]
      - Índice de Hiperplasia Benigna: [Indice]
    • Discrepancia Elip vs Real: [Delta]%

   2. BIOMARCADORES PSA / DENSIDADES (ADMISIÓN)
    • PSA Sérico: [PSA] ng/mL
    • Densidad PSA Global (PSAD): [PSAD] ng/mL/cc  [NORMAL < 0.15 | ALERTA >= 0.15]
    • Densidad PSA en Transición (PSAD_TZ): [PSAD_TZ] ng/mL/cc

   3. EVALUACIÓN ZONAL Y FOCOS EN DIFUSIÓN (PI-RADS v2.1)
    • Focos identificados en difusión (b alto + ADC):
      - FOCO 1: [Topografía 3D], Vol: [V_foco] cc, Diám: [Diam] mm
        ADC medio: [ADC_medio] | ADC P10: [ADC_P10] x10^-6 mm²/s | Restricción: Marcada
        DCE: [Realce focal precoz +/-/No evaluado] | Categoría sugerida: [PI-RADS 4/5]
    • Zona Transicional: Heterogénea habitual sin nódulos dominantes atípicos.

   4. IMPRESIÓN DIAGNÓSTICA (INTECNUS)
    • Vol Próstata: [V_elip] cc (Elipsoide) / [V_vóxel] cc (Planimetría 3D)
    • Densidad PSA: [PSAD] ng/mL/cc | Densidad TZ: [PSAD_TZ] ng/mL/cc
    • Conclusión: [Categoría sugerida PI-RADS v2.1 para confirmación médica]
   ```

3. **Exportación Estándar DICOM SEG (`prostate_seg.dcm`):**
   Generar el objeto estándar DICOM Segmentation (`pydicom-seg` o `highdicom`) referenciando los UID de las instancias originales de `01_T2_Axial` para que la máscara pueda cargarse nativamente en cualquier estación PACS del hospital.

---

## 5. Modos de Ejecución desde la CLI (`run_pipeline.py`)

El script principal [`run_pipeline.py`](run_pipeline.py) orquesta la ejecución completa:

### Opción A: Escaneo Automático del Estudio (Recomendado)
Recibe la carpeta del caso; lee automáticamente las carpetas `01_T2_Axial`, `02_T2_Sagital`, `03_ADC`, `04_DWI` y el valor de PSA desde `datos_admision.json`:
```bash
python run_pipeline.py \
  --dicom_dir /ruta/al/dataset_prostata_alumnos/PR15T01 \
  --output_dir ./output_PR15T01 \
  --device auto
```

### Opción B: Ingesta Manual de Series
Permite especificar manualmente las rutas de entrada (carpetas DICOM o volúmenes `.nii.gz`):
```bash
python run_pipeline.py \
  --manual \
  --t2w /ruta/a/01_T2_Axial \
  --t2_sag /ruta/a/02_T2_Sagital \
  --adc /ruta/a/03_ADC \
  --dwi /ruta/a/04_DWI \
  --psa 8.4 \
  --study_id "PR15T01" \
  --output_dir ./output_PR15T01
```

### Opción C: Re-ejecución con Máscara Corregida (Edición Rápida)
Si el especialista ajusta la segmentación automática en 3D Slicer o ITK-SNAP, se puede re-ejecutar el pipeline saltando la FASE 2:
```bash
python run_pipeline.py \
  --manual \
  --t2w /ruta/a/01_T2_Axial \
  --t2_sag /ruta/a/02_T2_Sagital \
  --adc /ruta/a/03_ADC \
  --dwi /ruta/a/04_DWI \
  --mask /ruta/a/prostate_mask_corregida.nii.gz \
  --psa 8.4 \
  --study_id "PR15T01" \
  --output_dir ./output_PR15T01_corregido
```

---

## 6. Cronograma Sugerido de Desarrollo (4 Semanas)

* **Semana 1: Lectura DICOM con SimpleITK, Conversión a NIfTI y Corregistro Espacial**
  - Configurar el entorno virtual con `requirements.txt`.
  - Implementar en `src/ingest_dicom.py` la lectura de las carpetas DICOM de entrada, la verificación de escala de ADC y el remuestreo de las series funcionales hacia el espacio anatómico de T2W axial.
* **Semana 2: Segmentación con Deep Learning (MONAI) y Volumetría 3D**
  - Implementar en `src/segmentation.py` la inferencia con el bundle `prostate_mri_anatomy`.
  - Implementar en `src/morphometry.py` el cálculo de planimetría real por conteo de vóxeles (`V_total`, `V_TZ`, `V_PZ`, `Ratio_TZ/PZ`) y la extracción de diámetros en planos ortogonales (Axial DT/DAP, Sagital DCC).
* **Semana 3: Física de Difusión, Focos Sospechosos y Validación con Ground Truth**
  - Implementar en `src/morphometry.py` el cálculo de `PSAD` global y `PSAD_TZ`.
  - Individualizar los candidatos a focos sospechosos cruzando `b ≥ 1400` y `ADC < 800`, extrayendo el ADC medio y percentil 10 (`ADC_P10`) puntual de cada foco.
  - Contrastar las métricas de los alumnos frente a los informes médicos de referencia (`INFORME_CLINICO.pdf`).
* **Semana 4: Reportes Clínicos (Visual, Texto Copy-Paste y DICOM SEG) y Cierre**
  - Implementar en `src/report_generator.py` la figura en Matplotlib (GridSpec) y la exportación de `clinical_report_template.txt`.
  - Generar el objeto estándar DICOM SEG (`pydicom-seg` o `highdicom`) para visualización directa de la máscara en el PACS.
  - Procesar los 10 casos de evaluación, tabular la discrepancia elipsoide vs. vóxel y presentar el informe final.
