#!/usr/bin/env python3
"""
Configuracion inicial de Bitacora Trading.
Ejecuta una sola vez para crear tu archivo .env con tus datos.
"""

import os
import sys

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
    print("--- PROPREPORTS (Broker) ---")
    print("(Deja en blanco si no usas PropReports)")

    user = input("Usuario: ").strip()
    password = input("Password: ").strip()
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

    print()
    print("=" * 60)
    print(f"  .env creado en {ENV_PATH}")
    print("  Ejecuta: python3 actualizar_reporte.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
