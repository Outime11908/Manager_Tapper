from flask import Flask, request, jsonify, render_template
from models import db, Producto, HistorialPrecio, Venta, Capital, ConteoInventario
import business_logic as logic


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///manager_tapper.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()

    # -------------------------------------------------------------- vistas
    @app.route("/")
    def index():
        return render_template("index.html")

    # ------------------------------------------------------------ productos
    @app.route("/api/productos", methods=["GET"])
    def listar_productos():
        productos = Producto.query.order_by(Producto.nombre).all()
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
            )
        except (KeyError, ValueError) as e:
            return jsonify({"error": f"Datos inválidos: {e}"}), 400

        db.session.add(producto)
        db.session.commit()
        return jsonify(producto.to_dict()), 201

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

    # ----------------------------------------------------------------- ventas
    @app.route("/api/ventas", methods=["GET"])
    def listar_ventas():
        ventas = Venta.query.order_by(Venta.fecha.desc()).all()
        return jsonify([v.to_dict() for v in ventas])

    @app.route("/api/ventas", methods=["POST"])
    def registrar_venta():
        data = request.get_json(force=True)
        producto = Producto.query.get_or_404(int(data.get("producto_id", 0)))
        try:
            cantidad = int(data["cantidad"])
        except (KeyError, ValueError):
            return jsonify({"error": "Debes enviar 'cantidad' entera"}), 400

        if cantidad <= 0:
            return jsonify({"error": "La cantidad debe ser mayor a cero"}), 400
        if cantidad > producto.stock:
            return jsonify({"error": "No hay suficiente stock para esta venta"}), 400

        venta = Venta(
            producto_id=producto.id,
            cantidad=cantidad,
            precio_unitario=producto.precio_actual,
            costo_unitario=producto.costo,
        )
        producto.stock -= cantidad
        db.session.add(venta)
        db.session.commit()
        return jsonify(venta.to_dict()), 201

    # ------------------------------------------------------------- inventario
    @app.route("/api/inventario/alertas", methods=["GET"])
    def alertas_inventario():
        productos = Producto.query.all()
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
