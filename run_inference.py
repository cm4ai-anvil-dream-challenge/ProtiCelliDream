# run_inference.py
import argparse
from itertools import product
from pathlib import Path
import csv
import uuid

from skimage.io import imsave

import pipeline_checks as check
from proticelli import Model


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint_zip", required=True, help="file:// or https:// URL")
    parser.add_argument("--vae_zip", required=True, help="file:// or https:// URL")
    parser.add_argument("--image_dir", required=True, help="Directory containing reference images")
    parser.add_argument("--image_files", nargs="+", required=True, help="Filenames within image_dir to use")
    parser.add_argument("--proteins", nargs="+", required=True)
    parser.add_argument("--cell_lines", nargs="+", required=True)
    parser.add_argument("--num_inference_steps", type=int, default=50)
    parser.add_argument("--batch_size", type=int, default=4)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--expected_range", type=float, nargs=2, default=[-1.0, 1.5])
    parser.add_argument(
        "--min_valid_fraction", type=float, default=0.0,
        help="Minimum fraction of images that must pass validation, or the run aborts."
    )
    return parser.parse_args()

def main():
    args = parse_args()

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    paths = Model.download_checkpoints(
        checkpoint_url=args.checkpoint_zip,
        vae_url=args.vae_zip,
    )
    model = Model(**paths)

    ref_images, report = check.validate_image_files(
        filenames=args.image_files,
        data_dir=args.image_dir,
        expected_range=tuple(args.expected_range),
        csv_path=str(Path(args.output_dir) / "validation_report.csv"),
        only_issues_to_csv=False,
    )
    passed_filenames = report[report["passed"] == True]["filename"].tolist()

    if len(passed_filenames) != len(ref_images):
        raise RuntimeError(
            f"Validation pairing mismatch: {len(passed_filenames)} filenames vs {len(ref_images)} images"
        )

    fraction_passed = len(ref_images) / len(args.image_files)
    if fraction_passed < args.min_valid_fraction:
        raise RuntimeError(
            f"Only {fraction_passed:.1%} of images passed validation "
            f"({len(ref_images)}/{len(args.image_files)}), below required {args.min_valid_fraction:.1%}"
        )

    if len(ref_images) == 0:
        raise RuntimeError("No images passed validation — nothing to predict on")

    file_image_pairs = list(zip(passed_filenames, ref_images))
    combos = list(product(file_image_pairs, args.proteins, args.cell_lines))

    ref_filenames_out = [c[0][0] for c in combos]
    images = [c[0][1] for c in combos]
    protein_names = [c[1] for c in combos]
    cell_line_names = [c[2] for c in combos]

    results = model.predict(
        images=images,
        protein_names=protein_names,
        cell_line_names=cell_line_names,
        num_inference_steps=args.num_inference_steps,
        batch_size=args.batch_size,
        seed=args.seed,
    )

    expected = len(combos)
    actual = len(results.images)
    if actual != expected:
        raise RuntimeError(
            f"Output count mismatch: expected {expected} "
            f"({len(passed_filenames)} images x {len(args.proteins)} proteins x {len(args.cell_lines)} cell_lines), "
            f"got {actual}"
        )

    # TL - you are here!
    run_id = uuid.uuid4().hex[:8]
    output_dir = Path(args.output_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    manifest_rows = []
    for ref_fn, cell_line, protein, img in zip(ref_filenames_out, cell_line_names, protein_names, results.images):
        ref_stem = Path(ref_fn).stem
        save_path = output_dir / f"{ref_stem}_{cell_line}_{protein}.tiff"
        imsave(save_path, img)
        manifest_rows.append({
            "run_id": run_id,
            "output_directory": str(output_dir),
            "output_file": save_path.name,
            "reference_image": ref_fn,
            "protein": protein,
            "cell_line": cell_line,
            "seed": args.seed,
            "num_inference_steps": args.num_inference_steps,
            "batch_size": args.batch_size,
        })
        print(f"Saved: {save_path}")

    manifest_path = output_dir / "manifest.csv"
    with open(manifest_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=manifest_rows[0].keys())
        writer.writeheader()
        writer.writerows(manifest_rows)
    print(f"Wrote manifest: {manifest_path}")

if __name__ == "__main__":
    main()

