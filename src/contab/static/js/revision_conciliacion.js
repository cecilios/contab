
document.addEventListener("DOMContentLoaded", () => {
    const formulario = document.getElementById(
        "revision-manual-formulario"
    );

    if (!formulario) {
        return;
    }

    const previstos = Array.from(
        formulario.querySelectorAll(
            'input[name="previsto_ids"][type="checkbox"]'
        )
    );

    const bancarios = Array.from(
        formulario.querySelectorAll(
            'input[name="bancario_ids"][type="checkbox"]'
        )
    );

    const totalPrevistos = document.getElementById(
        "revision-manual-total-previstos"
    );

    const totalBancarios = document.getElementById(
        "revision-manual-total-bancarios"
    );

    const diferencia = document.getElementById(
        "revision-manual-diferencia"
    );

    const botonConfirmar = formulario.querySelector(
        ".revision-manual__boton-confirmar"
    );

    const formatear = (centimos) =>
        (centimos / 100).toLocaleString("es-ES", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }) + " €";

    const totalSeleccionado = (casillas) =>
        casillas.reduce(
            (total, casilla) =>
                total + (
                    casilla.checked
                        ? Number(casilla.dataset.importe)
                        : 0
                ),
            0
        );

    const contarSeleccionados = (casillas) =>
        casillas.filter((casilla) => casilla.checked).length;

    function actualizarTotales() {
        const importePrevistos = totalSeleccionado(previstos);
        const importeBancarios = totalSeleccionado(bancarios);

        const cantidadPrevistos = contarSeleccionados(previstos);
        const cantidadBancarios = contarSeleccionados(bancarios);

        const diferenciaCentimos =
            importeBancarios - importePrevistos;

        totalPrevistos.textContent = formatear(importePrevistos);
        totalBancarios.textContent = formatear(importeBancarios);
        diferencia.textContent = formatear(diferenciaCentimos);

        const hayAmbosLados =
            cantidadPrevistos > 0 && cantidadBancarios > 0;

        const esMuchosAMuchos =
            cantidadPrevistos > 1 && cantidadBancarios > 1;

        const importesCoinciden =
            importePrevistos === importeBancarios;

        botonConfirmar.disabled = !(
            hayAmbosLados
            && !esMuchosAMuchos
            && importesCoinciden
        );

        diferencia.classList.toggle(
            "revision-manual__valor--descuadrado",
            hayAmbosLados && !importesCoinciden
        );
    }

    for (const casilla of [...previstos, ...bancarios]) {
        casilla.addEventListener(
            "change",
            actualizarTotales
        );
    }

    actualizarTotales();
});
