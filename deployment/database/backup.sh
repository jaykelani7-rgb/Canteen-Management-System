#!/usr/bin/env bash
# Operator-invoked only. Connection/password live in private libpq service files.
set -euo pipefail
umask 077

usage() {
  printf '%s\n' 'Usage: backup.sh SERVICE ABSOLUTE_OUTPUT_DIRECTORY AGE_PUBLIC_RECIPIENT' \
    'Example: backup.sh canteen_source /secure/backups age1...' \
    'Requires pg_dump, age and sha256sum. Never overwrites an existing archive.'
}
if [[ ${1:-} == --help ]]; then usage; exit 0; fi
if [[ $# != 3 ]]; then usage >&2; exit 2; fi
service=$1
output_directory=$2
recipient=$3
if [[ ! $service =~ ^[A-Za-z][A-Za-z0-9_-]{0,63}$ ]]; then
  printf '%s\n' 'Specify a named private libpq service, not a connection URL.' >&2; exit 2
fi
if [[ $output_directory != /* || ! -d $output_directory || -L $output_directory ]]; then
  printf '%s\n' 'The output must be an existing absolute private directory without a symlink.' >&2; exit 2
fi
if [[ $recipient != age1* || $recipient == *[[:space:]]* ]]; then
  printf '%s\n' 'Specify a public age recipient; keep the decryption identity off this host.' >&2; exit 2
fi
for executable in pg_dump age sha256sum; do command -v "$executable" >/dev/null; done
output_directory=$(cd -- "$output_directory" && pwd -P)
archive="$output_directory/canteen-$service-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump.age"
set -o noclobber
if ! pg_dump --no-password --format=custom --dbname="service=$service" | age --encrypt --recipient "$recipient" > "$archive"; then
  printf '%s\n' 'Backup failed. A partial archive may remain; do not upload it as a completed backup.' >&2
  exit 1
fi
chmod 600 -- "$archive"
(cd -- "$output_directory" && sha256sum -- "$(basename -- "$archive")") > "$archive.sha256"
chmod 600 -- "$archive.sha256"
printf 'Encrypted archive: %s\nChecksum file: %s\n' "$archive" "$archive.sha256"
printf '%s\n' 'Next: copy off-host, check the checksum, decrypt/list and restore into an explicitly selected empty recovery database.'
