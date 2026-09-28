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
└── static/
    ├── app.ts           # Frontend en TypeScript (fuente)
    ├── app.js           # Frontend compilado (el que carga index.html)
    └── style.css
```

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

## Endpoints principales de la API

| Método | Ruta | Qué hace |
|---|---|---|
| GET/POST | `/api/productos` | Listar / crear productos del catálogo |
| PUT | `/api/productos/<id>/precio` | Cambiar el precio (guarda el historial) |
| GET | `/api/productos/<id>/historial` | Historial de precios de un producto |
| GET/POST | `/api/capital` | Listar / registrar capital invertido |
| GET/POST | `/api/ventas` | Listar / registrar una venta (baja el stock) |
| GET | `/api/inventario/alertas` | Productos con stock bajo |
| POST | `/api/inventario/conteo` | Registrar un conteo físico y detectar desfases |
| GET | `/api/resumen` | Ganancia total, capital invertido y punto de equilibrio |
| GET | `/api/ranking` | Ranking de productos + estrategia sugerida |
| POST | `/api/simular-precio` | Simula subir/bajar el precio de un producto |

## Próximos pasos sugeridos

1. **Subir esto a tu repositorio de GitHub** (ya lo tienes creado).
2. Agregar autenticación si vas a tener más de un usuario/negocio.
3. Desplegar en Render (backend) como ya hiciste con Job_Radar Pro.
4. Ajustar el umbral de "stock bajo" en `models.py` (`UMBRAL_STOCK_BAJO`) según el negocio.
5. Si quieres persistir en producción, considera Postgres en vez de SQLite (Render lo ofrece gratis).
