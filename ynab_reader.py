import os
import requests
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Obtener el token de acceso y los ID de los presupuestos desde las variables de entorno
YNAB_ACCESS_TOKEN = os.getenv("YNAB_ACCESS_TOKEN")
MAIN_BUDGET_ID = os.getenv("MAIN_BUDGET_ID")
SECONDARY_BUDGET_ID = os.getenv("SECONDARY_BUDGET_ID")

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
        print(f"Error al obtener cuentas del presupuesto {budget_id}: {response.status_code}")
        return None

def format_currency(value):
    # Los balances en YNAB están en "mil" unidades (ej. 2766760 representa $2,766.76)
    return f"${value / 1000:,.2f}"

def consolidate_balances(main_accounts, secondary_accounts):
    consolidated = {}
    
    for account in main_accounts:
        consolidate_credit_card_balances(consolidated, account)

    for account in secondary_accounts:
        consolidate_credit_card_balances(consolidated, account)
                
    return consolidated

def consolidate_credit_card_balances(consolidated, account):
    if account['type'] == 'creditCard' and not account['closed']:
        if account['name'] in consolidated:
            consolidated[account['name']]['balance'] += account['balance']
            consolidated[account['name']]['name'] += " **"
        else:
            consolidated[account['name']] = {'balance': account['balance'], 'name': account['name']}

def print_consolidated_balances():
    main_accounts = get_accounts(MAIN_BUDGET_ID)
    secondary_accounts = get_accounts(SECONDARY_BUDGET_ID)
    
    if main_accounts and secondary_accounts:
        consolidated_balances = consolidate_balances(main_accounts, secondary_accounts)
        
        print("\nBalances consolidados de las cuentas de tarjetas de crédito (no cerradas):")
        for account in consolidated_balances.values():
            formatted_balance = format_currency(account['balance'])
            print(f"- {account['name']}: {formatted_balance}")
    else:
        print("No se pudieron obtener las cuentas de ambos presupuestos.")

def main():
    print_consolidated_balances()

if __name__ == "__main__":
    main()
