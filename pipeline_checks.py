import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from tifffile import imread

def validate_image_file(
    filename,
    data_dir,
    expected_hw,
    expected_dtype,
    channel_axis=-1,
    valid_channel_counts=(3, 4),
    expected_range=(-1.0, 1.0),
    range_tolerance=0.05,
):
    """Load and validate a single multi-channel reference image file against known-good specs."""
    path = os.path.join(data_dir, filename)
    img = imread(path)

    n_channels = img.shape[channel_axis]
    hw_shape = tuple(s for i, s in enumerate(img.shape) if i != (channel_axis % img.ndim))

    img_min, img_max = float(img.min()), float(img.max())
    issues = []

    if n_channels not in valid_channel_counts:
        issues.append(f"channel count {n_channels} not in {valid_channel_counts}")
    if hw_shape != expected_hw:
        issues.append(f"H/W {hw_shape} != expected {expected_hw}")
    if img.dtype != expected_dtype:
        issues.append(f"dtype {img.dtype} != expected {expected_dtype}")
    if img_min < expected_range[0] - range_tolerance:
        issues.append(f"min {img_min:.3f} below expected {expected_range[0]}")
    if img_max > expected_range[1] + range_tolerance:
        issues.append(f"max {img_max:.3f} above expected {expected_range[1]}")

    passed = len(issues) == 0

    return img, {
        "filename": filename, "shape": img.shape, "n_channels": n_channels,
        "dtype": img.dtype, "min": img_min, "max": img_max,
        "passed": passed,
        "issues": "; ".join(issues) if issues else "",
    }

def validate_image_files(
    filenames,
    data_dir,
    expected_hw=None,
    expected_dtype=None,
    csv_path=None,
    only_issues_to_csv=False,
    **kwargs,
):
    """Validate a batch of files. Returns (passing_images, report_df) — failed files excluded from images."""
    images, records = [], []

    if expected_hw is None or expected_dtype is None:
        probe = imread(os.path.join(data_dir, filenames[0]))
        axis = kwargs.get("channel_axis", -1)
        if expected_hw is None:
            expected_hw = tuple(s for i, s in enumerate(probe.shape) if i != (axis % probe.ndim))
        if expected_dtype is None:
            expected_dtype = probe.dtype

    for fname in filenames:
        img, record = validate_image_file(fname, data_dir, expected_hw, expected_dtype, **kwargs)
        if record["passed"]:
            images.append(img)
        records.append(record)  # every file still goes in the report, pass or fail

    report_df = pd.DataFrame(records)
    if csv_path is not None:
        out_df = report_df[~report_df["passed"]] if only_issues_to_csv else report_df
        out_df.to_csv(csv_path, index=False)
        print(f"Wrote {len(out_df)} rows to {csv_path}")

    return images, report_df


def show_predictions_for_cell(
        cell_index, 
        ref_filenames, 
        ref_images_b, 
        images, 
        protein_names, 
        cell_line_names, 
        results,
):
    """Display a reference image alongside all its protein/cell-line predictions.

    Parameters
    ----------
    cell_index : int
        Index into the sorted set of unique reference filenames.
    ref_filenames : list of str
        Filenames corresponding to each entry in `images`/`protein_names`/`cell_line_names`.
    ...

    Returns
    -------
    matplotlib.figure.Figure
        The generated comparison figure.
    """
     
    # Which reference filename are we looking at?
    target_filename = sorted(set(ref_filenames))[cell_index]
    ref_img = ref_images_b[cell_index]

    # Find all predictions matching this reference cell
    matches = [
        (p, c, results.images[i])
        for i, (fn, p, c) in enumerate(zip(ref_filenames, protein_names, cell_line_names))
        if fn == target_filename
    ]

    n = len(matches)
    fig, axes = plt.subplots(1, n + 1, figsize=(3 * (n + 1), 3))

    axes[0].imshow(ref_img)
    axes[0].set_title(f"Reference\n{target_filename}")
    axes[0].axis("off")

    for ax, (protein, cell_line, pred_img) in zip(axes[1:], matches):
        ax.imshow(pred_img)
        ax.set_title(f"{protein}\n{cell_line}")
        ax.axis("off")

    plt.tight_layout()
    plt.show()

    return fig
