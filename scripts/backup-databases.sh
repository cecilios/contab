#!/usr/bin/env bash
#
# Script para backups de las bases de datos que haya en data/.
# - copias coherentes aunque SQLite esté abierto
# - nombres fechados automáticamente
# - copia de todas las bases en data/
# - comprobación de integridad mediante sqlite3 .backup y PRAGMA quick_check.
# - Evita sobrescribir una copia con el mismo nombre.
# - Exige exactamente un argumento MSG.
# - En MSG rechaza espacios, incluso si se pasan entre comillas y admite letras, 
#   números, puntos, guiones y guiones bajos.
# - Almacena los backups en backups/.
#
# Uso habitual:  ./scripts/backup-databases.sh MSG
#   ej.: ./scripts/backup_databases.sh antes-de-ampliar-apuntes-contables
#

set -Eeuo pipefail

script_dir="$(
    CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
)"
project_dir="$(dirname -- "$script_dir")"

if (( $# != 1 )); then
    echo "Uso: $0 msg" >&2
    echo "Ejemplo: $0 antes-de-ampliar-apuntes-contables" >&2
    echo "Error: debe indicarse un único mensaje sin espacios." >&2
    exit 2
fi

message="$1"

if [[ -z "$message" || "$message" =~ [[:space:]] ]]; then
    echo "Error: el mensaje no puede estar vacío ni contener espacios." >&2
    exit 2
fi

if [[ ! "$message" =~ ^[[:alnum:]_.-]+$ ]]; then
    echo "Error: el mensaje sólo puede contener letras, números, puntos, guiones y guiones bajos." >&2
    exit 2
fi

data_dir="$project_dir/data"
backup_dir="$project_dir/backups"

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

backup_date="$(date '+%Y-%m-%d')"
created=0

for database in "${databases[@]}"; do
    filename="$(basename -- "$database")"
    name="${filename%.db}"
    destination="$backup_dir/${name}-${backup_date}-${message}.db"

    if [[ -e "$destination" ]]; then
        echo "Error: la copia ya existe: $destination" >&2
        exit 1
    fi

    temporary="$(
        mktemp "$backup_dir/.${name}-${backup_date}-${message}.XXXXXX.db"
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
