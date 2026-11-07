import os
import sys
import json
import subprocess
import argparse
from pathlib import Path


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Pipeline Cuantitativo de RM de Próstata — Fundación INTECNUS (Maestría en Física Médica)"
    )
    # Entrada de datos: carpeta de estudio completa o series individuales
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dicom_dir", help="Directorio del estudio del paciente (con carpetas normalizadas o estudio crudo).")
    group.add_argument("--manual", action="store_true", help="Ingreso manual de series específicas.")

    parser.add_argument("--t2w", help="Ruta a T2W Axial (NIfTI o carpeta DICOM). Requerido con --manual.")
    parser.add_argument("--t2_sag", default=None, help="[Recomendado] Ruta a T2W Sagital (NIfTI o carpeta DICOM).")
    parser.add_argument("--adc", help="Ruta a Mapa ADC (NIfTI o carpeta DICOM). Requerido con --manual.")
    parser.add_argument("--dwi", help="Ruta a DWI alto b (NIfTI o carpeta DICOM). Requerido con --manual.")
    parser.add_argument("--dce", default=None, help="[Opcional] Ruta a serie con contraste (NIfTI o carpeta DICOM).")
    parser.add_argument("--mask", default=None, help="[Opcional] Máscara corregida externamente (NIfTI). Si se define, salta la FASE 2.")

    parser.add_argument("--output_dir", default="./output", help="Directorio para guardar resultados y reportes.")
    parser.add_argument("--psa", type=float, default=None, help="Valor de PSA sérico de admisión del paciente (ng/mL).")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"], help="Dispositivo para inferencia.")
    parser.add_argument("--study_id", default=None, help="Identificador del estudio / paciente.")

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

    # Inferencia automática de study_id y PSA desde datos_admision.json si están disponibles
    study_id = args.study_id
    psa_val = args.psa

    if args.dicom_dir:
        dicom_path = Path(args.dicom_dir)
        if study_id is None:
            study_id = dicom_path.name

        # Carga automática del PSA de admisión si no fue especificado por CLI
        json_admision = dicom_path / "datos_admision.json"
        if json_admision.exists() and psa_val is None:
            try:
                with open(json_admision, "r", encoding="utf-8") as jf:
                    adm_info = json.load(jf)
                    psa_val = adm_info.get("psa_ng_ml")
                    if psa_val is not None:
                        print(f"[INFO] PSA sérico cargado desde {json_admision.name}: {psa_val} ng/mL")
            except Exception as e:
                print(f"[WARN] No se pudo leer {json_admision}: {e}")

    if study_id is None:
        study_id = "ESTUDIO_001"

    print("=" * 75)
    print("PIPELINE CUANTITATIVO DE RM PROSTÁTICA — FUNDACIÓN INTECNUS (PI-RADS v2.1)")
    print(f"Estudio: {study_id} | PSA Ingreso: {psa_val if psa_val is not None else 'No provisto'} ng/mL | Dispositivo: {args.device}")
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
        if args.t2_sag:
            cmd_fase1 += ["--t2_sag", args.t2_sag]
        if args.dce:
            cmd_fase1 += ["--dce", args.dce]

    run_command(cmd_fase1, "FASE 1: Ingesta y Corregistro (src/ingest_dicom.py)")

    t2_path = out_dir / "t2w_axial.nii.gz"
    t2_sag_path = out_dir / "t2w_sagital.nii.gz"
    adc_path = out_dir / "adc_in_t2w.nii.gz"
    dwi_path = out_dir / "dwi_high_b_in_t2w.nii.gz"
    dce_path = out_dir / "dce_in_t2w.nii.gz"

    # -------------------------------------------------------------------------
    # FASE 2: Segmentación Zonal con Deep Learning (src/segmentation.py)
    # -------------------------------------------------------------------------
    if args.mask:
        mask_path = Path(args.mask)
        if not mask_path.exists():
            sys.exit(f"Error: La máscara especificada no existe: {mask_path}")
        print(f"\n[INFO] Empleando máscara provista / corregida: {mask_path} (omitiendo inferencia de FASE 2).")
    else:
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
    if t2_sag_path.exists():
        cmd_fase3 += ["--t2_sag", str(t2_sag_path)]
    if dwi_path.exists():
        cmd_fase3 += ["--dwi", str(dwi_path)]
    if psa_val is not None:
        cmd_fase3 += ["--psa", str(psa_val)]
    if dce_path.exists():
        cmd_fase3 += ["--dce", str(dce_path)]

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
        "--study_id", study_id,
    ]
    if t2_sag_path.exists():
        cmd_fase4 += ["--t2_sag", str(t2_sag_path)]
    if dce_path.exists():
        cmd_fase4 += ["--dce", str(dce_path)]

    # Si se especificó carpeta DICOM original o T2, pasar referencia para DICOM SEG
    if args.dicom_dir:
        t2_dcm_ref = Path(args.dicom_dir) / "01_T2_Axial"
        if t2_dcm_ref.exists():
            cmd_fase4 += ["--dicom_ref", str(t2_dcm_ref)]

    run_command(cmd_fase4, "FASE 4: Reporte Clínico Multipanel (src/report_generator.py)")

    print("\n" + "=" * 75)
    print("PIPELINE COMPLETADO CON ÉXITO")
    print(f"Resultados guardados en: {out_dir.resolve()}")
    print("=" * 75)


if __name__ == "__main__":
    main()
