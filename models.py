"""
Modelos de datos de Manager Tapper.

Tablas:
- Usuario: la cuenta con la que se inicia sesión (contraseña con hash)
- Categoria: categorías para organizar el catálogo
- Producto: catálogo (nombre, costo, precio actual, stock, categoría, activo)
- HistorialPrecio: registro de cada cambio de precio de un producto
- Cliente: clientes para ventas a crédito
- Ticket: una venta del punto de venta (puede tener varios productos,
  método de pago efectivo/tarjeta/crédito)
- DetalleVenta: cada línea de producto dentro de un Ticket
- Capital: aportes de capital invertido en el negocio
- Gasto: gastos operativos del negocio aparte del costo de producto (renta, luz, etc.)
- Meta: meta de ventas para un rango de fechas
- ConteoInventario: conteos físicos para detectar desfases/pérdidas

Nota sobre "eliminar" productos: un producto nunca se borra de verdad si ya
tiene ventas asociadas (rompería el historial), así que "eliminar" solo lo
marca como inactivo (`activo = False`) y deja de aparecer en el catálogo.
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Debajo de este nivel de stock, un producto se considera "stock bajo"
UMBRAL_STOCK_BAJO = 5


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)


class Categoria(db.Model):
    __tablename__ = "categorias"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), nullable=False, unique=True)

    productos = db.relationship("Producto", backref="categoria", lazy=True)

    def to_dict(self):
        return {"id": self.id, "nombre": self.nombre}


class Producto(db.Model):
    __tablename__ = "productos"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False, unique=True)
    costo = db.Column(db.Float, nullable=False)
    precio_actual = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categorias.id"), nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    historial_precios = db.relationship(
        "HistorialPrecio", backref="producto", lazy=True,
        order_by="HistorialPrecio.fecha.desc()",
    )

    @property
    def margen_unitario(self):
        return self.precio_actual - self.costo

    @property
    def margen_porcentual(self):
        if self.precio_actual == 0:
            return 0
        return self.margen_unitario / self.precio_actual

    @property
    def stock_bajo(self):
        return self.stock <= UMBRAL_STOCK_BAJO

    def to_dict(self):
        return {
            "id": self.id,
            "nombre": self.nombre,
            "costo": self.costo,
            "precio_actual": self.precio_actual,
            "stock": self.stock,
            "stock_bajo": self.stock_bajo,
            "margen_unitario": round(self.margen_unitario, 2),
            "margen_porcentual": round(self.margen_porcentual * 100, 1),
            "categoria_id": self.categoria_id,
            "categoria_nombre": self.categoria.nombre if self.categoria else None,
            "activo": self.activo,
        }


class HistorialPrecio(db.Model):
    __tablename__ = "historial_precios"

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False)
    precio_anterior = db.Column(db.Float, nullable=False)
    precio_nuevo = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "precio_anterior": self.precio_anterior,
            "precio_nuevo": self.precio_nuevo,
            "fecha": self.fecha.isoformat(),
        }


class Cliente(db.Model):
    __tablename__ = "clientes"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    contacto = db.Column(db.String(120))

    tickets = db.relationship("Ticket", backref="cliente", lazy=True)

    def to_dict(self):
        return {"id": self.id, "nombre": self.nombre, "contacto": self.contacto}


class Ticket(db.Model):
    """Una venta del punto de venta. Puede incluir varios productos."""
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    metodo_pago = db.Column(db.String(20), nullable=False)  # "efectivo" | "tarjeta" | "credito"
    total = db.Column(db.Float, nullable=False)
    monto_pagado = db.Column(db.Float)  # solo aplica si metodo_pago == "efectivo"
    cambio = db.Column(db.Float)        # solo aplica si metodo_pago == "efectivo"
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=True)
    pagado = db.Column(db.Boolean, nullable=False, default=True)  # False mientras una venta a credito siga pendiente
    pagado_en = db.Column(db.DateTime, nullable=True)

    items = db.relationship(
        "DetalleVenta", backref="ticket", lazy=True, order_by="DetalleVenta.id"
    )

    def to_dict(self, incluir_items=True):
        data = {
            "id": self.id,
            "fecha": self.fecha.isoformat(),
            "metodo_pago": self.metodo_pago,
            "total": round(self.total, 2),
            "monto_pagado": round(self.monto_pagado, 2) if self.monto_pagado is not None else None,
            "cambio": round(self.cambio, 2) if self.cambio is not None else None,
            "cliente_id": self.cliente_id,
            "cliente_nombre": self.cliente.nombre if self.cliente else None,
            "pagado": self.pagado,
            "pagado_en": self.pagado_en.isoformat() if self.pagado_en else None,
            "num_items": len(self.items),
        }
        if incluir_items:
            data["items"] = [i.to_dict() for i in self.items]
        return data


class DetalleVenta(db.Model):
    """Una línea de producto dentro de un Ticket (cantidad, precio y costo al momento de vender)."""
    __tablename__ = "detalle_ventas"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Float, nullable=False)
    costo_unitario = db.Column(db.Float, nullable=False)

    producto = db.relationship("Producto", backref="detalles_venta")

    @property
    def subtotal(self):
        return self.precio_unitario * self.cantidad

    @property
    def ganancia(self):
        return (self.precio_unitario - self.costo_unitario) * self.cantidad

    def to_dict(self):
        return {
            "id": self.id,
            "producto_id": self.producto_id,
            "producto_nombre": self.producto.nombre if self.producto else None,
            "cantidad": self.cantidad,
            "precio_unitario": self.precio_unitario,
            "subtotal": round(self.subtotal, 2),
            "ganancia": round(self.ganancia, 2),
        }


class Capital(db.Model):
    __tablename__ = "capital"

    id = db.Column(db.Integer, primary_key=True)
    monto = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(200))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "monto": self.monto,
            "descripcion": self.descripcion,
            "fecha": self.fecha.isoformat(),
        }


class Gasto(db.Model):
    __tablename__ = "gastos"

    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(200), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    categoria = db.Column(db.String(80))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "descripcion": self.descripcion,
            "monto": self.monto,
            "categoria": self.categoria,
            "fecha": self.fecha.isoformat(),
        }


class Meta(db.Model):
    __tablename__ = "metas"

    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(200), nullable=False)
    monto_objetivo = db.Column(db.Float, nullable=False)
    fecha_inicio = db.Column(db.DateTime, nullable=False)
    fecha_fin = db.Column(db.DateTime, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "descripcion": self.descripcion,
            "monto_objetivo": self.monto_objetivo,
            "fecha_inicio": self.fecha_inicio.isoformat(),
            "fecha_fin": self.fecha_fin.isoformat(),
        }


class ConteoInventario(db.Model):
    __tablename__ = "conteos_inventario"

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False)
    stock_esperado = db.Column(db.Integer, nullable=False)
    stock_contado = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def desfase(self):
        return self.stock_contado - self.stock_esperado

    def to_dict(self):
        return {
            "id": self.id,
            "producto_id": self.producto_id,
            "stock_esperado": self.stock_esperado,
            "stock_contado": self.stock_contado,
            "desfase": self.desfase,
            "hay_perdida": self.desfase < 0,
            "fecha": self.fecha.isoformat(),
        }
