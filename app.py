import os
import secrets
import sys
import time
from collections import defaultdict
from datetime import datetime, time as dtime
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template, session, redirect, url_for, send_file, g,
)
from sqlalchemy.exc import IntegrityError
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

from models import (
    db, Negocio, Usuario, Categoria, Producto, HistorialPrecio, Cliente, Ticket, DetalleVenta,
    Capital, Gasto, Meta, ConteoInventario,
)
import business_logic as logic
import reportes as rep

# ----------------------------------------------- límites de intentos (en memoria)
# Se reinician si el proceso se reinicia y no se comparten entre varias
# instancias del servidor; con una sola instancia en Render alcanzan.
INTENTOS_MAXIMOS = 5
BLOQUEO_SEGUNDOS = 5 * 60
_intentos_login = defaultdict(list)  # clave "ip:usuario" -> [timestamps de fallos]

# Evita que alguien cree cientos de negocios falsos desde la misma conexión.
REGISTROS_MAXIMOS = int(os.environ.get("MANAGER_TAPPER_REGISTROS_MAX", "5"))
REGISTROS_VENTANA = 60 * 60
_registros_ip = defaultdict(list)  # ip -> [timestamps de registros]

MIN_PASSWORD = 8


def _clave_intentos():
    return f"{request.remote_addr}:{request.form.get('username', '')}"


def _bloqueado():
    ahora = time.time()
    intentos = [t for t in _intentos_login[_clave_intentos()] if ahora - t < BLOQUEO_SEGUNDOS]
    _intentos_login[_clave_intentos()] = intentos
    return len(intentos) >= INTENTOS_MAXIMOS


def _registrar_intento_fallido():
    _intentos_login[_clave_intentos()].append(time.time())


def _limpiar_intentos():
    _intentos_login.pop(_clave_intentos(), None)


def _registros_excedidos():
    ahora = time.time()
    recientes = [t for t in _registros_ip[request.remote_addr] if ahora - t < REGISTROS_VENTANA]
    _registros_ip[request.remote_addr] = recientes
    return len(recientes) >= REGISTROS_MAXIMOS


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

    # En Render hay un proxy delante: sin esto, request.remote_addr sería la IP
    # del proxy y los límites de intentos tratarían a todos como una sola persona.
    if os.environ.get("RENDER"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # En la web (Render) usa manager_tapper.db junto al código, como antes.
    # En el .exe de escritorio, desktop_app.py define esta variable de entorno
    # para guardar la base de datos en la carpeta del usuario.
    db_path = os.environ.get("MANAGER_TAPPER_DB", "manager_tapper.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # Define SECRET_KEY como variable de entorno en Render para producción;
    # este valor por defecto alcanza solo para desarrollo local.
    app.secret_key = os.environ.get("SECRET_KEY", "manager-tapper-clave-de-desarrollo")

    # ---- cookies de sesión más seguras ----
    app.config["SESSION_COOKIE_HTTPONLY"] = True       # JS no puede leer la cookie
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"       # mitiga CSRF entre sitios
    # "Secure" exige HTTPS -- Render ya sirve por HTTPS; en Render esta
    # variable de entorno viene definida automáticamente.
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RENDER") is not None

    db.init_app(app)

    with app.app_context():
        db.create_all()

    # ---- encabezados de seguridad en cada respuesta ----
    @app.after_request
    def agregar_encabezados_seguridad(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:;"
        )
        return resp

    # ----------------------------------------------------------------- auth
    def login_required(f):
        """Exige sesión válida y deja el negocio actual en g.negocio.
        Si el negocio fue suspendido, la sesión deja de servir de inmediato."""
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "usuario_id" in session and "negocio_id" in session:
                usuario = db.session.get(Usuario, session["usuario_id"])
                negocio = db.session.get(Negocio, session["negocio_id"])
                if usuario and negocio and negocio.activo and usuario.negocio_id == negocio.id:
                    g.negocio = negocio
                    g.usuario = usuario
                    return f(*args, **kwargs)
                session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"error": "No autenticado"}), 401
            return redirect(url_for("login"))
        return wrapper

    # ---- consultas SIEMPRE limitadas al negocio actual ----
    def mis(modelo):
        """Query de `modelo` solo con filas del negocio de la sesión."""
        return modelo.query.filter_by(negocio_id=g.negocio.id)

    def mio_o_404(modelo, id_):
        """Una fila por id, pero solo si es de mi negocio (si no, 404 igual que
        si no existiera: así no se puede adivinar qué ids existen en otros negocios)."""
        return mis(modelo).filter_by(id=id_).first_or_404()

    def guardar_o_error(mensaje_duplicado):
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": mensaje_duplicado}), 400
        return None

    def entero_o_none(valor):
        try:
            return int(valor)
        except (TypeError, ValueError):
            return None

    # ---- token anti-CSRF para los formularios de login/registro ----
    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)
        return session["csrf_token"]

    def csrf_valido():
        enviado = request.form.get("csrf_token", "")
        return enviado and secrets.compare_digest(enviado, session.get("csrf_token", ""))

    @app.route("/terminos")
    def terminos():
        return render_template(
            "terminos.html",
            TITULAR=os.environ.get("MANAGER_TAPPER_TITULAR", "[nombre del titular / empresa]"),
            CONTACTO=os.environ.get("MANAGER_TAPPER_CONTACTO", "[correo de contacto]"),
        )

    @app.route("/setup")
    def setup_antiguo():
        # Enlace viejo de cuando solo existía el primer usuario.
        return redirect(url_for("registro"))

    @app.route("/registro", methods=["GET", "POST"])
    def registro():
        if "usuario_id" in session:
            return redirect(url_for("index"))
        error = None
        if request.method == "POST":
            negocio_nombre = request.form.get("negocio", "").strip()
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            acepto = request.form.get("acepto_terminos") == "on"
            if not csrf_valido():
                error = "Tu sesión expiró, intenta de nuevo."
            elif _registros_excedidos():
                error = "Se crearon demasiadas cuentas desde esta conexión. Intenta más tarde."
            elif not negocio_nombre or not username or "@" not in email or "." not in email:
                error = "Completa el nombre del negocio, el usuario y un correo válido."
            elif len(password) < MIN_PASSWORD:
                error = f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres."
            elif not acepto:
                error = "Debes aceptar los términos y condiciones para crear tu cuenta."
            elif Usuario.query.filter_by(username=username).first():
                error = "Ese usuario ya está en uso. Elige otro."
            elif Usuario.query.filter_by(email=email).first():
                error = "Ya existe una cuenta con ese correo."
            else:
                try:
                    negocio = Negocio(nombre=negocio_nombre)
                    db.session.add(negocio)
                    db.session.flush()
                    usuario = Usuario(
                        negocio_id=negocio.id,
                        username=username,
                        email=email,
                        password_hash=generate_password_hash(password),
                        rol="dueno",
                        terminos_aceptados_en=datetime.utcnow(),
                    )
                    db.session.add(usuario)
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    error = "Ese usuario o correo ya está en uso."
                else:
                    _registros_ip[request.remote_addr].append(time.time())
                    session.clear()
                    session["usuario_id"] = usuario.id
                    session["negocio_id"] = negocio.id
                    return redirect(url_for("index"))
        return render_template(
            "registro.html", error=error, csrf_token=csrf_token(), valores=request.form,
            min_password=MIN_PASSWORD,
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if "usuario_id" in session:
            return redirect(url_for("index"))
        error = None
        if request.method == "POST":
            if not csrf_valido():
                error = "Tu sesión expiró, intenta de nuevo."
            elif _bloqueado():
                error = "Demasiados intentos fallidos. Espera unos minutos e intenta de nuevo."
            else:
                username = request.form.get("username", "")
                password = request.form.get("password", "")
                usuario = Usuario.query.filter_by(username=username).first()
                if usuario and check_password_hash(usuario.password_hash, password):
                    if not usuario.negocio.activo:
                        error = "Esta cuenta está suspendida. Contacta a soporte."
                    else:
                        _limpiar_intentos()
                        session.clear()
                        session["usuario_id"] = usuario.id
                        session["negocio_id"] = usuario.negocio_id
                        return redirect(url_for("index"))
                else:
                    _registrar_intento_fallido()
                    error = "Usuario o contraseña incorrectos."
        return render_template("login.html", error=error, csrf_token=csrf_token())

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # -------------------------------------------------------------- vistas
    @app.route("/")
    @login_required
    def index():
        return render_template("index.html", negocio_nombre=g.negocio.nombre)

    # ----------------------------------------------------------- categorias
    @app.route("/api/categorias", methods=["GET"])
    @login_required
    def listar_categorias():
        return jsonify([c.to_dict() for c in mis(Categoria).order_by(Categoria.nombre).all()])

    @app.route("/api/categorias", methods=["POST"])
    @login_required
    def crear_categoria():
        data = request.get_json(force=True)
        nombre = (data.get("nombre") or "").strip()
        if not nombre:
            return jsonify({"error": "El nombre no puede estar vacío"}), 400
        categoria = Categoria(negocio_id=g.negocio.id, nombre=nombre)
        db.session.add(categoria)
        err = guardar_o_error("Ya existe esa categoría")
        if err:
            return err
        return jsonify(categoria.to_dict()), 201

    def categoria_valida(categoria_id):
        """True si la categoría es None (sin categoría) o pertenece a mi negocio."""
        if categoria_id is None:
            return True
        return mis(Categoria).filter_by(id=categoria_id).first() is not None

    # ------------------------------------------------------------ productos
    @app.route("/api/productos", methods=["GET"])
    @login_required
    def listar_productos():
        productos = mis(Producto).filter_by(activo=True).order_by(Producto.nombre).all()
        return jsonify([p.to_dict() for p in productos])

    @app.route("/api/productos", methods=["POST"])
    @login_required
    def crear_producto():
        data = request.get_json(force=True)
        try:
            categoria_id = int(data["categoria_id"]) if data.get("categoria_id") else None
            producto = Producto(
                negocio_id=g.negocio.id,
                nombre=data["nombre"],
                costo=float(data["costo"]),
                precio_actual=float(data["precio"]),
                stock=int(data.get("stock", 0)),
                categoria_id=categoria_id,
            )
        except (KeyError, ValueError) as e:
            return jsonify({"error": f"Datos inválidos: {e}"}), 400
        if not categoria_valida(categoria_id):
            return jsonify({"error": "Categoría no válida"}), 400
        db.session.add(producto)
        err = guardar_o_error("Ya existe un producto con ese nombre")
        if err:
            return err
        return jsonify(producto.to_dict()), 201

    @app.route("/api/productos/<int:producto_id>", methods=["PUT"])
    @login_required
    def editar_producto(producto_id):
        producto = mio_o_404(Producto, producto_id)
        data = request.get_json(force=True)
        try:
            if "nombre" in data:
                producto.nombre = data["nombre"]
            if "costo" in data:
                producto.costo = float(data["costo"])
            if "stock" in data:
                producto.stock = int(data["stock"])
            if "categoria_id" in data:
                nueva = int(data["categoria_id"]) if data["categoria_id"] else None
                if not categoria_valida(nueva):
                    return jsonify({"error": "Categoría no válida"}), 400
                producto.categoria_id = nueva
        except ValueError as e:
            return jsonify({"error": f"Datos inválidos: {e}"}), 400
        err = guardar_o_error("Ya existe un producto con ese nombre")
        if err:
            return err
        return jsonify(producto.to_dict())

    @app.route("/api/productos/<int:producto_id>", methods=["DELETE"])
    @login_required
    def eliminar_producto(producto_id):
        producto = mio_o_404(Producto, producto_id)
        producto.activo = False
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/productos/<int:producto_id>/precio", methods=["PUT"])
    @login_required
    def actualizar_precio(producto_id):
        producto = mio_o_404(Producto, producto_id)
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
        producto = mio_o_404(Producto, producto_id)
        return jsonify([h.to_dict() for h in producto.historial_precios])

    # ---------------------------------------------------------------- capital
    @app.route("/api/capital", methods=["GET"])
    @login_required
    def listar_capital():
        return jsonify([c.to_dict() for c in mis(Capital).order_by(Capital.fecha.desc()).all()])

    @app.route("/api/capital", methods=["POST"])
    @login_required
    def registrar_capital():
        data = request.get_json(force=True)
        try:
            aporte = Capital(
                negocio_id=g.negocio.id,
                monto=float(data["monto"]),
                descripcion=data.get("descripcion"),
            )
        except (KeyError, ValueError):
            return jsonify({"error": "Debes enviar 'monto' numérico"}), 400
        db.session.add(aporte)
        db.session.commit()
        return jsonify(aporte.to_dict()), 201

    # ----------------------------------------------------------------- gastos
    @app.route("/api/gastos", methods=["GET"])
    @login_required
    def listar_gastos():
        return jsonify([g_.to_dict() for g_ in mis(Gasto).order_by(Gasto.fecha.desc()).all()])

    @app.route("/api/gastos", methods=["POST"])
    @login_required
    def crear_gasto():
        data = request.get_json(force=True)
        try:
            gasto = Gasto(
                negocio_id=g.negocio.id,
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
        return jsonify([c.to_dict() for c in mis(Cliente).order_by(Cliente.nombre).all()])

    @app.route("/api/clientes", methods=["POST"])
    @login_required
    def crear_cliente():
        data = request.get_json(force=True)
        nombre = (data.get("nombre") or "").strip()
        if not nombre:
            return jsonify({"error": "El nombre es requerido"}), 400
        cliente = Cliente(negocio_id=g.negocio.id, nombre=nombre, contacto=data.get("contacto"))
        db.session.add(cliente)
        db.session.commit()
        return jsonify(cliente.to_dict()), 201

    # ------------------------------------------------------------------ metas
    @app.route("/api/metas", methods=["GET"])
    @login_required
    def listar_metas():
        return jsonify(logic.progreso_metas(g.negocio.id))

    @app.route("/api/metas", methods=["POST"])
    @login_required
    def crear_meta():
        data = request.get_json(force=True)
        try:
            inicio = datetime.fromisoformat(data["fecha_inicio"])
            fin_date = datetime.fromisoformat(data["fecha_fin"]).date()
            meta = Meta(
                negocio_id=g.negocio.id,
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
            cliente_id = int(data["cliente_id"]) if data.get("cliente_id") else None
        except (TypeError, ValueError):
            return jsonify({"error": "monto_pagado y cliente_id deben ser numéricos"}), 400

        try:
            ticket = logic.registrar_ticket(
                negocio_id=g.negocio.id,
                items_data=data.get("items") or [],
                metodo_pago=data.get("metodo_pago"),
                monto_pagado=monto_pagado,
                cliente_id=cliente_id,
            )
        except (logic.ErrorVenta, TypeError, ValueError) as e:
            db.session.rollback()
            mensaje = str(e) if isinstance(e, logic.ErrorVenta) else "Datos de venta inválidos"
            return jsonify({"error": mensaje}), 400

        return jsonify(ticket.to_dict()), 201

    @app.route("/api/tickets", methods=["GET"])
    @login_required
    def listar_tickets():
        tickets = mis(Ticket).order_by(Ticket.fecha.desc()).all()
        return jsonify([t.to_dict(incluir_items=False) for t in tickets])

    @app.route("/api/tickets/<int:ticket_id>", methods=["GET"])
    @login_required
    def ver_ticket(ticket_id):
        ticket = mio_o_404(Ticket, ticket_id)
        return jsonify(ticket.to_dict(incluir_items=True))

    @app.route("/api/tickets/<int:ticket_id>/marcar-pagado", methods=["POST"])
    @login_required
    def marcar_pagado(ticket_id):
        ticket = mio_o_404(Ticket, ticket_id)
        logic.marcar_ticket_pagado(ticket)
        return jsonify(ticket.to_dict())

    @app.route("/api/cuentas-por-cobrar", methods=["GET"])
    @login_required
    def cuentas_por_cobrar():
        return jsonify([t.to_dict(incluir_items=False) for t in logic.cuentas_por_cobrar(g.negocio.id)])

    # ------------------------------------------------------------- inventario
    @app.route("/api/inventario/alertas", methods=["GET"])
    @login_required
    def alertas_inventario():
        productos = mis(Producto).filter_by(activo=True).all()
        return jsonify([p.to_dict() for p in productos if p.stock_bajo])

    @app.route("/api/inventario/conteo", methods=["POST"])
    @login_required
    def registrar_conteo():
        data = request.get_json(force=True)
        producto_id = entero_o_none(data.get("producto_id"))
        if producto_id is None:
            return jsonify({"error": "producto_id inválido"}), 400
        producto = mio_o_404(Producto, producto_id)
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
        return jsonify(logic.resumen_financiero(g.negocio.id))

    @app.route("/api/ranking", methods=["GET"])
    @login_required
    def ranking():
        return jsonify(logic.ranking_productos(g.negocio.id))

    @app.route("/api/simular-precio", methods=["POST"])
    @login_required
    def simular_precio():
        data = request.get_json(force=True)
        producto_id = entero_o_none(data.get("producto_id"))
        if producto_id is None:
            return jsonify({"error": "producto_id inválido"}), 400
        producto = mio_o_404(Producto, producto_id)
        try:
            porcentaje = float(data["porcentaje"])
        except (KeyError, ValueError):
            return jsonify({"error": "Debes enviar 'porcentaje' numérico (ej. 10 o -15)"}), 400
        return jsonify(logic.simular_cambio_precio(producto, porcentaje))

    @app.route("/api/ventas-por-periodo", methods=["GET"])
    @login_required
    def ventas_por_periodo():
        agrupacion = request.args.get("agrupacion", "dia")
        return jsonify(logic.ventas_por_periodo(g.negocio.id, agrupacion))

    @app.route("/api/reportes/ventas.xlsx", methods=["GET"])
    @login_required
    def reporte_ventas_excel():
        tickets = mis(Ticket).order_by(Ticket.fecha).all()
        buf = rep.generar_excel_ventas(tickets)
        return send_file(
            buf, as_attachment=True, download_name="ventas.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.route("/api/reportes/resumen.pdf", methods=["GET"])
    @login_required
    def reporte_resumen_pdf():
        resumen_data = logic.resumen_financiero(g.negocio.id)
        tickets = mis(Ticket).order_by(Ticket.fecha.desc()).all()
        buf = rep.generar_pdf_resumen(resumen_data, tickets, negocio_nombre=g.negocio.nombre)
        return send_file(buf, as_attachment=True, download_name="reporte.pdf", mimetype="application/pdf")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
