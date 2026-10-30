import os
import sys
import subprocess
import argparse
from pathlib import Path


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Pipeline Cuantitativo de RM de Próstata — Fundación INTECNUS (Maestría en Física Médica)"
    )
    # Entrada de datos: carpeta de estudio completa o series individuales
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dicom_dir", help="Directorio con el estudio DICOM crudo completo.")
    group.add_argument("--manual", action="store_true", help="Ingreso manual de las 3 series específicas.")

    parser.add_argument("--t2w", help="Ruta a T2W Axial (NIfTI o carpeta DICOM). Requerido con --manual.")
    parser.add_argument("--adc", help="Ruta a Mapa ADC (NIfTI o carpeta DICOM). Requerido con --manual.")
    parser.add_argument("--dwi", help="Ruta a DWI alto b (NIfTI o carpeta DICOM). Requerido con --manual.")

    parser.add_argument("--output_dir", default="./output", help="Directorio para guardar resultados y reportes.")
    parser.add_argument("--psa", type=float, default=None, help="Valor de PSA sérico del paciente (ng/mL).")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"], help="Dispositivo para inferencia.")
    parser.add_argument("--study_id", default="ESTUDIO_001", help="Identificador del estudio / paciente.")

    return parser.parse_args()


def run_command(cmd, step_name):
    print(f"\n>>> Ejecutando: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"\n[ERROR] Falló la ejecución de '{step_name}' (Código de salida: {result.returncode}).")


def main():
    args = parse_arguments()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    python_bin = sys.executable

    print("=" * 75)
    print("PIPELINE CUANTITATIVO DE RM PROSTÁTICA — FUNDACIÓN INTECNUS")
    print(f"Estudio: {args.study_id} | PSA: {args.psa} ng/mL | Dispositivo: {args.device}")
    print("=" * 75)

    # -------------------------------------------------------------------------
    # FASE 1: Ingesta, Filtrado y Corregistro (src/ingest_dicom.py)
    # -------------------------------------------------------------------------
    cmd_fase1 = [python_bin, "src/ingest_dicom.py", "--output_dir", str(out_dir)]
    if args.dicom_dir:
        cmd_fase1 += ["--dicom_dir", args.dicom_dir]
    else:
        if not (args.t2w and args.adc and args.dwi):
            sys.exit("Error: El modo --manual requiere especificar --t2w, --adc y --dwi.")
        cmd_fase1 += ["--manual", "--t2w", args.t2w, "--adc", args.adc, "--dwi", args.dwi]

    run_command(cmd_fase1, "FASE 1: Ingesta y Corregistro (src/ingest_dicom.py)")

    t2_path = out_dir / "t2w_axial.nii.gz"
    adc_path = out_dir / "adc_in_t2w.nii.gz"
    dwi_path = out_dir / "dwi_high_b_in_t2w.nii.gz"

    # -------------------------------------------------------------------------
    # FASE 2: Segmentación Zonal con Deep Learning (src/segmentation.py)
    # -------------------------------------------------------------------------
    mask_path = out_dir / "prostate_mask.nii.gz"
    cmd_fase2 = [
        python_bin, "src/segmentation.py",
        "--input", str(t2_path),
        "--output", str(mask_path),
        "--device", args.device,
    ]
    run_command(cmd_fase2, "FASE 2: Segmentación Zonal (src/segmentation.py)")

    # -------------------------------------------------------------------------
    # FASE 3: Morfometría 3D, Elipsoide, PSAD y Difusión (src/morphometry.py)
    # -------------------------------------------------------------------------
    cmd_fase3 = [
        python_bin, "src/morphometry.py",
        "--t2w", str(t2_path),
        "--adc", str(adc_path),
        "--mask", str(mask_path),
        "--output_dir", str(out_dir),
    ]
    if args.psa is not None:
        cmd_fase3 += ["--psa", str(args.psa)]

    run_command(cmd_fase3, "FASE 3: Morfometría y Difusión (src/morphometry.py)")

    # -------------------------------------------------------------------------
    # FASE 4: Reporte Clínico Multipanel e Informe Estructurado (src/report_generator.py)
    # -------------------------------------------------------------------------
    morph_json_path = out_dir / "morphometry_results.json"
    cmd_fase4 = [
        python_bin, "src/report_generator.py",
        "--t2w", str(t2_path),
        "--adc", str(adc_path),
        "--dwi", str(dwi_path),
        "--mask", str(mask_path),
        "--metrics", str(morph_json_path),
        "--output_dir", str(out_dir),
        "--study_id", args.study_id,
    ]
    run_command(cmd_fase4, "FASE 4: Reporte Clínico Multipanel (src/report_generator.py)")

    print("\n" + "=" * 75)
    print("PIPELINE EJECUTADO")
    print(f"Resultados guardados en: {out_dir.resolve()}")
    print("=" * 75)


if __name__ == "__main__":
    main()
