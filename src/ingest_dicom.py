"""
MÓDULO DE INGESTA DICOM, FILTRADO Y CORREGISTRO GEOMÉTRICO
===========================================================

PROPÓSITO DEL SCRIPT:
---------------------
Procesar un estudio DICOM anonimizado de RM prostática multiparamétrica (adquirido en equipos
GE SIGNA PRIME 1.5T o 3.0T de Fundación INTECNUS bajo protocolo PI-RADS v2.1), identificar
las series de interés, armonizar las unidades físicas de ADC, y corregistrar espacialmente
las secuencias funcionales de difusión a la grilla anatómica de la secuencia T2W Axial de referencia.

DATOS DE ENTRADA:
-----------------
Opción A (Escaneo automático de directorio de estudio):
  --dicom_dir: Directorio raíz con el estudio del paciente.
               El script debe ser compatible tanto con la estructura curada normalizada de cátedra:
                 * 01_T2_Axial/
                 * 02_T2_Sagital/
                 * 03_ADC/
                 * 04_DWI/
                 * _OPCIONALES/ (DCE, coronal T2, T1 pélvico)
               como con estudios crudos que contengan nomenclaturas nativas de consola GE.

Opción B (Ingesta manual de series):
  --manual: Flag para activar la carga directa de las series.
  --t2w:    Ruta a la serie T2W Axial (archivo NIfTI o carpeta con instancias DICOM).
  --t2_sag: [Recomendado] Ruta a la serie T2W Sagital para medición de DCC (NIfTI o carpeta DICOM).
  --adc:    Ruta al Mapa ADC (archivo NIfTI o carpeta con instancias DICOM).
  --dwi:    Ruta al DWI de alto valor b (archivo NIfTI o carpeta con instancias DICOM).
  --dce:    [Opcional] Ruta a serie con contraste (NIfTI o carpeta DICOM).

DATOS DE SALIDA (en --output_dir):
----------------------------------
1. t2w_axial.nii.gz: Volumen anatómico axial de referencia en formato NIfTI (Float32).
2. t2w_sagital.nii.gz: [Recomendado] Volumen anatómico sagital para biometría cráneo-caudal (DCC).
3. adc_in_t2w.nii.gz: Mapa ADC con unidades físicas estandarizadas en [10^-6 mm²/s],
   proyectado a la grilla geométrica exacta de t2w_axial.nii.gz.
4. dwi_high_b_in_t2w.nii.gz: Volumen de difusión de alto b (b >= 1400 s/mm²),
   proyectado a la grilla geométrica de t2w_axial.nii.gz.
5. dce_in_t2w.nii.gz: [Opcional] Volumen contrastado con realce arterial precoz,
   proyectado a la grilla geométrica de t2w_axial.nii.gz (si el estudio incluye contraste).

ESPECIFICACIONES TÉCNICAS Y CRITERIOS DE FÍSICA MÉDICA (INTECNUS / PI-RADS v2.1):
---------------------------------------------------------------------------------
1. Clasificación de series (por estructura normalizada o metadatos DICOM):
   - T2W Axial: Directorio '01_T2_Axial' o validar plano axial mediante el producto vectorial
     de los cosenos directores en ImageOrientationPatient (0020,0037):
       n = r_row x r_col. Si |n_z| > 0.80 y 'T2' en SeriesDescription, la orientación es axial.
   - T2W Sagital: Directorio '02_T2_Sagital' o validar plano sagital (|n_x| > 0.80) con 'T2' y 'SAG'.
   - Mapa ADC: Directorio '03_ADC' o identificar por 'ADC' / 'DIFFUSION COEFFICIENT' en SeriesDescription,
     excluyendo capturas secundarias RGB ('color', 'fusion') y mapas exponenciales ('eadc').
   - DWI Alto b: Directorio '04_DWI' o identificar por 'DWI', 'FOCUS', 'DW_SYNTHETIC' o 'DIF' (contemplando
     tanto la denominación en 1.5T 'Ax DWI FOCUS' como en 3.0T 'AXI DIF 50 1400').
     Seleccionar únicamente los cortes correspondientes al gradiente alto (b >= 1400 s/mm²).
   - DCE [Opcional]: Subcarpeta '_OPCIONALES/DCE_Liviana_PostContraste', 'LAVA' o 'DISCO'.

2. Manejo de secuencias con múltiples valores b (GE DW_Synthetic / FOCUS):
   En consolas GE, la adquisición de difusión suele apilar múltiples valores b en la misma serie
   (ej. cortes con b=50 intercalados con b=1400).
   Se deben agrupar las instancias por posición espacial ImagePositionPatient (0020,0032)
   y seleccionar exclusivamente el corte correspondiente al mayor valor b (b >= 1400 s/mm²).
   * Tags de valor b: Estándar (0018,9087) o Privado GE (0043,1039) -> primer entero mod 10000.

3. Armonización de unidades de ADC:
   El estándar PI-RADS v2.1 y Fundación INTECNUS utilizan la unidad [10^-6 mm²/s].
   Verificar la mediana de los vóxeles no nulos y re-escalar si proviene en:
   - mm²/s (mediana ~ 0.0012) -> multiplicar por 10^6.
   - 10^-3 mm²/s (mediana ~ 1.2) -> multiplicar por 10^3.
   - 10^-6 mm²/s (mediana ~ 1200) -> factor 1.0 (escala nativa).
   - 10^-9 mm²/s (mediana ~ 1200000) -> multiplicar por 10^-3.

4. Corregistro geométrico con SimpleITK:
   Las secuencias de difusión focalizada y las dinámicas poseen menor FOV o distinta resolución
   que el T2W axial. Utilizar sitk.ResampleImageFilter con interpolador lineal, transformación
   identidad y default_pixel_value = 0.0 para alinear ADC, DWI y DCE sobre la grilla del T2W axial.

5. Fase precoz de contraste dinámico (DCE) [Opcional]:
   Si se procesa la serie dinámica 4D completa, extraer la fase temporal con realce precoz (~30-45 s
   post-inyección). Si se emplea el dataset curado, utilizar directamente el volumen 3D provisto
   en '_OPCIONALES/DCE_Liviana_PostContraste'. Si el estudio es biparamétrico sin contraste,
   el pipeline omite este paso de forma transparente.
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
