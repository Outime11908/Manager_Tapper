import os
import sys
from datetime import datetime, time as dtime
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template, session, redirect, url_for, send_file,
)
from werkzeug.security import generate_password_hash, check_password_hash

from models import (
    db, Usuario, Categoria, Producto, HistorialPrecio, Cliente, Ticket, DetalleVenta,
    Capital, Gasto, Meta, ConteoInventario,
)
import business_logic as logic
import reportes as rep


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
    # Define SECRET_KEY como variable de entorno en Render para producción;
    # este valor por defecto alcanza para uso local/escolar.
    app.secret_key = os.environ.get("SECRET_KEY", "manager-tapper-clave-de-desarrollo")
    db.init_app(app)

    with app.app_context():
        db.create_all()

    # ----------------------------------------------------------------- auth
    def login_required(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "usuario_id" not in session:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "No autenticado"}), 401
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return wrapper

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        if Usuario.query.count() > 0:
            return redirect(url_for("login"))
        error = None
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if not username or len(password) < 4:
                error = "El usuario no puede estar vacío y la contraseña debe tener al menos 4 caracteres."
            else:
                db.session.add(Usuario(username=username, password_hash=generate_password_hash(password)))
                db.session.commit()
                return redirect(url_for("login"))
        return render_template("setup.html", error=error)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if Usuario.query.count() == 0:
            return redirect(url_for("setup"))
        error = None
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            usuario = Usuario.query.filter_by(username=username).first()
            if usuario and check_password_hash(usuario.password_hash, password):
                session["usuario_id"] = usuario.id
                return redirect(url_for("index"))
            error = "Usuario o contraseña incorrectos."
        return render_template("login.html", error=error)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # -------------------------------------------------------------- vistas
    @app.route("/")
    @login_required
    def index():
        return render_template("index.html")

    # ----------------------------------------------------------- categorias
    @app.route("/api/categorias", methods=["GET"])
    @login_required
    def listar_categorias():
        return jsonify([c.to_dict() for c in Categoria.query.order_by(Categoria.nombre).all()])

    @app.route("/api/categorias", methods=["POST"])
    @login_required
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
    @login_required
    def listar_productos():
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        return jsonify([p.to_dict() for p in productos])

    @app.route("/api/productos", methods=["POST"])
    @login_required
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
    @login_required
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
    @login_required
    def eliminar_producto(producto_id):
        producto = Producto.query.get_or_404(producto_id)
        producto.activo = False
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/productos/<int:producto_id>/precio", methods=["PUT"])
    @login_required
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
    @login_required
    def historial_precio(producto_id):
        producto = Producto.query.get_or_404(producto_id)
        return jsonify([h.to_dict() for h in producto.historial_precios])

    # ---------------------------------------------------------------- capital
    @app.route("/api/capital", methods=["GET"])
    @login_required
    def listar_capital():
        return jsonify([c.to_dict() for c in Capital.query.order_by(Capital.fecha.desc()).all()])

    @app.route("/api/capital", methods=["POST"])
    @login_required
    def registrar_capital():
        data = request.get_json(force=True)
        try:
            aporte = Capital(monto=float(data["monto"]), descripcion=data.get("descripcion"))
        except (KeyError, ValueError):
            return jsonify({"error": "Debes enviar 'monto' numérico"}), 400
        db.session.add(aporte)
        db.session.commit()
        return jsonify(aporte.to_dict()), 201

    # ----------------------------------------------------------------- gastos
    @app.route("/api/gastos", methods=["GET"])
    @login_required
    def listar_gastos():
        return jsonify([g.to_dict() for g in Gasto.query.order_by(Gasto.fecha.desc()).all()])

    @app.route("/api/gastos", methods=["POST"])
    @login_required
    def crear_gasto():
        data = request.get_json(force=True)
        try:
            gasto = Gasto(
                descripcion=data["descripcion"],
                monto=float(data["monto"]),
                categoria=data.get("categoria"),
            )
        except (KeyError, ValueError) as e:
            return jsonify({"error": f"Datos inválidos: {e}"}), 400
        db.session.add(gasto)
        db.session.commit()
        return jsonify(gasto.to_dict()), 201

    # --------------------------------------------------------------- clientes
    @app.route("/api/clientes", methods=["GET"])
    @login_required
    def listar_clientes():
        return jsonify([c.to_dict() for c in Cliente.query.order_by(Cliente.nombre).all()])

    @app.route("/api/clientes", methods=["POST"])
    @login_required
    def crear_cliente():
        data = request.get_json(force=True)
        nombre = (data.get("nombre") or "").strip()
        if not nombre:
            return jsonify({"error": "El nombre es requerido"}), 400
        cliente = Cliente(nombre=nombre, contacto=data.get("contacto"))
        db.session.add(cliente)
        db.session.commit()
        return jsonify(cliente.to_dict()), 201

    # ------------------------------------------------------------------ metas
    @app.route("/api/metas", methods=["GET"])
    @login_required
    def listar_metas():
        return jsonify(logic.progreso_metas())

    @app.route("/api/metas", methods=["POST"])
    @login_required
    def crear_meta():
        data = request.get_json(force=True)
        try:
            inicio = datetime.fromisoformat(data["fecha_inicio"])
            fin_date = datetime.fromisoformat(data["fecha_fin"]).date()
            meta = Meta(
                descripcion=data["descripcion"],
                monto_objetivo=float(data["monto_objetivo"]),
                fecha_inicio=inicio,
                fecha_fin=datetime.combine(fin_date, dtime(23, 59, 59)),
            )
        except (KeyError, ValueError) as e:
            return jsonify({"error": f"Datos inválidos: {e}"}), 400
        db.session.add(meta)
        db.session.commit()
        return jsonify(meta.to_dict()), 201

    # ------------------------------------------------- punto de venta (POS)
    @app.route("/api/ventas", methods=["POST"])
    @login_required
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
                cliente_id=int(data["cliente_id"]) if data.get("cliente_id") else None,
            )
        except logic.ErrorVenta as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

        return jsonify(ticket.to_dict()), 201

    @app.route("/api/tickets", methods=["GET"])
    @login_required
    def listar_tickets():
        tickets = Ticket.query.order_by(Ticket.fecha.desc()).all()
        return jsonify([t.to_dict(incluir_items=False) for t in tickets])

    @app.route("/api/tickets/<int:ticket_id>", methods=["GET"])
    @login_required
    def ver_ticket(ticket_id):
        ticket = Ticket.query.get_or_404(ticket_id)
        return jsonify(ticket.to_dict(incluir_items=True))

    @app.route("/api/tickets/<int:ticket_id>/marcar-pagado", methods=["POST"])
    @login_required
    def marcar_pagado(ticket_id):
        ticket = Ticket.query.get_or_404(ticket_id)
        logic.marcar_ticket_pagado(ticket)
        return jsonify(ticket.to_dict())

    @app.route("/api/cuentas-por-cobrar", methods=["GET"])
    @login_required
    def cuentas_por_cobrar():
        return jsonify([t.to_dict(incluir_items=False) for t in logic.cuentas_por_cobrar()])

    # ------------------------------------------------------------- inventario
    @app.route("/api/inventario/alertas", methods=["GET"])
    @login_required
    def alertas_inventario():
        productos = Producto.query.filter_by(activo=True).all()
        return jsonify([p.to_dict() for p in productos if p.stock_bajo])

    @app.route("/api/inventario/conteo", methods=["POST"])
    @login_required
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
    @login_required
    def resumen():
        return jsonify(logic.resumen_financiero())

    @app.route("/api/ranking", methods=["GET"])
    @login_required
    def ranking():
        return jsonify(logic.ranking_productos())

    @app.route("/api/simular-precio", methods=["POST"])
    @login_required
    def simular_precio():
        data = request.get_json(force=True)
        producto = Producto.query.get_or_404(int(data.get("producto_id", 0)))
        try:
            porcentaje = float(data["porcentaje"])
        except (KeyError, ValueError):
            return jsonify({"error": "Debes enviar 'porcentaje' numérico (ej. 10 o -15)"}), 400
        return jsonify(logic.simular_cambio_precio(producto, porcentaje))

    @app.route("/api/ventas-por-periodo", methods=["GET"])
    @login_required
    def ventas_por_periodo():
        agrupacion = request.args.get("agrupacion", "dia")
        return jsonify(logic.ventas_por_periodo(agrupacion))

    @app.route("/api/reportes/ventas.xlsx", methods=["GET"])
    @login_required
    def reporte_ventas_excel():
        tickets = Ticket.query.order_by(Ticket.fecha).all()
        buf = rep.generar_excel_ventas(tickets)
        return send_file(
            buf, as_attachment=True, download_name="ventas.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.route("/api/reportes/resumen.pdf", methods=["GET"])
    @login_required
    def reporte_resumen_pdf():
        resumen_data = logic.resumen_financiero()
        tickets = Ticket.query.order_by(Ticket.fecha.desc()).all()
        buf = rep.generar_pdf_resumen(resumen_data, tickets)
        return send_file(buf, as_attachment=True, download_name="reporte.pdf", mimetype="application/pdf")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
