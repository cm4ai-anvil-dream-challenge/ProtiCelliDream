i# BLAST-ProtiCelli baseline

A baseline submission for the CM4AI DREAM Challenge on predicting protein subcellular localization. Given reference images of a cell (microtubules, nucleus, ER) and the amino acid sequence of a protein, it generates a predicted fluorescence image of where that protein localizes.

The pipeline has two stages:

1. **Protein identification.** The amino acid sequence is searched with BLAST against a local database of reviewed human UniProt (Swiss-Prot) entries. The top hit's UniProt accession is mapped to an Ensembl gene ID and HGNC symbol with a local gene map. No network access is used at runtime.
2. **Image prediction.** The HGNC symbol and the three reference channels are passed to [ProtiCelli](https://github.com/CellProfiling/ProtiCelli), which generates the predicted image.

ProtiCelli uses a learned embedding for each protein it was trained on, so it can only predict proteins in its vocabulary (12,809 HGNC symbols in `proticelli/data/antibody_map.pkl`). Records whose protein falls outside that vocabulary are skipped and reported, not failed.

This repository is a fork of ProtiCelli, developed by the Lundberg lab. The original documentation is in [`docs/PROTICELLI_README.md`](docs/PROTICELLI_README.md).

## Repository layout

| Path | Purpose |
|---|---|
| `run_inference.py` | Runs the full pipeline over a set of input records |
| `protein_predictor.py` | Amino acid sequence to UniProt accession, Ensembl gene ID, and HGNC symbol |
| `pipeline_checks.py` | Channel assembly and optional input validation |
| `scripts/manifest_to_json.py` | Converts a manifest TSV into the input JSON |
| `scripts/build_human_blast_db.sh` | Builds the reference BLAST database zip |
| `scripts/build_human_gene_map.sh` | Builds the reference gene map zip |
| `scripts/build_weights_zip.sh` | Assembles the weights file from the model weights and reference zips |
| `scripts/split_reference_channels.py` | Splits a multichannel reference image into single-channel files (test data preparation) |

## Inputs

### Records

Each prediction is one record: three single-channel reference images plus one FASTA file holding a single amino acid sequence.

```json
[
  {
    "prediction_id": "cell_0",
    "microtubules_image": "/path/to/cell_0_microtubules.tiff",
    "er_image": "/path/to/cell_0_er.tiff",
    "nucleus_image": "/path/to/cell_0_nucleus.tiff",
    "fasta_file": "/path/to/cell_0.faa"
  }
]
```

`prediction_id` must be unique within a run; it becomes the output filename. The same reference images may appear in several records paired with different FASTA files.

Inputs are assumed to already meet ProtiCelli's requirements: matching height and width across the three channels, and pixel values normalized to ProtiCelli's expected range. No resampling or normalization happens in this pipeline.

To generate the JSON from a manifest TSV (which must include a `prediction_id` column):

```bash
python scripts/manifest_to_json.py manifest.tsv -o inputs.json
```

Relative paths in the manifest are resolved against the manifest's directory by default, or against `--path-prefix` (for example a `gs://` bucket path on Terra).

### Weights file

Everything the model needs at runtime ships in a single zip:

```
blast_proticelli_weights_v1.zip
    checkpoint/                     ProtiCelli model weights
    vae/                            ProtiCelli VAE weights
    reference/human_blast_db.zip    BLAST database
    reference/human_gene_map.zip    UniProt to Ensembl and HGNC map
```

The BLAST database and gene map are packaged with the model weights because they define which proteins this baseline can recognize, in the same way ProtiCelli's weights and vocabulary do. Each reference zip contains a `PROVENANCE.txt` recording its UniProt query, build date, and (from v2 on) the UniProt release it was downloaded from.

The weights file is not stored in git. See [Weights builds](#weights-builds) for released versions.

## Running

```bash
python run_inference.py \
  --inputs inputs.json \
  --weights_zip blast_proticelli_weights_v1.zip \
  --output_dir predictions/test_run
```

Optional arguments:

| Argument | Default | Purpose |
|---|---|---|
| `--cell_line` | none | ProtiCelli cell line name applied to every record; omit to run without cell line conditioning |
| `--seed` | none | Random seed for reproducible sampling |
| `--num_inference_steps` | 50 | Diffusion sampling steps |
| `--batch_size` | 4 | ProtiCelli prediction batch size |
| `--weights_dir` | `./weights` | Where model weights are extracted |
| `--reference_data_dir` | `./reference_data` | Where the BLAST database and gene map are extracted |
| `--antibody_map` | package copy | Override path to ProtiCelli's vocabulary file |

Weights always extract to a run-local directory, never into the installed `proticelli` package, so each run uses the weights file it was given. Any `LOCAL_BLAST_DB` or `LOCAL_GENE_MAP` environment variables left over from development are ignored for the same reason.

## Outputs

All outputs are written flat into `--output_dir`:

- `{prediction_id}.tiff`, one per record that could be predicted
- `prediction_results.tsv`, one row per input record, predicted or not

### Status values

| Status | Meaning |
|---|---|
| `predicted` | Image generated |
| `no_blast_hit` | BLAST ran but returned no hit |
| `no_hgnc_symbol` | A UniProt hit was found, but no HGNC symbol mapped to it |
| `not_in_model_vocabulary` | The protein was identified, but ProtiCelli was not trained on it |
| `predictor_error` | BLAST or gene mapping raised an error (details in `predictor_error`) |

If every record returns `predictor_error`, the run fails, since that points to a broken environment (for example a missing `blastp` binary or a malformed reference zip) rather than to the data.

### Results columns

| Column | Content |
|---|---|
| `prediction_id` | From the input record |
| `status` | See above |
| `output_file` | Image filename, empty if not predicted |
| `predicted_uniprot_accession` | Top BLAST hit |
| `predicted_ensembl_gene_id` | Mapped Ensembl gene ID |
| `predicted_hgnc_symbol` | Mapped HGNC symbol, passed to ProtiCelli |
| `percent_identity`, `e_value`, `alignment_length` | Top hit statistics |
| `gene_candidate_count`, `mapping_ambiguous` | Whether the accession mapped to more than one Ensembl gene |
| `search_database` | BLAST database path used |
| `predictor_pipeline_version` | Protein predictor version |
| `predictor_error` | Error message, if any |
| `cell_line`, `seed`, `num_inference_steps` | Run settings |
| `run_id` | Short random identifier shared by all rows of one run |

## Building the weights file

1. Build the reference zips with `scripts/build_human_blast_db.sh` and `scripts/build_human_gene_map.sh` (usage in each script's header). Both pull from the current UniProt release, so rebuilding later produces different content; keep built zips rather than relying on rebuilding them.
2. Obtain the ProtiCelli `checkpoint/` and `vae/` folders, for example by running ProtiCelli's `download_checkpoints()`, which fetches them from the Lundberg lab.
3. Assemble the weights file:

```bash
scripts/build_weights_zip.sh proticelli \
  human_blast_db/human_blast_db.zip \
  human_gene_map/human_gene_map.zip \
  blast_proticelli_weights_v1.zip
```

The script prints the top-level contents and the SHA-256 checksum. Record every build in the table below.

## Weights builds

| Version | Built | UniProt release (date) | ProtiCelli weights | SHA-256 | Location | Notes |
|---|---|---|---|---|---|---|
| v1 | 2026-09-28 | 2026_03 (2026-09-02), inferred |  Lundberg lab default `download_checkpoints()` URLs | `19fc815a99449e80eb2c703602aa58a5c92103225efb8203dca738b9cd9c0566` | TBD | Verified end to end on two test records. Includes ProtiCelli training state files. UniProt release inferred: reference zips built 2026-09-23, when 2026_03 was current; not recorded by the v1 build scripts. |

## Open items

- **Output pixel value range.** Inputs are normalized to roughly [-1, 1.5], but observed outputs fall in [0, 0.04]. Pending clarification from the Lundberg lab.
- **Weights file size.** `checkpoint/` includes training state (`optimizer.bin`, `scheduler.bin`, `random_states_0.pkl`) that inference likely does not need. Excluding it could substantially reduce the 6.5 GB file; not yet tested.
- **Handling of skipped records.** Skipping out-of-vocabulary proteins and failing only on all-error runs are provisional choices; how skipped records are scored is a challenge design question.
- **`cell_line`.** Currently a single optional value applied to every record in a run.
- **Containerization and WDL.** Docker image and WDL workflow in progress.