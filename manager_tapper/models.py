"""
Modelos de datos de Manager Tapper.

Tablas:
- Producto: catálogo (nombre, costo, precio actual, stock)
- HistorialPrecio: registro de cada cambio de precio de un producto
- Venta: cada venta registrada (producto, cantidad, precio al momento de vender)
- Capital: aportes de capital invertido en el negocio
- ConteoInventario: conteos físicos para detectar desfases/pérdidas
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Debajo de este nivel de stock, un producto se considera "stock bajo"
UMBRAL_STOCK_BAJO = 5


class Producto(db.Model):
    __tablename__ = "productos"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False, unique=True)
    costo = db.Column(db.Float, nullable=False)
    precio_actual = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    ventas = db.relationship("Venta", backref="producto", lazy=True)
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


class Venta(db.Model):
    __tablename__ = "ventas"

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Float, nullable=False)  # precio al momento de vender
    costo_unitario = db.Column(db.Float, nullable=False)   # costo al momento de vender
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

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
            "ganancia": round(self.ganancia, 2),
            "fecha": self.fecha.isoformat(),
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
