import os
import requests
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Obtener el token de acceso desde las variables de entorno
YNAB_ACCESS_TOKEN = os.getenv("YNAB_ACCESS_TOKEN")

# Definir la URL base de la API de YNAB
BASE_URL = "https://api.youneedabudget.com/v1"

# Encabezados para la solicitud, incluyendo el token de autorización
headers = {
    "Authorization": f"Bearer {YNAB_ACCESS_TOKEN}"
}

def get_budgets():
    url = f"{BASE_URL}/budgets"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["data"]["budgets"]
    else:
        print(f"Error al obtener presupuestos: {response.status_code}")
        return None

def get_accounts(budget_id):
    url = f"{BASE_URL}/budgets/{budget_id}/accounts"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["data"]["accounts"]
    else:
        print(f"Error al obtener cuentas: {response.status_code}")
        return None

def main():
    budgets = get_budgets()
    if budgets:
        print("Presupuestos disponibles:")
        for budget in budgets:
            print(f"- {budget['name']} (ID: {budget['id']})")

        # Tomar el primer presupuesto para la demostración
        budget_id = budgets[0]["id"]

        accounts = get_accounts(budget_id)
        if accounts:
            print("\nCuentas disponibles:")
            for account in accounts:
                print(f"- {account['name']}: {account['balance']} (ID: {account['id']})")
        else:
            print("No se pudieron obtener las cuentas.")
    else:
        print("No se pudieron obtener los presupuestos.")

if __name__ == "__main__":
    main()
