"""
MÓDULO DE SEGMENTACIÓN ZONAL DE PRÓSTATA (MONAI / PyTorch)
===========================================================

PROPÓSITO DEL SCRIPT:
---------------------
Ejecutar la inferencia de segmentación anatómica bi-zonal a partir del volumen
estructural T2W Axial (t2w_axial.nii.gz) utilizando un modelo preentrenado de Deep Learning,
produciendo una máscara 3D alineada en la misma grilla geométrica.

DATOS DE ENTRADA:
-----------------
1. --input: Ruta al volumen NIfTI T2W Axial preprocesado (t2w_axial.nii.gz).
2. --device: Dispositivo de cómputo para la inferencia ('auto', 'cpu' o 'cuda').

DATOS DE SALIDA:
----------------
1. --output: Ruta de destino para guardar la máscara NIfTI 3D (prostate_mask.nii.gz).
   Etiquetas requeridas por el protocolo PI-RADS:
     - Etiqueta 1: Zona de Transición / Central (TZ).
     - Etiqueta 2: Zona Periférica (PZ).
     - Etiqueta 0: Fondo periprostático.

ESPECIFICACIONES DEL MODELO Y CONSIDERACIONES DE HARDWARE:
----------------------------------------------------------
1. Modelo preentrenado:
   Utilizar el bundle 'prostate_mri_anatomy' del Model Zoo de MONAI
   (https://github.com/Project-MONAI/model-zoo/tree/dev/models/prostate_mri_anatomy).
   - Descarga automática: monai.bundle.download(name="prostate_mri_anatomy", bundle_dir=...)
   - Configuración: inference.json o inference.yaml provisto por el bundle.
   - Algoritmo de inferencia: sliding_window_inference para volúmenes 3D.

2. Gestión de memoria de GPU (VRAM):
   Las redes 3D de segmentación médica requieren un volumen significativo de memoria.
   Si la GPU disponible posee menos de 4 GB de VRAM libre, el script debe conmutar
   automáticamente a ejecución en CPU ('cpu') para evitar caídas por CUDA Out-of-Memory (OOM).

3. Geometría espacial estricta:
   La máscara de salida (prostate_mask.nii.gz) DEBE conservar exactamente la misma matriz
   de dirección (Direction), origen (Origin) y espaciado de vóxel (Spacing) del volumen
   T2W de entrada para garantizar el correcto enmascaramiento downstream.
"""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Segmentación zonal de próstata con bundle MONAI (prostate_mri_anatomy)."
    )
    parser.add_argument("--input", required=True, help="Ruta al volumen NIfTI T2W Axial de entrada.")
    parser.add_argument("--output", required=True, help="Ruta destino para guardar prostate_mask.nii.gz.")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"], help="Dispositivo para inferencia.")

    args = parser.parse_args()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Implementación de la inferencia con MONAI bundle
    pass


if __name__ == "__main__":
    main()
