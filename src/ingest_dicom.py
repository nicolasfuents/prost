"""
MÓDULO DE INGESTA DICOM, FILTRADO Y CORREGISTRO GEOMÉTRICO
===========================================================

PROPÓSITO DEL SCRIPT:
---------------------
Procesar un estudio DICOM crudo anonimizado de RM prostática multiparamétrica del equipo
GE SIGNA PET/MR - SIGNA PRIME (3.0T) de Fundación INTECNUS, identificar determinísticamente
las series de interés, armonizar las unidades físicas de ADC, y corregistrar espacialmente
las secuencias funcionales de difusión a la grilla anatómica de la secuencia T2W Axial de referencia.

DATOS DE ENTRADA:
-----------------
Opción A (Escaneo automático):
  --dicom_dir: Directorio raíz con los archivos DICOM del estudio completo.

Opción B (Ingesta manual):
  --manual: Flag para activar la carga directa de las series.
  --t2w: Ruta a la serie T2W Axial (archivo NIfTI o carpeta con instancias DICOM).
  --adc: Ruta al Mapa ADC (archivo NIfTI o carpeta con instancias DICOM).
  --dwi: Ruta al DWI de alto valor b (archivo NIfTI o carpeta con instancias DICOM).
  --dce: [Opcional] Ruta a la serie dinámica de contraste LAVA/DISCO (NIfTI o carpeta DICOM).

DATOS DE SALIDA (en --output_dir):
----------------------------------
1. t2w_axial.nii.gz: Volumen anatómico de referencia en formato NIfTI (Float32).
2. adc_in_t2w.nii.gz: Mapa ADC con unidades físicas estandarizadas en [10^-6 mm²/s],
   proyectado a la grilla geométrica exacta de t2w_axial.nii.gz.
3. dwi_high_b_in_t2w.nii.gz: Volumen de difusión de alto b (b >= 1400 s/mm²),
   proyectado a la grilla geométrica de t2w_axial.nii.gz.
4. dce_in_t2w.nii.gz: [Opcional] Fase arterial precoz dinámica (~30-45 seg post-contraste),
   proyectada a la grilla geométrica de t2w_axial.nii.gz (si el estudio incluye contraste).

ESPECIFICACIONES TÉCNICAS Y CRITERIOS DE FÍSICA MÉDICA (GE SIGNA PRIME / INTECNUS):
-----------------------------------------------------------------------------------
1. Clasificación determinista de series:
   - T2W Axial: Validar plano axial mediante el producto vectorial de los cosenos directores
     en ImageOrientationPatient (0020,0037). Si |n_z| > 0.80, la orientación es axial.
   - Mapa ADC: Identificar por 'adc' en SeriesDescription, excluyendo capturas secundarias RGB
     ('color', 'fusion', 'eadc').
   - DWI Alto b: Identificar por 'dwi', 'focus' o 'dw_synthetic'.
   - DCE Dinámico [Opcional]: Identificar por 'lava', 'disco' o 'dynamic'.

2. Manejo de secuencias con múltiples valores b (GE DW_Synthetic):
   En el equipo GE SIGNA PRIME, la serie sintética apila múltiples adquisiciones por corte
   anatómico (ej. 64 instancias para 32 posiciones de corte con b=50 y b=1400).
   Se deben agrupar las instancias por posición espacial ImagePositionPatient (0020,0032)
   y seleccionar el corte correspondiente al mayor valor b.
   * Tags de valor b: Estándar (0018,9087) o Privado GE (0043,1039) -> primer entero mod 10000.

3. Armonización de unidades de ADC:
   El estándar PI-RADS v2.1 y Fundación INTECNUS utilizan la unidad [10^-6 mm²/s].
   Verificar la mediana de los vóxeles no nulos y re-escalar si proviene en mm²/s (x 10^6),
   10^-3 mm²/s (x 10^3) o 10^-9 mm²/s (x 10^-3).

4. Corregistro geométrico con SimpleITK:
   Las secuencias de difusión focalizada (GE Ax FOCUS) y las dinámicas (LAVA/DISCO) poseen menor FOV
   o distinta resolución que el T2W axial. Utilizar sitk.ResampleImageFilter con interpolador lineal,
   transformación identidad y default_pixel_value = 0.0 para alinear ADC, DWI y DCE sobre la grilla del T2W axial.

5. Fase precoz de contraste dinámico (DCE) [Opcional]:
   Si el estudio incluye secuencias con gadolinio, extraer la fase temporal precoz (segundo volumen dinámico,
   típicamente a los ~30-45 segundos de la inyección) donde se observa el pico de realce arterial tumoral (wash-in)
   antes del lavado o realce de la glándula periférica normal.
"""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Ingesta DICOM, armonización de escala ADC y corregistro geométrico a T2W."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dicom_dir", help="Directorio del estudio DICOM completo para escaneo automático.")
    group.add_argument("--manual", action="store_true", help="Especificar manualmente las series de entrada.")

    parser.add_argument("--t2w", help="Ruta a T2W Axial (archivo NIfTI o carpeta DICOM).")
    parser.add_argument("--adc", help="Ruta a Mapa ADC (archivo NIfTI o carpeta DICOM).")
    parser.add_argument("--dwi", help="Ruta a DWI alto b (archivo NIfTI o carpeta DICOM).")
    parser.add_argument("--dce", default=None, help="[Opcional] Ruta a serie DCE dinámica LAVA/DISCO (NIfTI o carpeta DICOM).")
    parser.add_argument("--output_dir", default="./output", help="Directorio destino para guardar los NIfTI corregistrados.")

    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.manual and not (args.t2w and args.adc and args.dwi):
        parser.error("El modo --manual requiere como mínimo especificar --t2w, --adc y --dwi.")

    # Implementación de la ingesta, normalización de ADC y corregistro
    pass


if __name__ == "__main__":
    main()
