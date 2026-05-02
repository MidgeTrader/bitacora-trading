# Bitacora Trading

Genera un reporte HTML interactivo de performance a partir de tus archivos CSV de trading. Soporta multiples plataformas y brokers.

## Instalacion

```bash
git clone https://github.com/MidgeTrader/bitacora-trading.git
cd bitacora-trading
python3 setup.py
```

`setup.py` te guia paso a paso: nombre/marca, logo, plataformas que usas y credenciales de broker. Todo se guarda en `.env` (nunca se sube a GitHub).

## Uso

```bash
python3 actualizar_reporte.py
```

Esto descarga los datos mas recientes y genera `trading_report.html`. Abrelo en tu navegador.

### Opciones

| Comando | Descripcion |
|---|---|
| `python3 actualizar_reporte.py` | Descarga mes actual + genera + abre navegador |
| `python3 actualizar_reporte.py --no-browser` | Sin abrir navegador |
| `python3 actualizar_reporte.py --all` | Descarga todo el historico |
| `python3 actualizar_reporte.py 2026-04` | Solo un mes especifico |
| `python3 actualizar_reporte.py --no-serve` | Abre sin servidor (tags se guardan por descarga) |
| `python3 generate_report.py` | Solo genera el HTML (sin descargar) |

## Plataformas soportadas

Suelta tus archivos CSV en la carpeta correspondiente:

| Carpeta | Plataforma | Tipo |
|---|---|---|
| `Reports_Schwab/` | Charles Schwab | Ejecuciones individuales |
| `Reports_PropReports/` | PropReports / Alaric | Trades cerrados |
| `Reports_MetaTrader/` | MetaTrader 4/5 | Account History CSV |
| `Reports_DAS/` | DAS Trader | Execution log CSV |
| `Reports_TOS/` | ThinkOrSwim | Trade confirmation CSV |
| `Reports_Generic/` | Cualquier plataforma | Crea un `mapping.json` y mapea tus columnas |
| `Reports_Gastos/` | Gastos fijos | CSV con `Date`, `Category`, `Comment`, `Debit` |

### Ejemplo mapping.json para Reports_Generic/

```json
{
  "type": "executions",
  "date_col": "Date",
  "date_format": "%m/%d/%Y",
  "symbol_col": "Symbol",
  "action_col": "Side",
  "quantity_col": "Qty",
  "price_col": "Price",
  "fees_col": "Commission",
  "buy_values": ["BUY"],
  "sell_values": ["SELL"]
}
```

Para trades pre-emparejados usa `"type": "matched"` y define `direction_col`, `net_pl_col`, etc.

## Editor de TAGs

- Haz clic en cualquier simbolo en **Daily Details** para abrir el modal
- Asigna tags de entrada, salida y notas
- Los tags persisten entre regeneraciones del reporte (se guardan en `tags.json`)
- El boton **Save Tags** guarda tus asignaciones

## Switch EN / ES

El reporte detecta el idioma de tu navegador. Para cambiar:

1. Haz clic en **CUSTOMIZE** (esquina superior derecha)
2. En la seccion **Language**, elige **ES** o **EN**
3. Se guarda tu preferencia

## Estructura del proyecto

```
bitacora-trading/
├── setup.py                  # Configuracion inicial interactiva
├── actualizar_reporte.py     # Unifica descarga + generacion + servidor
├── generate_report.py        # Genera el HTML con todas las metricas
├── download_alaric.py        # Descarga datos desde PropReports
├── .env.example              # Plantilla de variables de entorno
├── .gitignore
├── Reports_Schwab/           # Tus CSVs de Schwab (gitignored)
├── Reports_PropReports/      # Tus CSVs de PropReports (gitignored)
├── Reports_MetaTrader/       # Tus CSVs de MT4/MT5 (gitignored)
├── Reports_DAS/              # Tus CSVs de DAS (gitignored)
├── Reports_TOS/              # Tus CSVs de ThinkOrSwim (gitignored)
├── Reports_Generic/          # Tus CSVs + mapping.json (gitignored)
├── Reports_Gastos/           # Tus gastos fijos (gitignored)
├── trading_report.html       # Reporte generado (gitignored)
└── tags.json                 # Tags guardados (gitignored)
```

## Seguridad

- `.env` con credenciales nunca se sube a GitHub (.gitignore)
- Los CSV de trading nunca se suben
- El logo personal nunca se sube
- `setup.py` usa `.env.example` como plantilla con placeholders genericos
