from src.ynab.reader import get_consolidated_ynab_entries


def print_consolidated_balances():
    entries = get_consolidated_ynab_entries()
    if entries:
        print(
            "\nBalances consolidados de las cuentas de tarjetas de crédito (no cerradas):"
        )
        for entry in entries:
            formatted_balance = f"${entry['balance']:,.2f}"
            name = entry["name"] + " **" if entry["consolidated"] else entry["name"]
            print(f"- {name}: {formatted_balance}")
    else:
        print("No se pudieron obtener las cuentas de ambos presupuestos.")


def main():
    print_consolidated_balances()


if __name__ == "__main__":
    main()
