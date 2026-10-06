// Dashboard de Manager Tapper — conecta la interfaz con la API de Flask.

interface Categoria { id: number; nombre: string; }

interface Producto {
  id: number;
  nombre: string;
  costo: number;
  precio_actual: number;
  stock: number;
  stock_bajo: boolean;
  margen_unitario: number;
  margen_porcentual: number;
  categoria_id: number | null;
  categoria_nombre: string | null;
  activo: boolean;
}

interface Resumen {
  capital_invertido: number;
  ganancia_bruta: number;
  gastos_totales: number;
  ganancia_neta: number;
  falta_para_recuperar_capital: number;
  punto_equilibrio_alcanzado: boolean;
  excedente: number;
}

interface FilaRanking {
  producto_id: number;
  nombre: string;
  unidades_vendidas: number;
  ganancia_generada: number;
  margen_porcentual: number;
  rotacion_alta: boolean;
  estrategia_sugerida: string;
}

interface ResultadoSimulacion {
  nombre: string;
  precio_actual: number;
  precio_simulado: number;
  porcentaje_aplicado: number;
  ganancia_actual: number;
  ganancia_proyectada: number;
  diferencia: number;
}

interface ItemCarrito {
  producto_id: number;
  nombre: string;
  precio_unitario: number;
  cantidad: number;
}

interface DetalleTicket {
  id: number;
  producto_id: number;
  producto_nombre: string;
  cantidad: number;
  precio_unitario: number;
  subtotal: number;
  ganancia: number;
}

interface Ticket {
  id: number;
  fecha: string;
  metodo_pago: "efectivo" | "tarjeta" | "credito";
  total: number;
  monto_pagado: number | null;
  cambio: number | null;
  num_items: number;
  cliente_id: number | null;
  cliente_nombre: string | null;
  pagado: boolean;
  pagado_en: string | null;
  items?: DetalleTicket[];
}

interface Gasto {
  id: number;
  descripcion: string;
  monto: number;
  categoria: string | null;
  fecha: string;
}

interface Meta {
  id: number;
  descripcion: string;
  monto_objetivo: number;
  fecha_inicio: string;
  fecha_fin: string;
  acumulado: number;
  porcentaje: number;
}

interface Cliente { id: number; nombre: string; contacto: string | null; }

interface VentaPeriodo { periodo: string; total: number; }

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || "Error de red");
  }
  return res.json();
}

let categoriasCache: Categoria[] = [];
let productosCache: Producto[] = [];
let clientesCache: Cliente[] = [];
let carrito: ItemCarrito[] = [];
let graficoRanking: any = null;
let graficoVentasTiempo: any = null;
let periodoActual: "dia" | "semana" | "mes" = "dia";

function fmt(n: number): string {
  return n.toFixed(2);
}

function fmtFecha(iso: string): string {
  const d = new Date(iso);
  const fecha = d.toLocaleDateString("es-MX");
  const hora = d.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
  return `${fecha} ${hora}`;
}

function leerFormulario(form: HTMLFormElement): Record<string, string> {
  const datos: Record<string, string> = {};
  new FormData(form).forEach((valor, clave) => (datos[clave] = String(valor)));
  return datos;
}

// ------------------------------------------------------------- modo oscuro
function aplicarTema(tema: "light" | "dark"): void {
  if (tema === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  document.getElementById("btn-tema")!.textContent = tema === "dark" ? "Modo claro" : "Modo oscuro";
  try { localStorage.setItem("mt-tema", tema); } catch (e) { /* almacenamiento no disponible */ }
}

document.getElementById("btn-tema")!.addEventListener("click", () => {
  const actual = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  aplicarTema(actual === "dark" ? "light" : "dark");
});
aplicarTema(document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light");

// --------------------------------------------------------------- resumen
async function cargarResumen(): Promise<void> {
  const r = await api<Resumen>("/api/resumen");
  const el = document.getElementById("resumen-contenido")!;
  el.innerHTML = `
    <div class="metric"><div class="valor">$${fmt(r.capital_invertido)}</div><div class="etiqueta">Capital invertido</div></div>
    <div class="metric"><div class="valor">$${fmt(r.ganancia_bruta)}</div><div class="etiqueta">Ganancia bruta</div></div>
    <div class="metric"><div class="valor">$${fmt(r.gastos_totales)}</div><div class="etiqueta">Gastos operativos</div></div>
    <div class="metric"><div class="valor">$${fmt(r.ganancia_neta)}</div><div class="etiqueta">Ganancia neta</div></div>
    <div class="metric"><div class="valor${r.punto_equilibrio_alcanzado ? " valor-gain" : ""}">${
      r.punto_equilibrio_alcanzado
        ? "¡Alcanzado! Excedente $" + fmt(r.excedente)
        : "$" + fmt(r.falta_para_recuperar_capital)
    }</div><div class="etiqueta">${r.punto_equilibrio_alcanzado ? "Punto de equilibrio" : "Falta para el punto de equilibrio"}</div></div>
  `;
}

// ------------------------------------------------------------ categorias
async function cargarCategorias(): Promise<void> {
  categoriasCache = await api<Categoria[]>("/api/categorias");

  const ul = document.getElementById("lista-categorias")!;
  ul.innerHTML = categoriasCache.length
    ? categoriasCache.map((c) => `<li>${c.nombre}</li>`).join("")
    : '<li class="sin-alertas">Sin categorías todavía.</li>';

  const opciones = categoriasCache.map((c) => `<option value="${c.id}">${c.nombre}</option>`).join("");
  (document.getElementById("select-categoria-producto") as HTMLSelectElement).innerHTML =
    '<option value="">Sin categoría</option>' + opciones;
  (document.getElementById("filtro-categoria") as HTMLSelectElement).innerHTML =
    '<option value="">Todas las categorías</option>' + opciones;
}

// ------------------------------------------------------------- productos
function productosFiltrados(): Producto[] {
  const busqueda = (document.getElementById("buscador-productos") as HTMLInputElement).value.trim().toLowerCase();
  const categoriaId = (document.getElementById("filtro-categoria") as HTMLSelectElement).value;
  return productosCache.filter((p) => {
    const coincideNombre = !busqueda || p.nombre.toLowerCase().includes(busqueda);
    const coincideCategoria = !categoriaId || String(p.categoria_id ?? "") === categoriaId;
    return coincideNombre && coincideCategoria;
  });
}

function renderTablaProductos(): void {
  const tbody = document.querySelector("#tabla-productos tbody")!;
  const lista = productosFiltrados();
  tbody.innerHTML = lista.length
    ? lista
        .map(
          (p) => `
      <tr>
        <td>${p.nombre}${p.stock_bajo ? ' <span class="stock-bajo">(stock bajo)</span>' : ""}</td>
        <td>${p.categoria_nombre ?? "—"}</td>
        <td>$${fmt(p.costo)}</td>
        <td>$${fmt(p.precio_actual)}</td>
        <td>${p.stock}</td>
        <td>${p.margen_porcentual}%</td>
        <td class="col-acciones">
          <button type="button" class="btn-editar" data-id="${p.id}">Editar</button>
          <button type="button" class="btn-eliminar" data-id="${p.id}">Eliminar</button>
        </td>
      </tr>`
        )
        .join("")
    : `<tr><td colspan="7" class="vacio">Sin productos que coincidan.</td></tr>`;

  tbody.querySelectorAll<HTMLButtonElement>(".btn-editar").forEach((btn) => {
    btn.addEventListener("click", () => iniciarEdicionProducto(Number(btn.dataset.id)));
  });
  tbody.querySelectorAll<HTMLButtonElement>(".btn-eliminar").forEach((btn) => {
    btn.addEventListener("click", () => eliminarProducto(Number(btn.dataset.id)));
  });
}

function renderSelectsProducto(): void {
  const opciones = productosCache.map((p) => `<option value="${p.id}">${p.nombre} — $${fmt(p.precio_actual)}</option>`).join("");
  (document.getElementById("select-producto-pos") as HTMLSelectElement).innerHTML = opciones;
  (document.getElementById("select-producto-simulador") as HTMLSelectElement).innerHTML = opciones;
}

async function cargarProductos(): Promise<void> {
  productosCache = await api<Producto[]>("/api/productos");
  renderTablaProductos();
  renderSelectsProducto();
}

function iniciarEdicionProducto(id: number): void {
  const producto = productosCache.find((p) => p.id === id);
  if (!producto) return;
  const form = document.getElementById("form-producto") as HTMLFormElement;
  (form.elements.namedItem("producto_id") as HTMLInputElement).value = String(producto.id);
  (form.elements.namedItem("nombre") as HTMLInputElement).value = producto.nombre;
  (form.elements.namedItem("costo") as HTMLInputElement).value = String(producto.costo);
  (form.elements.namedItem("precio") as HTMLInputElement).value = String(producto.precio_actual);
  (form.elements.namedItem("stock") as HTMLInputElement).value = String(producto.stock);
  (form.elements.namedItem("categoria_id") as HTMLSelectElement).value = producto.categoria_id ? String(producto.categoria_id) : "";
  document.getElementById("btn-guardar-producto")!.textContent = "Guardar cambios";
  document.getElementById("btn-cancelar-edicion")!.hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

function cancelarEdicionProducto(): void {
  const form = document.getElementById("form-producto") as HTMLFormElement;
  form.reset();
  (form.elements.namedItem("producto_id") as HTMLInputElement).value = "";
  document.getElementById("btn-guardar-producto")!.textContent = "Agregar producto";
  document.getElementById("btn-cancelar-edicion")!.hidden = true;
}

async function eliminarProducto(id: number): Promise<void> {
  const producto = productosCache.find((p) => p.id === id);
  if (!producto) return;
  if (!confirm(`¿Eliminar "${producto.nombre}" del catálogo?`)) return;
  await api(`/api/productos/${id}`, { method: "DELETE" });
  await Promise.all([cargarProductos(), cargarAlertas(), cargarRanking()]);
}

// -------------------------------------------------------------- alertas
async function cargarAlertas(): Promise<void> {
  const alertas = await api<Producto[]>("/api/inventario/alertas");
  const ul = document.getElementById("lista-alertas")!;
  ul.innerHTML = alertas.length
    ? alertas.map((p) => `<li>${p.nombre}: quedan ${p.stock} unidades</li>`).join("")
    : '<li class="sin-alertas">Sin alertas por ahora.</li>';
}

// -------------------------------------------------------------- ranking
async function cargarRanking(): Promise<void> {
  const filas = await api<FilaRanking[]>("/api/ranking");
  const tbody = document.querySelector("#tabla-ranking tbody")!;
  tbody.innerHTML = filas
    .map(
      (f) => `
      <tr>
        <td>${f.nombre}</td>
        <td>${f.unidades_vendidas}</td>
        <td>$${fmt(f.ganancia_generada)}</td>
        <td>${f.margen_porcentual}%</td>
        <td>${f.estrategia_sugerida}</td>
      </tr>`
    )
    .join("");

  const ctx = (document.getElementById("grafico-ranking") as HTMLCanvasElement).getContext("2d")!;
  const datos = {
    labels: filas.map((f) => f.nombre),
    datasets: [{ label: "Ganancia generada", data: filas.map((f) => f.ganancia_generada), backgroundColor: "#9C6B29" }],
  };
  if (graficoRanking) {
    graficoRanking.data = datos;
    graficoRanking.update();
  } else {
    // @ts-ignore Chart viene del script UMD cargado en index.html
    graficoRanking = new Chart(ctx, { type: "bar", data: datos, options: { responsive: true } });
  }
}

// ------------------------------------------------------- ventas en el tiempo
async function cargarVentasPorPeriodo(): Promise<void> {
  const filas = await api<VentaPeriodo[]>(`/api/ventas-por-periodo?agrupacion=${periodoActual}`);
  const ctx = (document.getElementById("grafico-ventas-tiempo") as HTMLCanvasElement).getContext("2d")!;
  const datos = {
    labels: filas.map((f) => f.periodo),
    datasets: [{ label: "Ventas", data: filas.map((f) => f.total), borderColor: "#9C6B29", backgroundColor: "rgba(156,107,41,0.15)", fill: true, tension: 0.2 }],
  };
  if (graficoVentasTiempo) {
    graficoVentasTiempo.data = datos;
    graficoVentasTiempo.update();
  } else {
    // @ts-ignore
    graficoVentasTiempo = new Chart(ctx, { type: "line", data: datos, options: { responsive: true } });
  }
}

document.querySelectorAll<HTMLButtonElement>("#segmentado-periodo button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#segmentado-periodo button").forEach((b) => b.classList.remove("activo"));
    btn.classList.add("activo");
    periodoActual = btn.dataset.periodo as "dia" | "semana" | "mes";
    cargarVentasPorPeriodo();
  });
});

// ------------------------------------------------------------------ gastos
async function cargarGastos(): Promise<void> {
  const gastos = await api<Gasto[]>("/api/gastos");
  const tbody = document.querySelector("#tabla-gastos tbody")!;
  tbody.innerHTML = gastos.length
    ? gastos
        .map(
          (g) => `
      <tr>
        <td>${fmtFecha(g.fecha)}</td>
        <td>${g.descripcion}</td>
        <td>${g.categoria ?? "—"}</td>
        <td>$${fmt(g.monto)}</td>
      </tr>`
        )
        .join("")
    : `<tr><td colspan="4" class="vacio">Sin gastos registrados.</td></tr>`;
}

// ------------------------------------------------------------------- metas
function renderMetas(metas: Meta[]): void {
  const cont = document.getElementById("lista-metas")!;
  cont.innerHTML = metas.length
    ? metas
        .map(
          (m) => `
      <div class="meta-item">
        <div class="meta-cabecera">
          <strong>${m.descripcion}</strong>
          <span>$${fmt(m.acumulado)} / $${fmt(m.monto_objetivo)}</span>
        </div>
        <div class="meta-barra"><div class="meta-progreso" style="width:${m.porcentaje}%"></div></div>
        <div class="meta-pie">${m.porcentaje}% · hasta ${fmtFecha(m.fecha_fin).split(" ")[0]}</div>
      </div>`
        )
        .join("")
    : '<p class="vacio-texto">Sin metas registradas todavía.</p>';
}

async function cargarMetas(): Promise<void> {
  const metas = await api<Meta[]>("/api/metas");
  renderMetas(metas);
}

// ---------------------------------------------------------------- clientes
async function cargarClientes(): Promise<void> {
  clientesCache = await api<Cliente[]>("/api/clientes");
  const ul = document.getElementById("lista-clientes")!;
  ul.innerHTML = clientesCache.length
    ? clientesCache.map((c) => `<li>${c.nombre}${c.contacto ? " — " + c.contacto : ""}</li>`).join("")
    : '<li class="sin-alertas">Sin clientes todavía.</li>';

  const opciones = clientesCache.map((c) => `<option value="${c.id}">${c.nombre}</option>`).join("");
  (document.getElementById("select-cliente-credito") as HTMLSelectElement).innerHTML =
    '<option value="">Selecciona un cliente…</option>' + opciones;
}

// -------------------------------------------------------- punto de venta
function renderCarrito(): void {
  const tbody = document.querySelector("#tabla-carrito tbody")!;
  tbody.innerHTML = carrito
    .map(
      (item, i) => `
      <tr>
        <td>${item.nombre}</td>
        <td><input type="number" min="1" value="${item.cantidad}" class="cantidad-carrito" data-idx="${i}" /></td>
        <td>$${fmt(item.precio_unitario)}</td>
        <td>$${fmt(item.precio_unitario * item.cantidad)}</td>
        <td><button type="button" class="btn-quitar-carrito" data-idx="${i}">Quitar</button></td>
      </tr>`
    )
    .join("");

  tbody.querySelectorAll<HTMLInputElement>(".cantidad-carrito").forEach((input) => {
    input.addEventListener("change", () => {
      const idx = Number(input.dataset.idx);
      carrito[idx].cantidad = Math.max(1, Number(input.value) || 1);
      renderCarrito();
    });
  });
  tbody.querySelectorAll<HTMLButtonElement>(".btn-quitar-carrito").forEach((btn) => {
    btn.addEventListener("click", () => {
      carrito.splice(Number(btn.dataset.idx), 1);
      renderCarrito();
    });
  });

  const total = carrito.reduce((acc, i) => acc + i.precio_unitario * i.cantidad, 0);
  document.getElementById("carrito-total")!.textContent = `Total: $${fmt(total)}`;
  actualizarCambio();
}

function totalCarrito(): number {
  return carrito.reduce((acc, i) => acc + i.precio_unitario * i.cantidad, 0);
}

function actualizarCambio(): void {
  const metodo = (document.getElementById("metodo-pago") as HTMLSelectElement).value;
  const montoInput = document.getElementById("monto-recibido") as HTMLInputElement;
  const clienteSelect = document.getElementById("select-cliente-credito") as HTMLSelectElement;
  const cambioEl = document.getElementById("cambio-calculado")!;

  montoInput.hidden = metodo !== "efectivo";
  clienteSelect.hidden = metodo !== "credito";

  if (metodo !== "efectivo") {
    cambioEl.textContent = "";
    return;
  }
  const monto = Number(montoInput.value);
  const total = totalCarrito();
  if (!montoInput.value || isNaN(monto)) {
    cambioEl.textContent = "";
  } else if (monto < total) {
    cambioEl.textContent = `Falta $${fmt(total - monto)}`;
  } else {
    cambioEl.textContent = `Cambio: $${fmt(monto - total)}`;
  }
}

function renderRecibo(ticket: Ticket): string {
  const items = ticket.items ?? [];
  const filas = items
    .map((i) => `<tr><td>${i.producto_nombre}</td><td>${i.cantidad}</td><td>$${fmt(i.subtotal)}</td></tr>`)
    .join("");

  const metodoTexto = ticket.metodo_pago === "efectivo" ? "Efectivo" : ticket.metodo_pago === "tarjeta" ? "Tarjeta" : "Crédito";

  return `
    <p class="recibo-titulo">Manager Tapper</p>
    <p class="recibo-meta">Ticket #${ticket.id} · ${fmtFecha(ticket.fecha)}</p>
    ${ticket.cliente_nombre ? `<p class="recibo-meta">Cliente: ${ticket.cliente_nombre}</p>` : ""}
    <table class="recibo-tabla">
      <thead><tr><th>Producto</th><th>Cant.</th><th>Subtotal</th></tr></thead>
      <tbody>${filas}</tbody>
    </table>
    <p class="recibo-total">Total: $${fmt(ticket.total)}</p>
    <p class="recibo-meta">Método de pago: ${metodoTexto}</p>
    ${
      ticket.metodo_pago === "efectivo" && ticket.monto_pagado !== null
        ? `<p class="recibo-meta">Pagó: $${fmt(ticket.monto_pagado!)} · Cambio: $${fmt(ticket.cambio ?? 0)}</p>`
        : ""
    }
    ${ticket.metodo_pago === "credito" ? `<p class="recibo-meta">${ticket.pagado ? "Pagado" : "Pendiente de pago"}</p>` : ""}
  `;
}

async function completarVenta(): Promise<void> {
  if (carrito.length === 0) {
    alert("Agrega al menos un producto al carrito");
    return;
  }
  const metodo = (document.getElementById("metodo-pago") as HTMLSelectElement).value;
  const montoInput = document.getElementById("monto-recibido") as HTMLInputElement;
  const clienteSelect = document.getElementById("select-cliente-credito") as HTMLSelectElement;

  const payload: Record<string, unknown> = {
    items: carrito.map((i) => ({ producto_id: i.producto_id, cantidad: i.cantidad })),
    metodo_pago: metodo,
  };
  if (metodo === "efectivo") payload.monto_pagado = Number(montoInput.value);
  if (metodo === "credito") payload.cliente_id = Number(clienteSelect.value) || null;

  try {
    const ticket = await api<Ticket>("/api/ventas", { method: "POST", body: JSON.stringify(payload) });
    document.getElementById("recibo-contenido")!.innerHTML = renderRecibo(ticket);
    document.getElementById("recibo")!.hidden = false;

    carrito = [];
    renderCarrito();
    montoInput.value = "";
    document.getElementById("cambio-calculado")!.textContent = "";

    await Promise.all([
      cargarResumen(), cargarProductos(), cargarAlertas(), cargarRanking(),
      cargarTickets(), cargarCuentasPorCobrar(), cargarVentasPorPeriodo(), cargarMetas(),
    ]);
  } catch (e) {
    alert((e as Error).message);
  }
}

// ----------------------------------------------------------- historial
async function cargarTickets(): Promise<void> {
  const tickets = await api<Ticket[]>("/api/tickets");
  const tbody = document.querySelector("#tabla-tickets tbody")!;
  tbody.innerHTML = tickets.length
    ? tickets
        .map(
          (t) => `
      <tr>
        <td>${fmtFecha(t.fecha)}</td>
        <td>${t.metodo_pago === "efectivo" ? "Efectivo" : t.metodo_pago === "tarjeta" ? "Tarjeta" : "Crédito"}</td>
        <td>${t.num_items}</td>
        <td>$${fmt(t.total)}</td>
        <td><button type="button" class="btn-ver-ticket" data-id="${t.id}">Ver</button></td>
      </tr>`
        )
        .join("")
    : `<tr><td colspan="5" class="vacio">Todavía no hay ventas registradas.</td></tr>`;

  tbody.querySelectorAll<HTMLButtonElement>(".btn-ver-ticket").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const ticket = await api<Ticket>(`/api/tickets/${btn.dataset.id}`);
      document.getElementById("detalle-ticket-contenido")!.innerHTML = renderRecibo(ticket);
      document.getElementById("detalle-ticket")!.hidden = false;
      document.getElementById("detalle-ticket")!.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });
}

// ----------------------------------------------------------- cuentas x cobrar
async function cargarCuentasPorCobrar(): Promise<void> {
  const tickets = await api<Ticket[]>("/api/cuentas-por-cobrar");
  const tbody = document.querySelector("#tabla-cuentas-cobrar tbody")!;
  tbody.innerHTML = tickets.length
    ? tickets
        .map(
          (t) => `
      <tr>
        <td>${fmtFecha(t.fecha)}</td>
        <td>${t.cliente_nombre ?? "—"}</td>
        <td>$${fmt(t.total)}</td>
        <td><button type="button" class="btn-marcar-pagado" data-id="${t.id}">Marcar pagado</button></td>
      </tr>`
        )
        .join("")
    : `<tr><td colspan="4" class="vacio">Sin cuentas pendientes.</td></tr>`;

  tbody.querySelectorAll<HTMLButtonElement>(".btn-marcar-pagado").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api(`/api/tickets/${btn.dataset.id}/marcar-pagado`, { method: "POST" });
      await Promise.all([cargarCuentasPorCobrar(), cargarTickets()]);
    });
  });
}

// --------------------------------------------------------------- global
async function recargarTodo(): Promise<void> {
  await Promise.all([
    cargarResumen(),
    cargarCategorias(),
    cargarProductos(),
    cargarClientes(),
    cargarAlertas(),
    cargarRanking(),
    cargarTickets(),
    cargarCuentasPorCobrar(),
    cargarGastos(),
    cargarMetas(),
    cargarVentasPorPeriodo(),
  ]);
}

document.getElementById("form-capital")!.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target as HTMLFormElement;
  const datos = leerFormulario(form);
  await api("/api/capital", { method: "POST", body: JSON.stringify({ monto: Number(datos.monto), descripcion: datos.descripcion }) });
  form.reset();
  await cargarResumen();
});

document.getElementById("form-gasto")!.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target as HTMLFormElement;
  const datos = leerFormulario(form);
  await api("/api/gastos", {
    method: "POST",
    body: JSON.stringify({ descripcion: datos.descripcion, monto: Number(datos.monto), categoria: datos.categoria || null }),
  });
  form.reset();
  await Promise.all([cargarGastos(), cargarResumen()]);
});

document.getElementById("form-meta")!.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target as HTMLFormElement;
  const datos = leerFormulario(form);
  try {
    await api("/api/metas", {
      method: "POST",
      body: JSON.stringify({
        descripcion: datos.descripcion,
        monto_objetivo: Number(datos.monto_objetivo),
        fecha_inicio: datos.fecha_inicio,
        fecha_fin: datos.fecha_fin,
      }),
    });
    form.reset();
    await cargarMetas();
  } catch (e) {
    alert((e as Error).message);
  }
});

document.getElementById("form-cliente")!.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target as HTMLFormElement;
  const datos = leerFormulario(form);
  try {
    await api("/api/clientes", { method: "POST", body: JSON.stringify({ nombre: datos.nombre, contacto: datos.contacto || null }) });
    form.reset();
    await cargarClientes();
  } catch (e) {
    alert((e as Error).message);
  }
});

document.getElementById("form-categoria")!.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target as HTMLFormElement;
  const datos = leerFormulario(form);
  try {
    await api("/api/categorias", { method: "POST", body: JSON.stringify({ nombre: datos.nombre }) });
    form.reset();
    await cargarCategorias();
  } catch (e) {
    alert((e as Error).message);
  }
});

document.getElementById("form-producto")!.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target as HTMLFormElement;
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
        await api(`/api/productos/${datos.producto_id}/precio`, { method: "PUT", body: JSON.stringify({ precio: nuevoPrecio }) });
      }
    } else {
      await api("/api/productos", { method: "POST", body: JSON.stringify(payload) });
    }
    cancelarEdicionProducto();
    await Promise.all([cargarProductos(), cargarAlertas(), cargarRanking()]);
  } catch (e) {
    alert((e as Error).message);
  }
});

document.getElementById("btn-cancelar-edicion")!.addEventListener("click", cancelarEdicionProducto);
document.getElementById("buscador-productos")!.addEventListener("input", renderTablaProductos);
document.getElementById("filtro-categoria")!.addEventListener("change", renderTablaProductos);

document.getElementById("form-agregar-carrito")!.addEventListener("submit", (ev) => {
  ev.preventDefault();
  const form = ev.target as HTMLFormElement;
  const datos = leerFormulario(form);
  const producto = productosCache.find((p) => p.id === Number(datos.producto_id));
  if (!producto) return;
  const cantidad = Math.max(1, Number(datos.cantidad) || 1);

  const existente = carrito.find((i) => i.producto_id === producto.id);
  if (existente) {
    existente.cantidad += cantidad;
  } else {
    carrito.push({ producto_id: producto.id, nombre: producto.nombre, precio_unitario: producto.precio_actual, cantidad });
  }
  renderCarrito();
  (form.elements.namedItem("cantidad") as HTMLInputElement).value = "1";
});

document.getElementById("metodo-pago")!.addEventListener("change", actualizarCambio);
document.getElementById("monto-recibido")!.addEventListener("input", actualizarCambio);
document.getElementById("form-cobro")!.addEventListener("submit", (ev) => {
  ev.preventDefault();
  completarVenta();
});

document.getElementById("btn-imprimir")!.addEventListener("click", () => window.print());
document.getElementById("btn-nueva-venta")!.addEventListener("click", () => {
  document.getElementById("recibo")!.hidden = true;
});
document.getElementById("btn-cerrar-detalle")!.addEventListener("click", () => {
  document.getElementById("detalle-ticket")!.hidden = true;
});

document.getElementById("form-simulador")!.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target as HTMLFormElement;
  const datos = leerFormulario(form);
  const resultado = await api<ResultadoSimulacion>("/api/simular-precio", {
    method: "POST",
    body: JSON.stringify({ producto_id: Number(datos.producto_id), porcentaje: Number(datos.porcentaje) }),
  });
  const el = document.getElementById("resultado-simulador")!;
  const signo = resultado.diferencia >= 0 ? "+" : "";
  el.innerHTML = `
    <p><strong>${resultado.nombre}</strong>: precio actual $${fmt(resultado.precio_actual)} →
    precio simulado $${fmt(resultado.precio_simulado)} (${resultado.porcentaje_aplicado}%)</p>
    <p>Ganancia actual: $${fmt(resultado.ganancia_actual)} · Ganancia proyectada: $${fmt(resultado.ganancia_proyectada)}
    (${signo}${fmt(resultado.diferencia)})</p>
  `;
});

actualizarCambio();
recargarTodo();
