#!/usr/bin/env bash
# build_human_blast_db.sh
#
# Downloads the reviewed (Swiss-Prot) human proteome from UniProt's REST
# API and builds a local blastp database from it, for use as
# LOCAL_BLAST_DB with protein_predictor.py's SEARCH_BACKEND=local.
#
# NOTE: the download step below has not been run or verified end to end,
# it's built from UniProt's documented REST query syntax, not confirmed
# against a live response. If the query comes back empty or malformed,
# the likely culprit is the query string itself, check
# https://www.uniprot.org/help/query-fields for the current field names.
#
# Usage:
#   ./build_human_blast_db.sh [output_dir]
#
# Requires: curl, gunzip, makeblastdb (from ncbi-blast+, e.g.
#   conda install -c bioconda blast   or   brew install blast)

set -euo pipefail

OUT_DIR="${1:-./human_blast_db}"
mkdir -p "$OUT_DIR"

FASTA_GZ="$OUT_DIR/human_reviewed.fasta.gz"
FASTA="$OUT_DIR/human_reviewed.fasta"
DB_PREFIX="$OUT_DIR/human_reviewed_swissprot"

echo "Downloading reviewed human proteome from UniProt..."
curl -sS -o "$FASTA_GZ" \
  "https://rest.uniprot.org/uniprotkb/stream?query=%28organism_id%3A9606%29%20AND%20%28reviewed%3Atrue%29&format=fasta&compressed=true"

echo "Decompressing..."
gunzip -f "$FASTA_GZ"

SEQ_COUNT=$(grep -c "^>" "$FASTA" || true)
echo "Downloaded $SEQ_COUNT sequences to $FASTA"

if [ "$SEQ_COUNT" -lt 1000 ]; then
  echo "WARNING: expected roughly 20000 reviewed human sequences, got $SEQ_COUNT." >&2
  echo "This usually means the query string needs adjusting, check the file contents before proceeding." >&2
fi

echo "Building blastp database at $DB_PREFIX ..."
makeblastdb -in "$FASTA" -dbtype prot -out "$DB_PREFIX"

PROVENANCE_FILE="$OUT_DIR/PROVENANCE.txt"
{
  echo "Reference database: reviewed human UniProtKB Swiss-Prot BLAST database"
  echo "Generated (UTC): $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "Source query URL: https://rest.uniprot.org/uniprotkb/stream?query=%28organism_id%3A9606%29%20AND%20%28reviewed%3Atrue%29&format=fasta&compressed=true"
  echo "Sequences downloaded: $SEQ_COUNT"
  echo ""
  echo "blastp version:"
  blastp -version
  echo ""
  echo "makeblastdb version:"
  makeblastdb -version
} > "$PROVENANCE_FILE"
echo "Wrote provenance to $PROVENANCE_FILE"

ZIP_FILE="$OUT_DIR/human_blast_db.zip"
(cd "$OUT_DIR" && zip -q "$(basename "$ZIP_FILE")" "$(basename "$DB_PREFIX")".* PROVENANCE.txt)
echo "Wrote $ZIP_FILE"

echo ""
echo "Done. To use this database with protein_predictor.py:"
echo "  export SEARCH_BACKEND=local"
echo "  export LOCAL_BLAST_DB=$DB_PREFIX"
echo "  python protein_predictor.py manifest.tsv predicted_manifest.tsv --fasta-dir /path/to/faa"