# Pipeline Cuantitativo de Morfometría y Biomarcadores en RM de Próstata



## 1. Contexto Clínico y Objetivo del Proyecto

El objetivo del proyecto es desarrollar el **núcleo computacional (Core CLI)** en Python para el procesamiento, análisis morfométrico y generación de reportes clínicos cuantitativos de Resonancia Magnética Multiparamétrica de próstata adquirida en el equipo **GE SIGNA PRIME (3.0T)** de Fundación INTECNUS, bajo el estándar internacional **PI-RADS v2.1**.

### Confidencialidad y Anonimización de Datos
Todos los estudios del servicio provistos para este trabajo integrador se encuentran estrictamente anonimizados (desprovistos de nombre, DNI, número de historia clínica y número de acceso) y son identificados únicamente mediante códigos institucionales tipo `CASO_01`, `ESTUDIO_002`, etc. Ningún dato filiatorio real debe ser incorporado al repositorio ni a los reportes generados.

El repositorio contiene la arquitectura modular del sistema y las plantillas base con sus interfaces y especificaciones físicas. **Los alumnos deben implementar el código correspondiente a cada módulo**, guiándose por las fórmulas analíticas, los criterios de física médica y la estructura observada en los informes clínicos del servicio.

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

     $$\vec{n} = \vec{r}_ {\text{row}} \times \vec{r}_ {\text{col}}$$

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
   Las secuencias de difusión focalizada (`Ax FOCUS`) y dinámicas de contraste (`LAVA`/`DISCO`) tienen distinta resolución y FOV respecto al T2W axial. Deben proyectar el mapa ADC, el DWI y el DCE a la grilla geométrica exacta del T2W axial utilizando `sitk.ResampleImageFilter` (interpolación lineal para imágenes continuas y default pixel value = 0.0).

5. **Manejo Opcional de Contraste Dinámico (DCE / LAVA / DISCO):**
   Si el estudio incluye secuencias contrastadas con gadolinio, identificar las series multiphase (`LAVA`, `DISCO`). Extraer el volumen correspondiente a la fase arterial precoz (~30-45 s post-inyección) donde se produce el pico de realce tumoral y generar `dce_in_t2w.nii.gz`. Si el estudio es biparamétrico (sin contraste), el pipeline prescinde de esta secuencia de forma transparente.

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

1. **Planimetría Automática 3D (Volumetría Real por Conteo de Vóxeles):**

   $$V_{\text{vóxel}} = N_{\text{vóxeles}} \times (\Delta x \cdot \Delta y \cdot \Delta z) \times 10^{-3}\text{ [cc o cm}^3\text{]}$$

   - **Justificación Asistencial:** Automatiza la planimetría corte a corte en segundos. Aporta máxima reproducibilidad y precisión diagnóstica en:
     * Glándulas grandes o asimétricas con hiperplasia prostática benigna (adenomas con lóbulo medio prominente donde el elipsoide falla entre un 20% y 30%).
     * Pacientes con densidades de PSA en zona gris cercanas al punto de corte ($0.12 - 0.18\text{ ng/mL/cc}$).
     * Seguimiento longitudinal y vigilancia activa (donde la variación volumétrica debe ser real y reproducible entre controles).
   - Calcular volúmenes parciales y biomarcadores zonales:
     * Volumen de la Zona de Transición ($V_{\text{TZ}}$).
     * Volumen de la Zona Periférica ($V_{\text{PZ}}$).
     * Volumen total de la glándula ($V_{\text{total}} = V_{\text{TZ}} + V_{\text{PZ}}$).
     * **Relación Transición / Periférica:** $`\text{Ratio}_{\text{TZ/PZ}} = V_{\text{TZ}} / V_{\text{PZ}}`$.
     * Índice de Hiperplasia Benigna: $V_{\text{TZ}} / V_{\text{total}}$.

2. **Diámetros Clínicos en Planos Anatómicos Estrictos:**
   Para asegurar que las mediciones del software sean directamente comparables con los calipers colocados manualmente por el médico en la estación de trabajo:
   - **Plano Axial T2W:**
     * $\text{DT}$: Diámetro Transverso máximo (ancho de izquierda a derecha, Eje X, en mm).
     * $\text{DAP}$: Diámetro Antero-Posterior máximo (profundidad ventral a dorsal, Eje Y, en mm).
   - **Plano Sagital T2W (corte medio sagital):**
     * $\text{DCC}$: Diámetro Cráneo-Caudal máximo (altura desde la base vesical al ápex prostático, Eje Z, en mm).

   Calcular el volumen del elipsoide clínico:

   $$V_{\text{elipsoide}} = \text{DAP} \times \text{DT} \times \text{DCC} \times \frac{\pi}{6} \times 10^{-3}\text{ [cc]}$$

   Cuantificar la discrepancia porcentual respecto a la planimetría real:

   $$\Delta\\% = \frac{|V_ {\text{vóxel}} - V_ {\text{elipsoide}}|}{V_ {\text{vóxel}}} \times 100\\%$$

3. **Biomarcadores de PSA:**
   - **Densidad de PSA Global ($\text{PSAD}$):**

     $$\text{PSAD} = \frac{\text{PSA [ng/mL]}}{V_{\text{total}}\text{ [cc]}}$$

     * Normal: $\text{PSAD} < 0.15\text{ ng/mL/cc}$.
     * Alerta clínica: $\text{PSAD} \ge 0.15\text{ ng/mL/cc}$ (alta sospecha de cáncer significativo).
   - **Densidad de PSA en Zona de Transición ($`\text{PSAD}_{\text{TZ}}`$):**

     $$\text{PSAD}_ {\text{TZ}} = \frac{\text{PSA [ng/mL]}}{V_ {\text{TZ}}\text{ [cc]}}$$

     Biomarcador diferencial fundamental: un PSA elevado acompañado de un $`\text{PSAD}_{\text{TZ}}`$ bajo se correlaciona con adenoma benigno voluminoso y no con neoplasia maligna oculta.

4. **Detección Focalizada de Candidatos en Difusión ($b \ge 1400$ y ADC):**
   *Nota Clínica:* El promedio global de ADC en toda la zona periférica no aporta valor diagnóstico. El software debe individualizar los focos sospechosos para que el médico los confirme visualmente:
   - Cruzar la hiperintensidad en difusión de alto $b$ ($b \ge 1400\text{ s/mm}^2$) con la restricción marcada en el mapa ADC ($50 < \text{ADC} < 800\times 10^{-6}\text{ mm}^2/\text{s}$) enmascarado en la Zona Periférica.
   - Aplicar filtrado morfológico 3D (`scipy.ndimage`) y segmentar componentes conexas con volumen $\ge 0.15\text{ cc}$ ($150\text{ mm}^3$).
   - Por cada candidato detectado (`FOCO_1`, `FOCO_2`), reportar sus métricas individuales:
     * Volumen focal ($V_{\text{foco}}$ en cc) y diámetro máximo (mm).
     * ADC medio puntual y percentil 10 ($\text{ADC}_{\text{P10}}$ en $10^{-6}\text{ mm}^2/\text{s}$).
     * Localización topográfica 3D (Base / Región Media / Ápex, Derecha / Izquierda / Línea Media, Anterior / Posterolateral).

5. **Criterio de Desempate PI-RADS v2.1 con Contraste Dinámico (DCE) [Opcional]:**
   En la Zona Periférica (PZ), la secuencia dominante es DWI/ADC:
   - Si un foco presenta un score DWI/ADC de 3 (restricción focal intermedia):
     * Si DCE es **positivo** (realce focal precoz respecto al parénquima adyacente): categoría final **PI-RADS 4**.
     * Si DCE es **negativo** o **no realizado** (estudio biparamétrico bpMRI sin contraste): se mantiene en **PI-RADS 3**.
   - En la Zona de Transición (TZ), la secuencia dominante es T2W; el estado de DCE no altera la categoría diagnóstica final.

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
   - Si se cuenta con `--dce`: Panel de fase arterial precoz dinámica mostrando el realce focal tumoral precoz.
   - Histograma cuantitativo comparando las distribuciones de ADC en PZ normal vs. TZ vs. foco tumoral, con línea vertical punteada en el umbral 800.
4. **Informe Estructurado Institucional y Texto Copy-Paste:**
   Emular el formato textual de los informes de Fundación INTECNUS para la generación simultánea de `clinical_report_template.txt`:
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

   2. BIOMARCADORES PSA / DENSIDADES
    • PSA Sérico: [PSA] ng/mL
    • Densidad PSA Global (PSAD): [PSAD] ng/mL/cc  [NORMAL < 0.15 | ALERTA >= 0.15]
    • Densidad PSA en Transición (PSAD_TZ): [PSAD_TZ] ng/mL/cc

   3. EVALUACIÓN ZONAL Y FOCOS EN DIFUSIÓN (PI-RADS v2.1)
    • Focos identificados en difusión (b alto + ADC):
      - FOCO 1: [Topografía 3D], Vol: [V_foco] cc, Diám: [Diam] mm
        ADC medio: [ADC_medio] | ADC P10: [ADC_P10] x10^-6 mm²/s | Restricción: Marcada
        DCE: [Realce focal precoz +/-/No evaluado] | Categoría sugerida: [PI-RADS 4/5]
    • Zona Transicional: Heterogénea habitual sin nódulos dominantes atípicos. Cat T2: 2 | PI-RADS: 2

   4. IMPRESIÓN DIAGNÓSTICA (INTECNUS)
    • Vol Próstata: [V_elip] cc (Elipsoide) / [V_vóxel] cc (Planimetría 3D)
    • Densidad PSA: [PSAD] ng/mL/cc | Densidad TZ: [PSAD_TZ] ng/mL/cc
    • Conclusión: [Categoría sugerida PI-RADS v2.1 para confirmación del especialista]
   ```

5. **Exportaciones Requeridas:**
   - `clinical_report.png` (resolución $\ge 200\text{ dpi}$ para vista rápida).
   - `clinical_report.pdf` (vectorial de una página para incorporación a historia clínica digital).
   - `clinical_report_template.txt` (texto plano con el bloque formateado listo para copiar y pegar en la plantilla de informe médico).
   - `prostate_seg.dcm` [Opcional - Hito Integrador]: Objeto estándar DICOM SEG (`pydicom-seg`) para importar la segmentación al PACS.
   - `morphometry_metrics.csv` (tabla cuantitativa de una fila por paciente para auditoría del servicio).

---

## 4. Modos de Ejecución desde la CLI (`run_pipeline.py`)

El script principal [`run_pipeline.py`](run_pipeline.py) orquesta la ejecución completa:

### Opción A: Ingesta Manual de Series (Recomendado durante el desarrollo)
Permite especificar manualmente las rutas de entrada (volúmenes `.nii.gz` o carpetas DICOM individuales):
```bash
python run_pipeline.py \
  --manual \
  --t2w /ruta/al/T2_AXIAL.nii.gz \
  --adc /ruta/al/ADC.nii.gz \
  --dwi /ruta/al/DWI_b1400.nii.gz \
  --dce /ruta/al/DCE_fase_precoz.nii.gz \
  --psa 22.5 \
  --study_id "INTECNUS_CASO_01" \
  --output_dir ./output_caso01
```
*(Nota: El parámetro `--dce` es opcional; si el estudio es biparamétrico sin contraste, se omite).*

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

### Opción C: Re-ejecución con Máscara Corregida Manualmente (Flujo Clínico Ágil)
Si el radiólogo o físico médico observa que la segmentación automática de MONAI requiere ajustes en ápex o base, puede editar la máscara en 3D Slicer o ITK-SNAP en segundos y re-ejecutar el pipeline saltando la inferencia de FASE 2:
```bash
python run_pipeline.py \
  --manual \
  --t2w /ruta/al/T2_AXIAL.nii.gz \
  --adc /ruta/al/ADC.nii.gz \
  --dwi /ruta/al/DWI_b1400.nii.gz \
  --mask /ruta/a/prostate_mask_corregida.nii.gz \
  --psa 22.5 \
  --study_id "INTECNUS_CASO_01" \
  --output_dir ./output_caso01_corregido
```

---

## 5. Cronograma de Entregas Sugerido (4 Semanas)

* **Semana 1: Entorno, Lectura DICOM y Corregistro Espacial**
  - Configurar el entorno virtual con `requirements.txt`.
  - Implementar en `src/ingest_dicom.py` la lectura de tags, ordenamiento de cortes, separación del valor $b$ sintético de GE, armonización de escala de ADC y el remuestreo hacia T2W con SimpleITK.
* **Semana 2: Segmentación con Deep Learning (MONAI) y Volumetría 3D**
  - Implementar en `src/segmentation.py` la inferencia con el bundle `prostate_mri_anatomy`.
  - Implementar en `src/morphometry.py` el cálculo de planimetría real por conteo de vóxeles ($`V_{\text{total}}`$, $`V_{\text{TZ}}`$, $`V_{\text{PZ}}`$, $`\text{Ratio}_{\text{TZ/PZ}}`$) y la extracción de diámetros ortogonales en planos anatómicos estrictos (Axial DT/DAP, Sagital DCC).
* **Semana 3: Física de Difusión, Focos Sospechosos y Biomarcadores**
  - Implementar en `src/morphometry.py` el cálculo de $`\text{PSAD}_{\text{total}}`$ y $`\text{PSAD}_{\text{TZ}}`$.
  - Individualizar los candidatos a focos sospechosos cruzando $b \ge 1400$ y $\text{ADC} < 800$, extrayendo el $\text{ADC}$ medio y percentil 10 ($`\text{ADC}_{\text{P10}}`$) de cada foco junto a su topografía para confirmación médica.
  - Validar los resultados sobre al menos 5 casos locales anonimizados de Fundación INTECNUS.
* **Semana 4: Reportes Clínicos (Visual, Texto Copy-Paste y DICOM SEG) y Cierre**
  - Implementar en `src/report_generator.py` la figura en Matplotlib (GridSpec) y la exportación de `clinical_report_template.txt` para pegado directo en plantillas de informes.
  - Generar el objeto DICOM SEG (`pydicom-seg`) para visualización directa de la máscara en el PACS del servicio.
  - Procesar la cohorte completa de evaluación, tabular la discrepancia elipsoide vs. vóxel y presentar las conclusiones.
