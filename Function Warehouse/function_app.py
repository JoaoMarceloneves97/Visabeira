import azure.functions as func
import json
import logging
import requests
import uuid
from datetime import datetime

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Define a list of 10 materials with their ids and available quantity
inventory = [
    {"material_id": "cimento", "quantity": 10},
    {"material_id": "tijolo", "quantity": 15},
    {"material_id": "areia", "quantity": 8},
    {"material_id": "ferro", "quantity": 20},
    {"material_id": "cimento_colante", "quantity": 5},
    {"material_id": "ceramica", "quantity": 7},
    {"material_id": "cal", "quantity": 6},
    {"material_id": "telha", "quantity": 14},
]

EVENT_GRID_ENDPOINT = "https://requestmaterial.northeurope-1.eventgrid.azure.net/api/events"  # Replace with your Event Grid endpoint
EVENT_GRID_KEY = "/JWICDpSsXlFLAnd8kZTIbU4ZobzsM66gAZEGAMSnm4="  # Replace with your Event Grid key

@app.function_name(name="warehouse_database")
@app.event_grid_trigger(arg_name="event")
def main(event: func.EventGridEvent):
    logging.info("Event received")
        
    # Parse event data
    event_data = event.get_json()
    
    if event_data:
        process_event(event_data)

def process_event(event_data):
    try:
        # Access the fields directly from event_data
        order_id = event_data.get('order_id')
        field_service_id = event_data.get('fieldServiceId')
        materials = event_data.get('Material', [])
        delivery_address = event_data.get('delivery_address')
        status = event_data.get('Status')
        driver_location = event_data.get('driverLocation',{})

        logging.info(f"Order ID: {order_id}")
        logging.info(f"Field Service ID: {field_service_id}")
        logging.info(f"Materials: {materials}")
        logging.info(f"Delivery Address: {delivery_address}")
        logging.info(f"Status: {status}")
        logging.info(f"Driver Location: {driver_location}")

        # Check inventory
        if check_inventory(materials):
            logging.info("All materials are available")
            logging.info(event_data)
            event = {
            "id": str(uuid.uuid4()),
            "eventType": "orderConfirmed",
            "subject": "NewOrder",
            "eventTime": datetime.utcnow().isoformat(),
            "data": {
                "order_id": order_id,
                "fieldServiceId": field_service_id,
                "Material": materials,
                "delivery_address": delivery_address,
                "Status":'ready_for_pickup',
                "driverLocation": driver_location
            },
            "dataVersion": "1.0"
            }
            logging.info(event)
            headers = {'aeg-sas-key': EVENT_GRID_KEY}
            response = requests.post(EVENT_GRID_ENDPOINT, json=[event], headers=headers)
            logging.info(response)
            print(response)
            
        else:
            logging.info("Materials are not available")
            event = {
            "id": str(uuid.uuid4()),
            "eventType": "orderConfirmed",
            "subject": "NewOrder",
            "eventTime": datetime.utcnow().isoformat(),
            "data": {
                "order_id": order_id,
                "fieldServiceId": field_service_id,
                "Material": materials,
                "delivery_address": delivery_address,
                "Status": 'pending_inventory',
                "driverLocation": driver_location
            },
            "dataVersion": "1.0"
            }
            logging.info(event)
            headers = {'aeg-sas-key': EVENT_GRID_KEY}
            response = requests.post(EVENT_GRID_ENDPOINT, json=[event], headers=headers)
            logging.info(response)
            print(response)

        # Send an event to the Event Grid
        

    except Exception as e:
        logging.error(f"Error processing event: {str(e)}")

def check_inventory(materials):
    for material in materials:
        found = next((item for item in inventory if item["material_id"] == material["material_id"]), None)
        if not found or found["quantity"] < material["quantity"]:
            return False
    return True


