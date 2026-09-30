import os
import sys

from flask import Flask, request, jsonify, render_template
from models import (
    db, Categoria, Producto, HistorialPrecio, Ticket, DetalleVenta,
    Capital, ConteoInventario,
)
import business_logic as logic


def _base_path():
    """
    Carpeta base para encontrar templates/ y static/.
    - Al correr normal (python app.py, o en Render): la carpeta de este archivo.
    - Empaquetado con PyInstaller (el .exe de escritorio): la carpeta temporal
      donde PyInstaller extrae los archivos (sys._MEIPASS).
    """
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(_base_path(), "templates"),
        static_folder=os.path.join(_base_path(), "static"),
    )

    # En la web (Render) usa manager_tapper.db junto al código, como antes.
    # En el .exe de escritorio, desktop_app.py define esta variable de entorno
    # para guardar la base de datos en la carpeta del usuario.
    db_path = os.environ.get("MANAGER_TAPPER_DB", "manager_tapper.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()

    # -------------------------------------------------------------- vistas
    @app.route("/")
    def index():
        return render_template("index.html")

    # ----------------------------------------------------------- categorias
    @app.route("/api/categorias", methods=["GET"])
    def listar_categorias():
        categorias = Categoria.query.order_by(Categoria.nombre).all()
        return jsonify([c.to_dict() for c in categorias])

    @app.route("/api/categorias", methods=["POST"])
    def crear_categoria():
        data = request.get_json(force=True)
        nombre = (data.get("nombre") or "").strip()
        if not nombre:
            return jsonify({"error": "El nombre no puede estar vacío"}), 400
        if Categoria.query.filter_by(nombre=nombre).first():
            return jsonify({"error": "Ya existe esa categoría"}), 400
        categoria = Categoria(nombre=nombre)
        db.session.add(categoria)
        db.session.commit()
        return jsonify(categoria.to_dict()), 201

    # ------------------------------------------------------------ productos
    @app.route("/api/productos", methods=["GET"])
    def listar_productos():
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        return jsonify([p.to_dict() for p in productos])

    @app.route("/api/productos", methods=["POST"])
    def crear_producto():
        data = request.get_json(force=True)
        try:
            producto = Producto(
                nombre=data["nombre"],
                costo=float(data["costo"]),
                precio_actual=float(data["precio"]),
                stock=int(data.get("stock", 0)),
                categoria_id=int(data["categoria_id"]) if data.get("categoria_id") else None,
            )
        except (KeyError, ValueError) as e:
            return jsonify({"error": f"Datos inválidos: {e}"}), 400

        db.session.add(producto)
        db.session.commit()
        return jsonify(producto.to_dict()), 201

    @app.route("/api/productos/<int:producto_id>", methods=["PUT"])
    def editar_producto(producto_id):
        producto = Producto.query.get_or_404(producto_id)
        data = request.get_json(force=True)
        try:
            if "nombre" in data:
                producto.nombre = data["nombre"]
            if "costo" in data:
                producto.costo = float(data["costo"])
            if "stock" in data:
                producto.stock = int(data["stock"])
            if "categoria_id" in data:
                producto.categoria_id = int(data["categoria_id"]) if data["categoria_id"] else None
        except ValueError as e:
            return jsonify({"error": f"Datos inválidos: {e}"}), 400
        db.session.commit()
        return jsonify(producto.to_dict())

    @app.route("/api/productos/<int:producto_id>", methods=["DELETE"])
    def eliminar_producto(producto_id):
        producto = Producto.query.get_or_404(producto_id)
        producto.activo = False
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/productos/<int:producto_id>/precio", methods=["PUT"])
    def actualizar_precio(producto_id):
        producto = Producto.query.get_or_404(producto_id)
        data = request.get_json(force=True)
        try:
            nuevo_precio = float(data["precio"])
        except (KeyError, ValueError):
            return jsonify({"error": "Debes enviar 'precio' numérico"}), 400

        historial = HistorialPrecio(
            producto_id=producto.id,
            precio_anterior=producto.precio_actual,
            precio_nuevo=nuevo_precio,
        )
        producto.precio_actual = nuevo_precio
        db.session.add(historial)
        db.session.commit()
        return jsonify(producto.to_dict())

    @app.route("/api/productos/<int:producto_id>/historial", methods=["GET"])
    def historial_precio(producto_id):
        producto = Producto.query.get_or_404(producto_id)
        return jsonify([h.to_dict() for h in producto.historial_precios])

    # ---------------------------------------------------------------- capital
    @app.route("/api/capital", methods=["GET"])
    def listar_capital():
        aportes = Capital.query.order_by(Capital.fecha.desc()).all()
        return jsonify([c.to_dict() for c in aportes])

    @app.route("/api/capital", methods=["POST"])
    def registrar_capital():
        data = request.get_json(force=True)
        try:
            aporte = Capital(monto=float(data["monto"]), descripcion=data.get("descripcion"))
        except (KeyError, ValueError):
            return jsonify({"error": "Debes enviar 'monto' numérico"}), 400
        db.session.add(aporte)
        db.session.commit()
        return jsonify(aporte.to_dict()), 201

    # ------------------------------------------------- punto de venta (POS)
    @app.route("/api/ventas", methods=["POST"])
    def registrar_venta():
        data = request.get_json(force=True)
        monto_pagado = data.get("monto_pagado")
        try:
            monto_pagado = float(monto_pagado) if monto_pagado is not None else None
        except ValueError:
            return jsonify({"error": "monto_pagado debe ser numérico"}), 400

        try:
            ticket = logic.registrar_ticket(
                items_data=data.get("items") or [],
                metodo_pago=data.get("metodo_pago"),
                monto_pagado=monto_pagado,
            )
        except logic.ErrorVenta as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

        return jsonify(ticket.to_dict()), 201

    @app.route("/api/tickets", methods=["GET"])
    def listar_tickets():
        tickets = Ticket.query.order_by(Ticket.fecha.desc()).all()
        return jsonify([t.to_dict(incluir_items=False) for t in tickets])

    @app.route("/api/tickets/<int:ticket_id>", methods=["GET"])
    def ver_ticket(ticket_id):
        ticket = Ticket.query.get_or_404(ticket_id)
        return jsonify(ticket.to_dict(incluir_items=True))

    # ------------------------------------------------------------- inventario
    @app.route("/api/inventario/alertas", methods=["GET"])
    def alertas_inventario():
        productos = Producto.query.filter_by(activo=True).all()
        return jsonify([p.to_dict() for p in productos if p.stock_bajo])

    @app.route("/api/inventario/conteo", methods=["POST"])
    def registrar_conteo():
        data = request.get_json(force=True)
        producto = Producto.query.get_or_404(int(data.get("producto_id", 0)))
        try:
            contado = int(data["stock_contado"])
        except (KeyError, ValueError):
            return jsonify({"error": "Debes enviar 'stock_contado' entero"}), 400

        conteo = ConteoInventario(
            producto_id=producto.id,
            stock_esperado=producto.stock,
            stock_contado=contado,
        )
        db.session.add(conteo)
        db.session.commit()
        return jsonify(conteo.to_dict()), 201

    # --------------------------------------------------------------- reportes
    @app.route("/api/resumen", methods=["GET"])
    def resumen():
        return jsonify(logic.resumen_financiero())

    @app.route("/api/ranking", methods=["GET"])
    def ranking():
        return jsonify(logic.ranking_productos())

    @app.route("/api/simular-precio", methods=["POST"])
    def simular_precio():
        data = request.get_json(force=True)
        producto = Producto.query.get_or_404(int(data.get("producto_id", 0)))
        try:
            porcentaje = float(data["porcentaje"])
        except (KeyError, ValueError):
            return jsonify({"error": "Debes enviar 'porcentaje' numérico (ej. 10 o -15)"}), 400
        return jsonify(logic.simular_cambio_precio(producto, porcentaje))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
