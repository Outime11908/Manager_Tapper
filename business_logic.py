"""
Toda la lógica de cálculo de Manager Tapper vive aquí, separada de las
rutas de Flask, para que sea fácil de probar y de explicar en el proyecto.
"""
from collections import defaultdict
from datetime import datetime

from models import db, Producto, DetalleVenta, Ticket, Capital, Gasto, Meta


# ---------------------------------------------------------------------------
# Ganancias, gastos y punto de equilibrio
# ---------------------------------------------------------------------------

def ganancia_bruta_total():
    """Suma la ganancia (precio - costo) x cantidad de todas las líneas de venta."""
    total = 0.0
    for detalle in DetalleVenta.query.all():
        total += detalle.ganancia
    return total


def capital_total_invertido():
    total = db.session.query(db.func.sum(Capital.monto)).scalar()
    return total or 0.0


def gastos_totales():
    total = db.session.query(db.func.sum(Gasto.monto)).scalar()
    return total or 0.0


def resumen_financiero():
    """
    Punto de equilibrio: compara el capital invertido contra la ganancia
    bruta (por venta de producto) acumulada. "falta_para_recuperar" indica
    cuánto dinero de ganancia falta por generar.

    "ganancia_neta" resta los gastos operativos (renta, luz, etc.) de esa
    ganancia bruta -- es la ganancia real del negocio. El punto de
    equilibrio se deja calculado sobre la ganancia bruta por producto para
    no mezclar dos cosas distintas en una sola métrica.
    """
    ganancia_bruta = ganancia_bruta_total()
    capital = capital_total_invertido()
    gastos = gastos_totales()
    falta_para_recuperar = max(capital - ganancia_bruta, 0.0)
    punto_equilibrio_alcanzado = ganancia_bruta >= capital and capital > 0

    return {
        "capital_invertido": round(capital, 2),
        "ganancia_bruta": round(ganancia_bruta, 2),
        "gastos_totales": round(gastos, 2),
        "ganancia_neta": round(ganancia_bruta - gastos, 2),
        "falta_para_recuperar_capital": round(falta_para_recuperar, 2),
        "punto_equilibrio_alcanzado": punto_equilibrio_alcanzado,
        "excedente": round(ganancia_bruta - capital, 2) if punto_equilibrio_alcanzado else 0.0,
    }


# ---------------------------------------------------------------------------
# Ranking de productos y sugerencias de estrategia
# ---------------------------------------------------------------------------

def _metricas_producto(producto):
    detalles = producto.detalles_venta
    unidades_vendidas = sum(d.cantidad for d in detalles)
    ganancia_generada = sum(d.ganancia for d in detalles)
    return unidades_vendidas, ganancia_generada


def ranking_productos():
    productos = Producto.query.filter_by(activo=True).all()
    if not productos:
        return []

    filas = []
    for p in productos:
        unidades, ganancia = _metricas_producto(p)
        filas.append({"producto": p, "unidades_vendidas": unidades, "ganancia_generada": ganancia})

    unidades_ordenadas = sorted(f["unidades_vendidas"] for f in filas)
    mitad = len(unidades_ordenadas) // 2
    mediana = unidades_ordenadas[mitad] if unidades_ordenadas else 0

    filas.sort(key=lambda f: f["ganancia_generada"], reverse=True)

    resultado = []
    for f in filas:
        p = f["producto"]
        rotacion_alta = f["unidades_vendidas"] >= mediana and f["unidades_vendidas"] > 0
        estrategia = _sugerir_estrategia(p, rotacion_alta)
        resultado.append({
            "producto_id": p.id,
            "nombre": p.nombre,
            "unidades_vendidas": f["unidades_vendidas"],
            "ganancia_generada": round(f["ganancia_generada"], 2),
            "margen_porcentual": round(p.margen_porcentual * 100, 1),
            "rotacion_alta": rotacion_alta,
            "estrategia_sugerida": estrategia,
        })
    return resultado


def _sugerir_estrategia(producto, rotacion_alta):
    margen_bueno = producto.margen_porcentual >= 0.20  # 20% o más

    if rotacion_alta and margen_bueno:
        return "Producto estrella: aumenta inventario y crea promociones o combos con él."
    if rotacion_alta and not margen_bueno:
        return "Alta demanda con margen bajo: considera subir el precio."
    if not rotacion_alta and producto.stock > 0:
        return "Baja rotación: aplica un descuento o promoción para impulsar la venta."
    return "Desempeño estable: mantén seguimiento."


# ---------------------------------------------------------------------------
# Simulador de cambio de precio
# ---------------------------------------------------------------------------

def simular_cambio_precio(producto, porcentaje):
    unidades_vendidas, ganancia_actual = _metricas_producto(producto)

    nuevo_precio = producto.precio_actual * (1 + porcentaje / 100)
    nuevo_margen_unitario = nuevo_precio - producto.costo
    ganancia_proyectada = nuevo_margen_unitario * unidades_vendidas

    return {
        "producto_id": producto.id,
        "nombre": producto.nombre,
        "precio_actual": producto.precio_actual,
        "precio_simulado": round(nuevo_precio, 2),
        "porcentaje_aplicado": porcentaje,
        "unidades_de_referencia": unidades_vendidas,
        "ganancia_actual": round(ganancia_actual, 2),
        "ganancia_proyectada": round(ganancia_proyectada, 2),
        "diferencia": round(ganancia_proyectada - ganancia_actual, 2),
    }


# ---------------------------------------------------------------------------
# Punto de venta: registrar un ticket con varios productos
# ---------------------------------------------------------------------------

class ErrorVenta(Exception):
    """Error de validación al registrar una venta (carrito, stock, pago, etc.)."""


def registrar_ticket(items_data, metodo_pago, monto_pagado=None, cliente_id=None):
    if not items_data:
        raise ErrorVenta("El carrito está vacío")
    if metodo_pago not in ("efectivo", "tarjeta", "credito"):
        raise ErrorVenta("El método de pago debe ser 'efectivo', 'tarjeta' o 'credito'")
    if metodo_pago == "credito" and not cliente_id:
        raise ErrorVenta("Una venta a crédito necesita un cliente")

    renglones = []
    total = 0.0
    for item in items_data:
        producto = Producto.query.get(int(item.get("producto_id", 0)))
        if not producto or not producto.activo:
            raise ErrorVenta("Hay un producto inválido en el carrito")
        cantidad = int(item.get("cantidad", 0))
        if cantidad <= 0:
            raise ErrorVenta(f"Cantidad inválida para {producto.nombre}")
        if cantidad > producto.stock:
            raise ErrorVenta(f"No hay suficiente stock de {producto.nombre}")
        renglones.append((producto, cantidad))
        total += producto.precio_actual * cantidad

    cambio = None
    if metodo_pago == "efectivo":
        if monto_pagado is None:
            raise ErrorVenta("Debes indicar el monto pagado para un pago en efectivo")
        if monto_pagado < total:
            raise ErrorVenta("El monto pagado es menor al total de la venta")
        cambio = monto_pagado - total

    ticket = Ticket(
        metodo_pago=metodo_pago,
        total=total,
        monto_pagado=monto_pagado,
        cambio=cambio,
        cliente_id=cliente_id,
        pagado=(metodo_pago != "credito"),
    )
    db.session.add(ticket)
    db.session.flush()  # asigna ticket.id sin cerrar la transacción

    for producto, cantidad in renglones:
        db.session.add(DetalleVenta(
            ticket_id=ticket.id,
            producto_id=producto.id,
            cantidad=cantidad,
            precio_unitario=producto.precio_actual,
            costo_unitario=producto.costo,
        ))
        producto.stock -= cantidad

    db.session.commit()
    return ticket


def marcar_ticket_pagado(ticket):
    ticket.pagado = True
    ticket.pagado_en = datetime.utcnow()
    db.session.commit()
    return ticket


def cuentas_por_cobrar():
    return Ticket.query.filter_by(pagado=False).order_by(Ticket.fecha.desc()).all()


# ---------------------------------------------------------------------------
# Ventas por periodo (para la gráfica de tendencia)
# ---------------------------------------------------------------------------

def ventas_por_periodo(agrupacion="dia"):
    if agrupacion == "semana":
        clave = lambda f: f.strftime("%G-W%V")
    elif agrupacion == "mes":
        clave = lambda f: f.strftime("%Y-%m")
    else:
        clave = lambda f: f.strftime("%Y-%m-%d")

    totales = defaultdict(float)
    for ticket in Ticket.query.all():
        totales[clave(ticket.fecha)] += ticket.total

    periodos = sorted(totales.keys())
    return [{"periodo": p, "total": round(totales[p], 2)} for p in periodos]


# ---------------------------------------------------------------------------
# Metas de venta
# ---------------------------------------------------------------------------

def progreso_metas():
    metas = Meta.query.order_by(Meta.fecha_inicio.desc()).all()
    resultado = []
    for m in metas:
        acumulado = 0.0
        for t in Ticket.query.filter(Ticket.fecha >= m.fecha_inicio, Ticket.fecha <= m.fecha_fin).all():
            acumulado += t.total
        porcentaje = (acumulado / m.monto_objetivo * 100) if m.monto_objetivo else 0
        data = m.to_dict()
        data["acumulado"] = round(acumulado, 2)
        data["porcentaje"] = round(min(porcentaje, 999), 1)
        resultado.append(data)
    return resultado
