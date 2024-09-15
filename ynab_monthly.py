import os
import requests
from dotenv import load_dotenv
from datetime import datetime

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Obtener el token de acceso y los ID de los presupuestos desde las variables de entorno
YNAB_ACCESS_TOKEN = os.getenv("YNAB_ACCESS_TOKEN")
MAIN_BUDGET_ID = os.getenv("MAIN_BUDGET_ID")

# Definir la URL base de la API de YNAB
BASE_URL = "https://api.youneedabudget.com/v1"

# Encabezados para la solicitud, incluyendo el token de autorización
headers = {
    "Authorization": f"Bearer {YNAB_ACCESS_TOKEN}"
}

def format_currency(value):
    return f"${value / 1000:,.2f}"

def get_monthly_spending(budget_id, month):
    url = f"{BASE_URL}/budgets/{budget_id}/months/{month}-01"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        jsonResponse = response.json()
        montlyResponse = jsonResponse["data"]["month"]
        return montlyResponse
    else:
        print(f"Error al obtener datos del mes {month}: {response.status_code}")
        print(response.json())
        return None

def get_total_spending_for_month(budget_id, month):
    month_data = get_monthly_spending(budget_id, month)
    
    if month_data:
        total_spending = sum(category['activity'] for category in month_data['categories'] if category['activity'] < 0)
        return total_spending
    return 0

def get_average_spending_per_month(budget_id, start_date, end_date):
    url = f"{BASE_URL}/budgets/{budget_id}/months"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        months_data = response.json()["data"]["months"]

        filtered_months = [month for month in months_data if start_date <= month['month'] <= end_date]

        if filtered_months:
            first_month = filtered_months[0]['month']
            last_month = filtered_months[-1]['month']
            print(f"Primer mes filtrado: {first_month}")
            print(f"Último mes filtrado: {last_month}")
        
        total_spending = sum(month['activity'] for month in filtered_months)
        num_months = len(filtered_months)
        average_spending = total_spending / num_months if num_months > 0 else 0
        return average_spending
    else:
        print(f"Error al obtener datos de meses: {response.status_code}")
        print(response.json())
        return 0

def main():
    current_date = datetime.now()
    
    current_month = current_date.strftime("%Y-%m")

    start_of_year = current_date.replace(month=1, day=1).strftime("%Y-%m-%d")
    end_of_year = current_date.strftime("%Y-%m-%d")

    print("\nGastos del presupuesto principal:")
    
    total_spending = get_total_spending_for_month(MAIN_BUDGET_ID, current_month)
    average_spending = get_average_spending_per_month(MAIN_BUDGET_ID, start_of_year, end_of_year)
    
    print(f"Total gastado en el mes en curso ({current_month}): {format_currency(total_spending)}")
    print(f"Gasto promedio mensual: {format_currency(average_spending)}")

if __name__ == "__main__":
    main()
