#!/usr/bin/env bash
#
#script para backups de las bases de datos que haya en data/.
# Asegura:
# - copias coherentes aunque SQLite esté abierto;
# - nombres fechados automáticamente;
# - copia de todas las bases;
# - comprobación de integridad;
# - menos riesgo de sobrescribir una copia anterior.
#
# Uso habitual:  .scripts/backup-databases.sh

set -Eeuo pipefail

script_dir="$(
    CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
)"
project_dir="$(dirname -- "$script_dir")"

data_dir="${1:-$project_dir/data}"
backup_dir="${2:-$project_dir/backups}"

if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "Error: no se encuentra el programa sqlite3." >&2
    exit 1
fi

if [[ ! -d "$data_dir" ]]; then
    echo "Error: no existe el directorio de datos: $data_dir" >&2
    exit 1
fi

mkdir -p -- "$backup_dir"

shopt -s nullglob
databases=("$data_dir"/*.db)

if (( ${#databases[@]} == 0 )); then
    echo "Error: no hay bases de datos .db en: $data_dir" >&2
    exit 1
fi

timestamp="$(date '+%Y%m%d-%H%M%S')"
created=0

for database in "${databases[@]}"; do
    filename="$(basename -- "$database")"
    name="${filename%.db}"
    destination="$backup_dir/${name}-${timestamp}.db"
    temporary="$(
        mktemp "$backup_dir/.${name}-${timestamp}.XXXXXX.db"
    )"

    cleanup_temporary() {
        if [[ -n "${temporary:-}" && -e "$temporary" ]]; then
            rm -f -- "$temporary"
        fi
    }

    trap cleanup_temporary EXIT

    sqlite3 "$database" ".backup '$temporary'"

    check="$(sqlite3 "$temporary" 'PRAGMA quick_check;')"

    if [[ "$check" != "ok" ]]; then
        echo "Error: la copia de $filename no superó quick_check." >&2
        exit 1
    fi

    mv -- "$temporary" "$destination"
    temporary=""
    trap - EXIT

    echo "Copia creada: $destination"
    ((created += 1))
done

echo "Proceso terminado: $created base(s) de datos copiadas."
