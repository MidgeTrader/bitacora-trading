#!/usr/bin/env python3
"""
Configuracion inicial de Bitacora Trading.
Ejecuta una sola vez para crear tu archivo .env con tus datos.
"""

import os
import sys
import stat
from getpass import getpass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, ".env")


def ask(prompt, default=""):
    """Pregunta con valor por defecto opcional."""
    if default:
        val = input(f"{prompt} [{default}]: ").strip()
        return val if val else default
    while True:
        val = input(f"{prompt}: ").strip()
        if val:
            return val
        print("  Este campo es obligatorio.")


def main():
    print("=" * 60)
    print("  BITACORA TRADING — Setup Inicial")
    print("=" * 60)
    print()
    print("Esto creara tu archivo .env con tus datos personales.")
    print("(El .env nunca se sube a GitHub — esta en .gitignore)")
    print()

    # Datos del trader
    print("--- PERFIL ---")
    name = ask("Nombre / Marca (aparece en el reporte)", "MIDGE TRADE")

    logo = input("Ruta a tu logo PNG (deja vacio si no tienes): ").strip()
    if logo and not os.path.exists(logo):
        alt = os.path.join(SCRIPT_DIR, logo)
        if os.path.exists(alt):
            logo = alt
        else:
            print(f"  WARNING: '{logo}' no existe. El logo no se mostrara hasta que corrijas la ruta.")

    print()
    print("--- PLATAFORMAS DE TRADING ---")
    print("Selecciona las plataformas que usas (creara las carpetas para tus CSVs):")
    print()
    print("  1. MetaTrader 4/5 (Account History CSV)")
    print("  2. DAS Trader (Execution log CSV)")
    print("  3. ThinkOrSwim (Trade confirmation CSV)")
    print("  4. Schwab (Trade confirmation CSV)")
    print("  5. Generica (CSV con mapping.json personalizado)")
    print("  6. PropReports / Alaric (descarga automatica)")
    print()
    print("Escribe los numeros separados por comas, ej: 1,3,4")

    sel = input("Plataformas (deja vacio para todas): ").strip()
    if not sel:
        selected = ['1', '2', '3', '4', '5', '6']
    else:
        selected = [s.strip() for s in sel.split(',')]

    platform_dirs = []
    if '1' in selected: platform_dirs.append('Reports_MetaTrader')
    if '2' in selected: platform_dirs.append('Reports_DAS')
    if '3' in selected: platform_dirs.append('Reports_TOS')
    if '4' in selected: platform_dirs.append('Reports_Schwab')
    if '5' in selected: platform_dirs.append('Reports_Generic')
    if '6' in selected: platform_dirs.append('Reports_PropReports')

    # Always create Gastos folder
    platform_dirs.append('Reports_Gastos')

    for d in platform_dirs:
        dir_path = os.path.join(SCRIPT_DIR, d)
        os.makedirs(dir_path, exist_ok=True)
        # Create example CSV in Generic folder
        if d == 'Reports_Generic':
            example_csv = os.path.join(dir_path, 'example_trades.csv')
            if not os.path.exists(example_csv):
                with open(example_csv, 'w') as f:
                    f.write("Date,Symbol,Side,Qty,Price,Commission,Direction\n")
                    f.write("01/15/2026,AAPL,BUY,100,150.00,1.50,Long\n")
                    f.write("01/20/2026,AAPL,SELL,100,155.00,1.50,Long\n")
            mapping = os.path.join(dir_path, 'mapping.json')
            if not os.path.exists(mapping):
                import json
                with open(mapping, 'w') as f:
                    json.dump({
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
                    }, f, indent=2)

    print(f"  Carpetas creadas: {', '.join(platform_dirs)}")

    print()
    print("--- PROPREPORTS (Broker) ---")
    print("(Deja en blanco si no usas PropReports)")

    user = input("Usuario: ").strip()
    password = ""
    if user:
        password = getpass("Password (no se mostrara en pantalla): ").strip()
    group = input("Group ID [-4]: ").strip() or "-4"
    account = input("Account ID: ").strip()

    # Escribir .env
    lines = []
    lines.append("# Bitacora Trading — configuracion personal")
    lines.append("# Generado por setup.py — no compartir")
    lines.append("")
    lines.append(f"TRADER_NAME={name}")
    if logo:
        lines.append(f"LOGO_PATH={logo}")
    else:
        lines.append("# LOGO_PATH=logo.png")
    lines.append("")
    if user:
        lines.append(f"PROPREPORTS_USER={user}")
        lines.append(f"PROPREPORTS_PASSWORD={password}")
        lines.append(f"PROPREPORTS_GROUP_ID={group}")
        lines.append(f"PROPREPORTS_ACCOUNT_ID={account}")
    else:
        lines.append("# PROPREPORTS_USER=")
        lines.append("# PROPREPORTS_PASSWORD=")
        lines.append("# PROPREPORTS_GROUP_ID=")
        lines.append("# PROPREPORTS_ACCOUNT_ID=")

    with open(ENV_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(ENV_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0600 — solo el propietario lee/escribe

    print()
    print("=" * 60)
    print(f"  .env creado en {ENV_PATH}")
    print("  Ejecuta: python3 actualizar_reporte.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
