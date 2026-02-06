# Herramienta de Reportes de Trading (Versión Compartible)

Esta carpeta contiene el código necesario para generar un reporte de performance interactivo en HTML a partir de tus archivos de trading (Schwab y Alaric).

## Requisitos
- **Python 3.x** instalado.
- Los archivos CSV de tus brokers.

## Cómo usar
1. **Prepara tus archivos CSV**:
   - Pon tus archivos de Schwab, Alaric y Gastos en esta misma carpeta.
2. **Configura el script**:
   - Abre `generate_report.py` con un editor de texto (como Notepad o VS Code).
   - Busca la sección `CONFIGURACIÓN DE ARCHIVOS` al principio del archivo.
   - Cambia los nombres de los archivos en las listas `SCHWAB_FILES`, `ALARIC_FILES` y `GASTOS_FILES` para que coincidan exactamente con tus archivos.
3. **Ejecuta el script**:
   - Abre una terminal o consola en esta carpeta.
   - Ejecuta el comando: `python generate_report.py`
4. **Ver el reporte**:
   - Se generará un archivo llamado `trading_report_compartible.html`.
   - Ábrelo con cualquier navegador (Chrome, Edge, etc.) para ver tus estadísticas.

## Formatos Esperados
- **Schwab**: Archivos de ejecuciones con columnas `Date`, `Symbol`, `Quantity`, `Price`, `Action`.
- **Alaric**: Archivos de trades cerrados con columnas `Opened`, `Closed`, `Symbol`, `Qty`, `Entry`, `Exit`.
- **Gastos**: Un archivo CSV simple con columnas `Date` (MM/DD/YYYY) y `Debit` (monto del gasto).

---
*Desarrollado para Midge_Trader*
