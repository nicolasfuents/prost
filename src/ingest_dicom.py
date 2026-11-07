"""
MÓDULO DE INGESTA DICOM, ESCALA ADC Y CORREGISTRO ESPACIAL
==========================================================

PROPÓSITO DEL SCRIPT:
---------------------
Procesar las series DICOM de RM prostática provistas en el dataset de cátedra
(organizadas en las carpetas 01_T2_Axial, 02_T2_Sagital, 03_ADC y 04_DWI),
cargar los volúmenes con SimpleITK, armonizar las unidades físicas de ADC
a la escala asistencial estándar [10^-6 mm²/s], remuestrear espacialmente
las secuencias funcionales sobre la grilla anatómica de referencia (T2 Axial)
y exportar los volúmenes en formato NIfTI (.nii.gz).

DATOS DE ENTRADA:
-----------------
Opción A (Escaneo automático de directorio del caso):
  --dicom_dir: Directorio raíz del caso (ej. dataset_prostata_alumnos/PR15T01).
               El script detecta automáticamente las carpetas normalizadas:
                 * 01_T2_Axial/
                 * 02_T2_Sagital/
                 * 03_ADC/
                 * 04_DWI/
                 * _OPCIONALES/ (si incluye secuencias con contraste)

Opción B (Ingesta manual de series):
  --manual: Flag para especificar rutas individuales.
  --t2w:    Ruta a la serie T2W Axial (carpeta DICOM o archivo NIfTI).
  --t2_sag: [Recomendado] Ruta a la serie T2W Sagital (carpeta DICOM o NIfTI).
  --adc:    Ruta al Mapa ADC (carpeta DICOM o NIfTI).
  --dwi:    Ruta a la serie DWI de alto b (carpeta DICOM o NIfTI).
  --dce:    [Opcional] Ruta a serie DCE con contraste.

DATOS DE SALIDA (en --output_dir):
----------------------------------
1. t2w_axial.nii.gz: Volumen anatómico axial de referencia en formato NIfTI (Float32).
2. t2w_sagital.nii.gz: Volumen anatómico sagital para biometría cráneo-caudal (DCC).
3. adc_in_t2w.nii.gz: Mapa ADC estandarizado en [10^-6 mm²/s] proyectado a la grilla de T2W.
4. dwi_high_b_in_t2w.nii.gz: Volumen DWI de alto b proyectado a la grilla de T2W.
5. dce_in_t2w.nii.gz: [Opcional] Volumen contrastado proyectado a la grilla de T2W.

ESPECIFICACIONES TÉCNICAS (PI-RADS v2.1):
----------------------------------------
1. Lectura y conversión DICOM a NIfTI (Herramientas a elección):
   - SimpleITK: sitk.ImageSeriesReader() con GetGDCMSeriesFileNames(dir) para ensamblar
     las instancias ordenadas espacialmente según ImagePositionPatient (0020,0032).
   - dcm2niix: Conversor de referencia para exportar de carpeta DICOM a NIfTI conservando matrices qform/sform.
   - NiBabel (nibabel): Manejo, lectura de matrices afines (affine) y manipulación de datos NIfTI en Python.

2. Armonización de escala de ADC:
   El estándar PI-RADS v2.1 y la práctica clínica expresan el ADC en [10^-6 mm²/s].
   En tejido prostático sano, la mediana del ADC se sitúa típicamente entre 1000 y 1600.
   Verificar el orden de magnitud de los vóxeles y multiplicar por el factor necesario
   (ej. factor 10^6 si viene en mm²/s o 10^3 si viene en 10^-3 mm²/s) para estandarizar
   la escala antes de la exportación NIfTI.

3. Corregistro espacial (sitk.ResampleImageFilter):
   Las secuencias funcionales de difusión poseen menor matriz o distinto FOV que el T2W axial.
   Remuestrear adc_img y dwi_img sobre la grilla exacta de t2w_axial (mismo espaciado,
   origen, dirección y dimensiones) empleando interpolación lineal y default_pixel_value = 0.0.
"""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Ingesta DICOM, armonización de escala ADC y corregistro geométrico a T2W."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dicom_dir", help="Directorio del estudio del paciente para escaneo automático.")
    group.add_argument("--manual", action="store_true", help="Especificar manualmente las series de entrada.")

    parser.add_argument("--t2w", help="Ruta a T2W Axial (archivo NIfTI o carpeta DICOM).")
    parser.add_argument("--t2_sag", default=None, help="[Recomendado] Ruta a T2W Sagital (archivo NIfTI o carpeta DICOM).")
    parser.add_argument("--adc", help="Ruta a Mapa ADC (archivo NIfTI o carpeta DICOM).")
    parser.add_argument("--dwi", help="Ruta a DWI alto b (archivo NIfTI o carpeta DICOM).")
    parser.add_argument("--dce", default=None, help="[Opcional] Ruta a serie DCE con contraste (NIfTI o carpeta DICOM).")
    parser.add_argument("--output_dir", default="./output", help="Directorio destino para guardar los NIfTI corregistrados.")

    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.manual and not (args.t2w and args.adc and args.dwi):
        parser.error("El modo --manual requiere como mínimo especificar --t2w, --adc y --dwi.")

    # Implementación de la ingesta, normalización de ADC y corregistro por parte de los alumnos
    pass


if __name__ == "__main__":
    main()
