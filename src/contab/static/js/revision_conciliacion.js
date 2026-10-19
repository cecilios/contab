
document.addEventListener("DOMContentLoaded", () => {
    const formularios = document.querySelectorAll(
        ".revision-manual__formulario"
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

    function configurarBoton(boton, visible, habilitado) {
        boton.hidden = !visible;
        boton.disabled = !habilitado;
    }

    function inicializarFormulario(formulario) {
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

        const totalPrevistos = formulario.querySelector(
            ".revision-manual__total-previstos"
        );

        const totalBancarios = formulario.querySelector(
            ".revision-manual__total-bancarios"
        );

        const diferencia = formulario.querySelector(
            ".revision-manual__diferencia"
        );

        const botonExacta = formulario.querySelector(
            ".revision-manual__boton-confirmar"
        );

        const botonParcial = formulario.querySelector(
            ".revision-manual__boton-parcial"
        );

        const botonDiferencia = formulario.querySelector(
            ".revision-manual__boton-diferencia"
        );

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

            const confirmarExacta =
                hayAmbosLados
                && !esMuchosAMuchos
                && importesCoinciden;

            const confirmarDiferencia =
                hayAmbosLados
                && !esMuchosAMuchos
                && !importesCoinciden
                && importePrevistos > 0
                && importeBancarios > 0;

            configurarBoton(
                botonExacta,
                !confirmarDiferencia,
                confirmarExacta
            );

            configurarBoton(
                botonParcial,
                confirmarDiferencia,
                confirmarDiferencia
            );

            configurarBoton(
                botonDiferencia,
                confirmarDiferencia,
                confirmarDiferencia
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
    }

    for (const formulario of formularios) {
        inicializarFormulario(formulario);
    }
});
