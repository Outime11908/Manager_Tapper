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
let categoriasCache = [];
let productosCache = [];
let carrito = [];
let graficoRanking = null;
function fmt(n) {
    return n.toFixed(2);
}
function fmtFecha(iso) {
    const d = new Date(iso);
    const fecha = d.toLocaleDateString("es-MX");
    const hora = d.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
    return `${fecha} ${hora}`;
}
function leerFormulario(form) {
    const datos = {};
    new FormData(form).forEach((valor, clave) => (datos[clave] = String(valor)));
    return datos;
}
// --------------------------------------------------------------- resumen
async function cargarResumen() {
    const resumen = await api("/api/resumen");
    const el = document.getElementById("resumen-contenido");
    el.innerHTML = `
    <div class="metric"><div class="valor">$${fmt(resumen.capital_invertido)}</div><div class="etiqueta">Capital invertido</div></div>
    <div class="metric"><div class="valor">$${fmt(resumen.ganancia_total)}</div><div class="etiqueta">Ganancia acumulada</div></div>
    <div class="metric"><div class="valor${resumen.punto_equilibrio_alcanzado ? " valor-gain" : ""}">${resumen.punto_equilibrio_alcanzado
        ? "¡Alcanzado! Excedente $" + fmt(resumen.excedente)
        : "$" + fmt(resumen.falta_para_recuperar_capital)}</div><div class="etiqueta">${resumen.punto_equilibrio_alcanzado ? "Punto de equilibrio" : "Falta para el punto de equilibrio"}</div></div>
  `;
}
// ------------------------------------------------------------ categorias
async function cargarCategorias() {
    categoriasCache = await api("/api/categorias");
    const ul = document.getElementById("lista-categorias");
    ul.innerHTML = categoriasCache.length
        ? categoriasCache.map((c) => `<li>${c.nombre}</li>`).join("")
        : '<li class="sin-alertas">Sin categorías todavía.</li>';
    const opciones = categoriasCache.map((c) => `<option value="${c.id}">${c.nombre}</option>`).join("");
    document.getElementById("select-categoria-producto").innerHTML =
        '<option value="">Sin categoría</option>' + opciones;
    document.getElementById("filtro-categoria").innerHTML =
        '<option value="">Todas las categorías</option>' + opciones;
}
// ------------------------------------------------------------- productos
function productosFiltrados() {
    const busqueda = document.getElementById("buscador-productos").value.trim().toLowerCase();
    const categoriaId = document.getElementById("filtro-categoria").value;
    return productosCache.filter((p) => {
        var _a;
        const coincideNombre = !busqueda || p.nombre.toLowerCase().includes(busqueda);
        const coincideCategoria = !categoriaId || String((_a = p.categoria_id) !== null && _a !== void 0 ? _a : "") === categoriaId;
        return coincideNombre && coincideCategoria;
    });
}
function renderTablaProductos() {
    const tbody = document.querySelector("#tabla-productos tbody");
    const lista = productosFiltrados();
    tbody.innerHTML = lista.length
        ? lista
            .map((p) => {
            var _a;
            return `
      <tr>
        <td>${p.nombre}${p.stock_bajo ? ' <span class="stock-bajo">(stock bajo)</span>' : ""}</td>
        <td>${(_a = p.categoria_nombre) !== null && _a !== void 0 ? _a : "—"}</td>
        <td>$${fmt(p.costo)}</td>
        <td>$${fmt(p.precio_actual)}</td>
        <td>${p.stock}</td>
        <td>${p.margen_porcentual}%</td>
        <td class="col-acciones">
          <button type="button" class="btn-editar" data-id="${p.id}">Editar</button>
          <button type="button" class="btn-eliminar" data-id="${p.id}">Eliminar</button>
        </td>
      </tr>`;
        })
            .join("")
        : `<tr><td colspan="7" class="vacio">Sin productos que coincidan.</td></tr>`;
    tbody.querySelectorAll(".btn-editar").forEach((btn) => {
        btn.addEventListener("click", () => iniciarEdicionProducto(Number(btn.dataset.id)));
    });
    tbody.querySelectorAll(".btn-eliminar").forEach((btn) => {
        btn.addEventListener("click", () => eliminarProducto(Number(btn.dataset.id)));
    });
}
function renderSelectsProducto() {
    const activos = productosCache;
    const opciones = activos.map((p) => `<option value="${p.id}">${p.nombre} — $${fmt(p.precio_actual)}</option>`).join("");
    document.getElementById("select-producto-pos").innerHTML = opciones;
    document.getElementById("select-producto-simulador").innerHTML = opciones;
}
async function cargarProductos() {
    productosCache = await api("/api/productos");
    renderTablaProductos();
    renderSelectsProducto();
}
function iniciarEdicionProducto(id) {
    const producto = productosCache.find((p) => p.id === id);
    if (!producto)
        return;
    const form = document.getElementById("form-producto");
    form.elements.namedItem("producto_id").value = String(producto.id);
    form.elements.namedItem("nombre").value = producto.nombre;
    form.elements.namedItem("costo").value = String(producto.costo);
    form.elements.namedItem("precio").value = String(producto.precio_actual);
    form.elements.namedItem("stock").value = String(producto.stock);
    form.elements.namedItem("categoria_id").value = producto.categoria_id ? String(producto.categoria_id) : "";
    document.getElementById("btn-guardar-producto").textContent = "Guardar cambios";
    document.getElementById("btn-cancelar-edicion").hidden = false;
    form.scrollIntoView({ behavior: "smooth", block: "start" });
}
function cancelarEdicionProducto() {
    const form = document.getElementById("form-producto");
    form.reset();
    form.elements.namedItem("producto_id").value = "";
    document.getElementById("btn-guardar-producto").textContent = "Agregar producto";
    document.getElementById("btn-cancelar-edicion").hidden = true;
}
async function eliminarProducto(id) {
    const producto = productosCache.find((p) => p.id === id);
    if (!producto)
        return;
    if (!confirm(`¿Eliminar "${producto.nombre}" del catálogo?`))
        return;
    await api(`/api/productos/${id}`, { method: "DELETE" });
    await Promise.all([cargarProductos(), cargarAlertas(), cargarRanking()]);
}
// -------------------------------------------------------------- alertas
async function cargarAlertas() {
    const alertas = await api("/api/inventario/alertas");
    const ul = document.getElementById("lista-alertas");
    ul.innerHTML = alertas.length
        ? alertas.map((p) => `<li>${p.nombre}: quedan ${p.stock} unidades</li>`).join("")
        : '<li class="sin-alertas">Sin alertas por ahora.</li>';
}
// -------------------------------------------------------------- ranking
async function cargarRanking() {
    const filas = await api("/api/ranking");
    const tbody = document.querySelector("#tabla-ranking tbody");
    tbody.innerHTML = filas
        .map((f) => `
      <tr>
        <td>${f.nombre}</td>
        <td>${f.unidades_vendidas}</td>
        <td>$${fmt(f.ganancia_generada)}</td>
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
                backgroundColor: "#9C6B29",
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
// -------------------------------------------------------- punto de venta
function renderCarrito() {
    const tbody = document.querySelector("#tabla-carrito tbody");
    tbody.innerHTML = carrito
        .map((item, i) => `
      <tr>
        <td>${item.nombre}</td>
        <td><input type="number" min="1" value="${item.cantidad}" class="cantidad-carrito" data-idx="${i}" /></td>
        <td>$${fmt(item.precio_unitario)}</td>
        <td>$${fmt(item.precio_unitario * item.cantidad)}</td>
        <td><button type="button" class="btn-quitar-carrito" data-idx="${i}">Quitar</button></td>
      </tr>`)
        .join("");
    tbody.querySelectorAll(".cantidad-carrito").forEach((input) => {
        input.addEventListener("change", () => {
            const idx = Number(input.dataset.idx);
            const cantidad = Math.max(1, Number(input.value) || 1);
            carrito[idx].cantidad = cantidad;
            renderCarrito();
        });
    });
    tbody.querySelectorAll(".btn-quitar-carrito").forEach((btn) => {
        btn.addEventListener("click", () => {
            carrito.splice(Number(btn.dataset.idx), 1);
            renderCarrito();
        });
    });
    const total = carrito.reduce((acc, i) => acc + i.precio_unitario * i.cantidad, 0);
    document.getElementById("carrito-total").textContent = `Total: $${fmt(total)}`;
    actualizarCambio();
}
function totalCarrito() {
    return carrito.reduce((acc, i) => acc + i.precio_unitario * i.cantidad, 0);
}
function actualizarCambio() {
    const metodo = document.getElementById("metodo-pago").value;
    const montoInput = document.getElementById("monto-recibido");
    const cambioEl = document.getElementById("cambio-calculado");
    if (metodo !== "efectivo") {
        montoInput.hidden = true;
        cambioEl.textContent = "";
        return;
    }
    montoInput.hidden = false;
    const monto = Number(montoInput.value);
    const total = totalCarrito();
    if (!montoInput.value || isNaN(monto)) {
        cambioEl.textContent = "";
    }
    else if (monto < total) {
        cambioEl.textContent = `Falta $${fmt(total - monto)}`;
    }
    else {
        cambioEl.textContent = `Cambio: $${fmt(monto - total)}`;
    }
}
function renderRecibo(ticket) {
    var _a, _b;
    const items = (_a = ticket.items) !== null && _a !== void 0 ? _a : [];
    const filas = items
        .map((i) => `
      <tr>
        <td>${i.producto_nombre}</td>
        <td>${i.cantidad}</td>
        <td>$${fmt(i.subtotal)}</td>
      </tr>`)
        .join("");
    return `
    <p class="recibo-titulo">Manager Tapper</p>
    <p class="recibo-meta">Ticket #${ticket.id} · ${fmtFecha(ticket.fecha)}</p>
    <table class="recibo-tabla">
      <thead><tr><th>Producto</th><th>Cant.</th><th>Subtotal</th></tr></thead>
      <tbody>${filas}</tbody>
    </table>
    <p class="recibo-total">Total: $${fmt(ticket.total)}</p>
    <p class="recibo-meta">Método de pago: ${ticket.metodo_pago === "efectivo" ? "Efectivo" : "Tarjeta"}</p>
    ${ticket.metodo_pago === "efectivo" && ticket.monto_pagado !== null
        ? `<p class="recibo-meta">Pagó: $${fmt(ticket.monto_pagado)} · Cambio: $${fmt((_b = ticket.cambio) !== null && _b !== void 0 ? _b : 0)}</p>`
        : ""}
  `;
}
async function completarVenta() {
    if (carrito.length === 0) {
        alert("Agrega al menos un producto al carrito");
        return;
    }
    const metodo = document.getElementById("metodo-pago").value;
    const montoInput = document.getElementById("monto-recibido");
    const payload = {
        items: carrito.map((i) => ({ producto_id: i.producto_id, cantidad: i.cantidad })),
        metodo_pago: metodo,
    };
    if (metodo === "efectivo") {
        payload.monto_pagado = Number(montoInput.value);
    }
    try {
        const ticket = await api("/api/ventas", { method: "POST", body: JSON.stringify(payload) });
        document.getElementById("recibo-contenido").innerHTML = renderRecibo(ticket);
        document.getElementById("recibo").hidden = false;
        carrito = [];
        renderCarrito();
        montoInput.value = "";
        document.getElementById("cambio-calculado").textContent = "";
        await Promise.all([cargarResumen(), cargarProductos(), cargarAlertas(), cargarRanking(), cargarTickets()]);
    }
    catch (e) {
        alert(e.message);
    }
}
// ----------------------------------------------------------- historial
async function cargarTickets() {
    const tickets = await api("/api/tickets");
    const tbody = document.querySelector("#tabla-tickets tbody");
    tbody.innerHTML = tickets.length
        ? tickets
            .map((t) => `
      <tr>
        <td>${fmtFecha(t.fecha)}</td>
        <td>${t.metodo_pago === "efectivo" ? "Efectivo" : "Tarjeta"}</td>
        <td>${t.num_items}</td>
        <td>$${fmt(t.total)}</td>
        <td><button type="button" class="btn-ver-ticket" data-id="${t.id}">Ver</button></td>
      </tr>`)
            .join("")
        : `<tr><td colspan="5" class="vacio">Todavía no hay ventas registradas.</td></tr>`;
    tbody.querySelectorAll(".btn-ver-ticket").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const ticket = await api(`/api/tickets/${btn.dataset.id}`);
            document.getElementById("detalle-ticket-contenido").innerHTML = renderRecibo(ticket);
            document.getElementById("detalle-ticket").hidden = false;
            document.getElementById("detalle-ticket").scrollIntoView({ behavior: "smooth", block: "center" });
        });
    });
}
// --------------------------------------------------------------- global
async function recargarTodo() {
    await Promise.all([
        cargarResumen(),
        cargarCategorias(),
        cargarProductos(),
        cargarAlertas(),
        cargarRanking(),
        cargarTickets(),
    ]);
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
document.getElementById("form-categoria").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const datos = leerFormulario(form);
    try {
        await api("/api/categorias", { method: "POST", body: JSON.stringify({ nombre: datos.nombre }) });
        form.reset();
        await cargarCategorias();
    }
    catch (e) {
        alert(e.message);
    }
});
document.getElementById("form-producto").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const datos = leerFormulario(form);
    const payload = {
        nombre: datos.nombre,
        costo: Number(datos.costo),
        precio: Number(datos.precio),
        stock: Number(datos.stock),
        categoria_id: datos.categoria_id || null,
    };
    try {
        if (datos.producto_id) {
            const original = productosCache.find((p) => p.id === Number(datos.producto_id));
            await api(`/api/productos/${datos.producto_id}`, { method: "PUT", body: JSON.stringify(payload) });
            const nuevoPrecio = Number(datos.precio);
            if (original && nuevoPrecio !== original.precio_actual) {
                // El precio tiene su propio endpoint para que el cambio quede en el historial.
                await api(`/api/productos/${datos.producto_id}/precio`, {
                    method: "PUT",
                    body: JSON.stringify({ precio: nuevoPrecio }),
                });
            }
        }
        else {
            await api("/api/productos", { method: "POST", body: JSON.stringify(payload) });
        }
        cancelarEdicionProducto();
        await Promise.all([cargarProductos(), cargarAlertas(), cargarRanking()]);
    }
    catch (e) {
        alert(e.message);
    }
});
document.getElementById("btn-cancelar-edicion").addEventListener("click", cancelarEdicionProducto);
document.getElementById("buscador-productos").addEventListener("input", renderTablaProductos);
document.getElementById("filtro-categoria").addEventListener("change", renderTablaProductos);
document.getElementById("form-agregar-carrito").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const datos = leerFormulario(form);
    const producto = productosCache.find((p) => p.id === Number(datos.producto_id));
    if (!producto)
        return;
    const cantidad = Math.max(1, Number(datos.cantidad) || 1);
    const existente = carrito.find((i) => i.producto_id === producto.id);
    if (existente) {
        existente.cantidad += cantidad;
    }
    else {
        carrito.push({
            producto_id: producto.id,
            nombre: producto.nombre,
            precio_unitario: producto.precio_actual,
            cantidad,
        });
    }
    renderCarrito();
    form.elements.namedItem("cantidad").value = "1";
});
document.getElementById("metodo-pago").addEventListener("change", actualizarCambio);
document.getElementById("monto-recibido").addEventListener("input", actualizarCambio);
document.getElementById("form-cobro").addEventListener("submit", (ev) => {
    ev.preventDefault();
    completarVenta();
});
document.getElementById("btn-imprimir").addEventListener("click", () => window.print());
document.getElementById("btn-nueva-venta").addEventListener("click", () => {
    document.getElementById("recibo").hidden = true;
});
document.getElementById("btn-cerrar-detalle").addEventListener("click", () => {
    document.getElementById("detalle-ticket").hidden = true;
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
    <p><strong>${resultado.nombre}</strong>: precio actual $${fmt(resultado.precio_actual)} →
    precio simulado $${fmt(resultado.precio_simulado)} (${resultado.porcentaje_aplicado}%)</p>
    <p>Ganancia actual: $${fmt(resultado.ganancia_actual)} · Ganancia proyectada: $${fmt(resultado.ganancia_proyectada)}
    (${signo}${fmt(resultado.diferencia)})</p>
  `;
});
// estado inicial del selector de método de pago (oculta "monto recibido" si aplica)
actualizarCambio();
recargarTodo();
