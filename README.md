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

La primera vez que abras la app (web o `.exe`) te manda a `/setup` para crear
un usuario y contraseña — no hay credenciales por defecto. A partir de ahí,
cada vez que entres te pide login. La contraseña se guarda con hash
(`werkzeug.security`), nunca en texto plano.

En Render, define la variable de entorno `SECRET_KEY` (Settings ->
Environment) con cualquier texto largo y aleatorio — si no la defines, la
sesión se invalida cada vez que el servicio se reinicia y tendrás que volver
a iniciar sesión más seguido.

Nota: la web (Render) y el `.exe` de escritorio tienen bases de datos
separadas, así que vas a crear una cuenta en cada una la primera vez que las
abras.

## Seguridad

Protecciones ya incluidas, pensadas para un proyecto escolar expuesto en
internet (no para un sistema con dinero real):

- **Términos y condiciones** — hay que aceptarlos para crear una cuenta
  (`/terminos`); queda guardada la fecha de aceptación en `Usuario.terminos_aceptados_en`.
- **Bloqueo por intentos fallidos** — 5 intentos de login incorrectos desde
  la misma combinación IP+usuario bloquean el login por 5 minutos
  (`app.py`, `INTENTOS_MAXIMOS` / `BLOQUEO_SEGUNDOS`). Es en memoria, así que
  se reinicia si el servicio se reinicia — suficiente para este alcance.
- **Protección CSRF** en los formularios de login/setup — un token por
  sesión que se valida con comparación segura (`secrets.compare_digest`).
- **Cookies de sesión** con `HttpOnly` (JavaScript no puede leerla),
  `SameSite=Lax`, y `Secure` automático cuando corre en Render (exige HTTPS).
- **Encabezados HTTP de seguridad** en cada respuesta: `X-Content-Type-Options`,
  `X-Frame-Options`, `Content-Security-Policy`, `Referrer-Policy`.
- **Contraseñas con hash** (`werkzeug.security`, algoritmo scrypt), nunca en
  texto plano.
- **Consultas con SQLAlchemy** (ORM) en todo el proyecto — nada de SQL armado
  a mano, así que no hay inyección SQL por concatenar texto.

Ningún sistema es 100% invulnerable, y esto no sustituye buenas prácticas
básicas de tu parte: usa una contraseña real (no "admin123"), define
`SECRET_KEY` en Render, y no captures datos sensibles reales de un negocio
de verdad en un proyecto escolar.

## Funciones nuevas en esta versión

- **Login** con usuario/contraseña (`/setup` la primera vez).
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

El modelo de ventas cambió (antes era una venta por producto; ahora un
ticket con varias líneas), así que una `manager_tapper.db` de una versión
anterior no es compatible. Bórrala antes de correr esta versión — tanto la
de pruebas locales/Render (`manager_tapper.db` en la carpeta del proyecto)
como la del `.exe` de escritorio (`%USERPROFILE%\ManagerTapper\manager_tapper.db`).
Se vuelve a crear vacía la primera vez que abras la app.

## Próximos pasos sugeridos

1. Ajustar el umbral de "stock bajo" en `models.py` (`UMBRAL_STOCK_BAJO`) según el negocio.
2. Si quieres persistir en producción, considera Postgres en vez de SQLite (Render lo ofrece gratis).
3. Si en algún momento manejas más de un usuario por negocio (no solo un admin compartido), considera cuentas con roles en vez del usuario único actual.
