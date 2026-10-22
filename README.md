# Manager Tapper

App de gestión financiera para negocios: capital invertido, punto de equilibrio,
inventario con catálogo e historial de precios, ranking de productos con
estrategias de venta sugeridas, y simulador de cambio de precio.

## Estructura del proyecto

```
manager_tapper/
├── app.py               # Flask: rutas de la API y la página principal
├── models.py            # Modelos de datos (SQLAlchemy): Producto, Venta, Capital, etc.
├── business_logic.py    # Cálculos: ganancias, punto de equilibrio, ranking, simulación
├── requirements.txt
├── templates/
│   └── index.html       # Dashboard
├── static/
│   ├── app.ts           # Frontend en TypeScript (fuente)
│   ├── app.js           # Frontend compilado (el que carga index.html)
│   └── style.css
├── tests/
│   └── test_multinegocio.py  # prueba de aislamiento entre negocios
├── desktop_app.py            # Envoltorio: abre app.py en una ventana de Windows
└── requirements-desktop.txt  # Dependencias extra para compilar el .exe
```

Es el mismo backend y el mismo frontend para las dos versiones —
`desktop_app.py` solo le pone una ventana nativa encima al Flask de siempre.

Esto corresponde directamente a la sección "Datos" de tu Análisis:
- **Entrada** → los formularios de `index.html` y las rutas `POST` de `app.py`.
- **Proceso** → `business_logic.py` (ahí vive toda la lógica de cálculo).
- **Salida** → las rutas `GET` de `app.py`, que el dashboard consume.

## Cómo correrlo

```bash
python3 -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abre http://127.0.0.1:5000 en el navegador. La base de datos SQLite
(`manager_tapper.db`) se crea sola la primera vez que corres la app.

## Si editas static/app.ts

El navegador carga `app.js`, no `app.ts` — hay que recompilar después de cada cambio:

```bash
npm install -g typescript   # una sola vez
tsc static/app.ts --target ES2017 --lib DOM,ES2017 --outDir static
```

## App de escritorio para Windows (.exe)

Esto se compila directamente en tu máquina Windows (no se puede generar un
.exe de Windows desde otro sistema operativo):

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements-desktop.txt

pyinstaller --noconfirm --onefile --windowed --name "ManagerTapper" ^
  --add-data "templates;templates" --add-data "static;static" desktop_app.py
```

El ejecutable queda en `dist\ManagerTapper.exe` — es un solo archivo, no
necesita tener Python instalado para correr en otra computadora. La base de
datos de esa versión se guarda en `%USERPROFILE%\ManagerTapper\manager_tapper.db`
(una copia local, separada de la de Render).

Nota: la primera vez que abras el .exe, Windows Defender puede mostrar una
advertencia por ser un ejecutable sin firmar — es normal en proyectos
personales/escolares, solo da clic en "Más información" → "Ejecutar de
todas formas".

## Punto de venta

La sección "Punto de venta" reemplaza el registro de ventas de un solo
producto: ahora se arma un carrito con varios productos, se elige método de
pago (efectivo o tarjeta), y si es efectivo se calcula el cambio
automáticamente. Al cobrar se genera un **ticket** (ver `Ticket` y
`DetalleVenta` en `models.py`) con un botón para imprimirlo
(`window.print()` con estilos especiales en `style.css` que ocultan todo lo
demás de la página al imprimir). Todos los tickets quedan guardados y se
pueden volver a consultar en "Historial de ventas".

## Productos: categorías, búsqueda, edición y baja

- Las categorías se crean en su propia sección y luego aparecen como
  desplegable al crear/editar un producto.
- El buscador y el filtro de categoría del catálogo filtran la tabla en el
  navegador (no hacen una petición nueva al servidor).
- "Editar" reutiliza el mismo formulario de "Agregar producto" (cambia a
  modo edición); el precio sigue actualizándose por su propio endpoint para
  no perder el historial.
- "Eliminar" no borra el producto de la base de datos — lo marca como
  inactivo (`activo = False`) para no romper el historial de ventas que ya
  lo mencionan. Por eso deja de aparecer en el catálogo, el punto de venta y
  el ranking, pero sigue intacto en los tickets antiguos.

## Cuenta y acceso

Cualquier persona puede crear la cuenta de su negocio en `/registro` (nombre
del negocio, usuario, correo, contraseña de mínimo 8 caracteres y aceptar los
términos). No hay credenciales por defecto. Después, cada vez que entre, le
pide login. La contraseña se guarda con hash (`werkzeug.security`), nunca en
texto plano. El enlace viejo `/setup` redirige a `/registro`.

En Render, define la variable de entorno `SECRET_KEY` (Settings ->
Environment) con cualquier texto largo y aleatorio — si no la defines, la
sesión se invalida cada vez que el servicio se reinicia y tendrás que volver
a iniciar sesión más seguido.

Nota: la web (Render) y el `.exe` de escritorio tienen bases de datos
separadas, así que vas a crear una cuenta en cada una la primera vez que las
abras.

## Multi-negocio (cuentas separadas por cliente)

Cada negocio (`Negocio` en `models.py`) tiene sus propios productos,
categorías, clientes, ventas, capital, gastos y metas. Casi todas las tablas
llevan `negocio_id`, y **toda** consulta de `app.py` pasa por `mis(Modelo)` /
`mio_o_404(Modelo, id)`, que filtran por el negocio de la sesión. Si alguien
pide por id algo de otro negocio recibe 404 (igual que si no existiera), y
los nombres de producto/categoría solo deben ser únicos dentro de cada
negocio.

- Una cuenta pertenece a un solo negocio. Ya existen las columnas `rol`
  (`dueno`/`empleado`) y `Negocio.activo` (para suspender cuentas), pero los
  permisos por rol y el panel de administrador todavía no están construidos.
- Si un negocio se suspende (`activo = False`), su sesión deja de funcionar en
  la siguiente petición y no puede volver a entrar.
- Hay un límite de 5 registros por hora desde la misma conexión (variable
  `MANAGER_TAPPER_REGISTROS_MAX` para cambiarlo). En Render se usa `ProxyFix`
  para ver la IP real del visitante y no la del proxy.

**Prueba de aislamiento:** `python tests/test_multinegocio.py` crea una base
temporal con varios negocios y comprueba que uno no puede ver, editar, borrar
ni usar datos de otro (listados, ids ajenos, ventas con productos o clientes
ajenos, reportes, sesiones manipuladas, suspensión). Córrela después de
cualquier cambio en `app.py` o `business_logic.py`.

## Seguridad

Protecciones ya incluidas, pensadas para un proyecto escolar expuesto en
internet (no para un sistema con dinero real):

- **Términos y condiciones** — hay que aceptarlos para crear una cuenta
  (`/terminos`); queda guardada la fecha de aceptación en `Usuario.terminos_aceptados_en`.
- **Bloqueo por intentos fallidos** — 5 intentos de login incorrectos desde
  la misma combinación IP+usuario bloquean el login por 5 minutos
  (`app.py`, `INTENTOS_MAXIMOS` / `BLOQUEO_SEGUNDOS`). Es en memoria, así que
  se reinicia si el servicio se reinicia — suficiente para este alcance.
- **Protección CSRF** en los formularios de login/registro — un token por
  sesión que se valida con comparación segura (`secrets.compare_digest`).
- **Cookies de sesión** con `HttpOnly` (JavaScript no puede leerla),
  `SameSite=Lax`, y `Secure` automático cuando corre en Render (exige HTTPS).
- **Encabezados HTTP de seguridad** en cada respuesta: `X-Content-Type-Options`,
  `X-Frame-Options`, `Content-Security-Policy`, `Referrer-Policy`.
- **Términos y condiciones** (`/terminos`): el titular y el contacto que se
  muestran salen de las variables de entorno `MANAGER_TAPPER_TITULAR` y
  `MANAGER_TAPPER_CONTACTO` (defínelas en Render; si no, aparece un marcador
  entre corchetes). Es un texto base, no asesoría legal: si vas a cobrar,
  necesitas además un Aviso de Privacidad (LFPDPPP) y que un abogado revise
  los términos.
- **Contraseñas con hash** (`werkzeug.security`, algoritmo scrypt), nunca en
  texto plano.
- **Consultas con SQLAlchemy** (ORM) en todo el proyecto — nada de SQL armado
  a mano, así que no hay inyección SQL por concatenar texto.

Ningún sistema es 100% invulnerable, y esto no sustituye buenas prácticas
básicas de tu parte: usa una contraseña real (no "admin123"), define
`SECRET_KEY` en Render, y no captures datos sensibles reales de un negocio
de verdad en un proyecto escolar.

## Funciones nuevas en esta versión

- **Login y registro de negocios** (`/registro`), con datos separados por negocio.
- **Modo oscuro** — botón en la esquina superior derecha, se recuerda entre
  sesiones.
- **Gastos operativos** — además de la ganancia bruta por producto, el
  resumen ahora muestra ganancia neta (ganancia - gastos).
- **Metas de venta** — defines un monto objetivo y un rango de fechas; la
  app calcula cuánto llevas vendido y el % de avance.
- **Clientes y ventas a crédito** — el punto de venta ahora acepta
  "crédito" como método de pago (requiere elegir un cliente); la sección
  "Cuentas por cobrar" lista lo pendiente y tiene un botón para marcarlo
  pagado.
- **Ventas en el tiempo** — gráfica de línea con el total vendido por
  día/semana/mes.
- **Reportes descargables** — botones para exportar el historial de ventas
  en Excel y un resumen en PDF.

## Endpoints principales de la API

| Método | Ruta | Qué hace |
|---|---|---|
| GET/POST | `/api/categorias` | Listar / crear categorías |
| GET/POST | `/api/productos` | Listar (solo activos) / crear productos |
| PUT/DELETE | `/api/productos/<id>` | Editar (nombre/costo/stock/categoría) / dar de baja |
| PUT | `/api/productos/<id>/precio` | Cambiar el precio (guarda el historial) |
| GET | `/api/productos/<id>/historial` | Historial de precios de un producto |
| GET/POST | `/api/capital` | Listar / registrar capital invertido |
| POST | `/api/ventas` | Cobrar un carrito completo (crea un Ticket) |
| GET | `/api/tickets` | Historial de tickets (sin detalle) |
| GET | `/api/tickets/<id>` | Un ticket con todas sus líneas |
| GET | `/api/inventario/alertas` | Productos con stock bajo |
| POST | `/api/inventario/conteo` | Registrar un conteo físico y detectar desfases |
| GET | `/api/resumen` | Ganancia total, capital invertido y punto de equilibrio |
| GET | `/api/ranking` | Ranking de productos + estrategia sugerida |
| POST | `/api/simular-precio` | Simula subir/bajar el precio de un producto |

## Si tenías una base de datos de antes

Esta versión agrega negocios (`negocio_id` en casi todas las tablas, `email` y
`rol` en usuarios), así que una base de una versión anterior no es
compatible. Bórrala antes de correr esta versión: la carpeta `instance/`
(ahí guarda Flask el `.db` en pruebas locales) y, para el `.exe` de
escritorio, `%USERPROFILE%\ManagerTapper`. En Render el disco gratuito se
reinicia solo en cada despliegue. Se vuelve a crear vacía y tendrás que
registrar de nuevo tu negocio en `/registro`.

## Próximos pasos sugeridos

Para vender el servicio, en este orden:

1. ~~Multi-negocio con registro~~ (hecho).
2. Base de datos persistente (Postgres de pago): SQLite en el plan gratuito de
   Render se pierde en cada despliegue.
3. Recuperar contraseña por correo (ya se guarda el correo de cada usuario).
4. Roles dueño/empleado (ya existe la columna `rol`).
5. Cobro de suscripción (Stripe o Mercado Pago).
6. Aviso de privacidad (obligatorio en México si manejas datos de clientes).
7. Respaldos automáticos y panel de administrador.
8. Facturación electrónica (CFDI).

Además: ajustar el umbral de "stock bajo" en `models.py` (`UMBRAL_STOCK_BAJO`).
