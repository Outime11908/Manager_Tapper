"use strict";
// Dashboard de Manager Tapper — conecta la interfaz con la API de Flask.
async function api(url, options) {
    const res = await fetch(url, Object.assign({ headers: { "Content-Type": "application/json" } }, options));
    if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(err.error || "Error de red");
    }
    return res.json();
}
let productosCache = [];
let graficoRanking = null;
async function cargarResumen() {
    const resumen = await api("/api/resumen");
    const el = document.getElementById("resumen-contenido");
    el.innerHTML = `
    <div class="metric"><div class="valor">$${resumen.capital_invertido.toFixed(2)}</div><div class="etiqueta">Capital invertido</div></div>
    <div class="metric"><div class="valor">$${resumen.ganancia_total.toFixed(2)}</div><div class="etiqueta">Ganancia acumulada</div></div>
    <div class="metric"><div class="valor">${resumen.punto_equilibrio_alcanzado
        ? "¡Alcanzado! Excedente $" + resumen.excedente.toFixed(2)
        : "$" + resumen.falta_para_recuperar_capital.toFixed(2)}</div><div class="etiqueta">${resumen.punto_equilibrio_alcanzado ? "Punto de equilibrio" : "Falta para el punto de equilibrio"}</div></div>
  `;
}
async function cargarProductos() {
    productosCache = await api("/api/productos");
    const tbody = document.querySelector("#tabla-productos tbody");
    tbody.innerHTML = productosCache
        .map((p) => `
      <tr>
        <td>${p.nombre}${p.stock_bajo ? ' <span class="stock-bajo">(stock bajo)</span>' : ""}</td>
        <td>$${p.costo.toFixed(2)}</td>
        <td>$${p.precio_actual.toFixed(2)}</td>
        <td>${p.stock}</td>
        <td>${p.margen_porcentual}%</td>
      </tr>`)
        .join("");
    const opciones = productosCache
        .map((p) => `<option value="${p.id}">${p.nombre}</option>`)
        .join("");
    document.getElementById("select-producto-venta").innerHTML = opciones;
    document.getElementById("select-producto-simulador").innerHTML = opciones;
}
async function cargarAlertas() {
    const alertas = await api("/api/inventario/alertas");
    const ul = document.getElementById("lista-alertas");
    ul.innerHTML = alertas.length
        ? alertas.map((p) => `<li>${p.nombre}: quedan ${p.stock} unidades</li>`).join("")
        : "<li>Sin alertas por ahora.</li>";
}
async function cargarRanking() {
    const filas = await api("/api/ranking");
    const tbody = document.querySelector("#tabla-ranking tbody");
    tbody.innerHTML = filas
        .map((f) => `
      <tr>
        <td>${f.nombre}</td>
        <td>${f.unidades_vendidas}</td>
        <td>$${f.ganancia_generada.toFixed(2)}</td>
        <td>${f.margen_porcentual}%</td>
        <td>${f.estrategia_sugerida}</td>
      </tr>`)
        .join("");
    const ctx = document.getElementById("grafico-ranking").getContext("2d");
    const datos = {
        labels: filas.map((f) => f.nombre),
        datasets: [
            {
                label: "Ganancia generada",
                data: filas.map((f) => f.ganancia_generada),
                backgroundColor: "#2e5e4e",
            },
        ],
    };
    if (graficoRanking) {
        graficoRanking.data = datos;
        graficoRanking.update();
    }
    else {
        // @ts-ignore Chart viene del script UMD cargado en index.html
        graficoRanking = new Chart(ctx, { type: "bar", data: datos, options: { responsive: true } });
    }
}
async function recargarTodo() {
    await Promise.all([cargarResumen(), cargarProductos(), cargarAlertas(), cargarRanking()]);
}
function leerFormulario(form) {
    const datos = {};
    new FormData(form).forEach((valor, clave) => (datos[clave] = String(valor)));
    return datos;
}
document.getElementById("form-capital").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const datos = leerFormulario(form);
    await api("/api/capital", {
        method: "POST",
        body: JSON.stringify({ monto: Number(datos.monto), descripcion: datos.descripcion }),
    });
    form.reset();
    await cargarResumen();
});
document.getElementById("form-producto").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const datos = leerFormulario(form);
    await api("/api/productos", {
        method: "POST",
        body: JSON.stringify({
            nombre: datos.nombre,
            costo: Number(datos.costo),
            precio: Number(datos.precio),
            stock: Number(datos.stock),
        }),
    });
    form.reset();
    await recargarTodo();
});
document.getElementById("form-venta").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const datos = leerFormulario(form);
    try {
        await api("/api/ventas", {
            method: "POST",
            body: JSON.stringify({ producto_id: Number(datos.producto_id), cantidad: Number(datos.cantidad) }),
        });
        form.reset();
        await recargarTodo();
    }
    catch (e) {
        alert(e.message);
    }
});
document.getElementById("form-simulador").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const datos = leerFormulario(form);
    const resultado = await api("/api/simular-precio", {
        method: "POST",
        body: JSON.stringify({ producto_id: Number(datos.producto_id), porcentaje: Number(datos.porcentaje) }),
    });
    const el = document.getElementById("resultado-simulador");
    const signo = resultado.diferencia >= 0 ? "+" : "";
    el.innerHTML = `
    <p><strong>${resultado.nombre}</strong>: precio actual $${resultado.precio_actual.toFixed(2)} →
    precio simulado $${resultado.precio_simulado.toFixed(2)} (${resultado.porcentaje_aplicado}%)</p>
    <p>Ganancia actual: $${resultado.ganancia_actual.toFixed(2)} · Ganancia proyectada: $${resultado.ganancia_proyectada.toFixed(2)}
    (${signo}${resultado.diferencia.toFixed(2)})</p>
  `;
});
recargarTodo();
