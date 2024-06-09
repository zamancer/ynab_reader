import os
import requests
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Obtener el token de acceso y el ID del presupuesto principal desde las variables de entorno
YNAB_ACCESS_TOKEN = os.getenv("YNAB_ACCESS_TOKEN")
MAIN_BUDGET_ID = os.getenv("MAIN_BUDGET_ID")

# Definir la URL base de la API de YNAB
BASE_URL = "https://api.youneedabudget.com/v1"

# Encabezados para la solicitud, incluyendo el token de autorización
headers = {
    "Authorization": f"Bearer {YNAB_ACCESS_TOKEN}"
}

def get_accounts(budget_id):
    url = f"{BASE_URL}/budgets/{budget_id}/accounts"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["data"]["accounts"]
    else:
        print(f"Error al obtener cuentas: {response.status_code}")
        return None

def format_currency(value):
    # Los balances en YNAB están en "mil" unidades (ej. 2766760 representa $2,766.76)
    return f"${value / 1000:,.2f}"

def print_credit_card_balances(budget_id):
    accounts = get_accounts(budget_id)
    if accounts:
        print("\nBalances de las cuentas de tarjetas de crédito (no cerradas):")
        for account in accounts:
            if account['type'] == 'creditCard' and not account['closed']:
                formatted_balance = format_currency(account['balance'])
                print(f"- {account['name']}: {formatted_balance}")
    else:
        print("No se pudieron obtener las cuentas.")

def main():
    print_credit_card_balances(MAIN_BUDGET_ID)

if __name__ == "__main__":
    main()
