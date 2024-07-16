import azure.functions as func
import requests
import json
import uuid
from datetime import datetime
from . import app  # Import the app instance from __init__.py

@app.function_name(name="http_trigger")
@app.route(route="http_trigger")
def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # Parse request body
        request_body = req.get_json()
        print(request_body)
        
        # Determine the input format
        if isinstance(request_body, dict) and 'data' in request_body:
            # Handle the event grid format
            order_data = request_body['data']
        else:
            # Handle the direct order format
            order_data = request_body
        
        # Validate request format
        required_fields = ["order_id", "fieldServiceId", "Material", "delivery_address", "Status"]
        for field in required_fields:
            if field not in order_data:
                return func.HttpResponse(
                    f"Missing required field: {field}", 
                    status_code=400
                )
        
        materials = order_data["Material"]
        if not isinstance(materials, list) or not all(isinstance(item, dict) for item in materials):
            return func.HttpResponse(
                "Invalid format for 'Material'. It should be a list of dictionaries.",
                status_code=400
            )
        
        print(materials)
        
        # Warehouse location (fixed)
        warehouse_lat = 34.052235
        warehouse_lon = -118.243683
        
        # Check status and handle accordingly
        if order_data["Status"] == "ready_to_pickup":
            delivery_address = order_data["delivery_address"]
            print(delivery_address)
            azure_maps_key = "CPiS0LsmIo4hpVm9X360A4vwRPreIhUxEsZ7wgrqErIxfKuY8G5xJQQJ99AFACi5YpzxJCnnAAAgAZMPcG7h"
            try:
                delivery_lat, delivery_lon = get_location(delivery_address, azure_maps_key)
            except ValueError as e:
                return func.HttpResponse(str(e), status_code=404)
            except Exception as e:
                return func.HttpResponse(str(e), status_code=500)
            
            # Calculate travel time using Azure Maps Route API
            try:
                print(delivery_lat)
                print(delivery_lon)
                
                travel_time = calculate_travel_time(
                    warehouse_lat=warehouse_lat,
                    warehouse_lon=warehouse_lon,
                    delivery_lat=delivery_lat,
                    delivery_lon=delivery_lon,
                    azure_maps_key=azure_maps_key
                )
                print(travel_time)
                return func.HttpResponse(
                    f"Estimated travel time to delivery address: {travel_time} minutes", 
                    status_code=200
                )
            except Exception as e:
                return func.HttpResponse(f"Error calculating travel time: {str(e)}", status_code=500)
        
        # For other statuses, send the order data to the Event Grid topic
        event_grid_url = "https://visabeiragrid.northeurope-1.eventgrid.azure.net/api/events"
        event = {
            "id": str(uuid.uuid4()),
            "eventType": "newOrderReceived",
            "subject": "NewOrder",
            "eventTime": datetime.utcnow().isoformat(),
            "data": {
                "order_id": order_data["order_id"],
                "fieldServiceId": order_data["fieldServiceId"],
                "Material": order_data["Material"],
                "delivery_address": order_data["delivery_address"],
                "Status": order_data["Status"],
                "driverLocation": order_data.get("driverLocation", {})
            },
            "dataVersion": "1.0"
        }
        headers = {'aeg-sas-key': '79p4fG7wQAJlltOwJhNDKLrItzkJUWfXLAZEGAGv9Po='}
        response = requests.post(event_grid_url, json=[event], headers=headers)
        print(response)
        
        if response.status_code == 200:
            return func.HttpResponse(
                "Order placed successfully!", 
                status_code=200
            )
        else:
            return func.HttpResponse(
                f"Failed to send event to Event Grid: {response.text}", 
                status_code=response.status_code
            )
    except Exception as e:
        return func.HttpResponse(
            f"Internal Server Error: {str(e)}", 
            status_code=500
        )

def get_location(order_address, azure_maps_key):
    geocode_url = f"https://atlas.microsoft.com/search/address/json?api-version=1.0&subscription-key={azure_maps_key}&query={order_address}"
    response = requests.get(geocode_url)
    print(response)
    if response.status_code == 200:
        geocode_result = response.json()
        print(geocode_result)
        if geocode_result['results']:
            coordinates = geocode_result['results'][0]['position']
            print(coordinates)
            return coordinates['lat'], coordinates['lon']
        else:
            raise ValueError("Address not found.")
    else:
        raise Exception("Error calling Azure Maps Geocoding API.")

def calculate_travel_time(warehouse_lat, warehouse_lon, delivery_lat, delivery_lon, azure_maps_key):
    route_url = (
        f"https://atlas.microsoft.com/route/directions/json?"
        f"api-version=1.0&subscription-key={azure_maps_key}"
        f"&query={warehouse_lat},{warehouse_lon}:{delivery_lat},{delivery_lon}"
    )
    print(route_url)
    response = requests.get(route_url)
    if response.status_code == 200:
        route_data = response.json()
        travel_time_seconds = route_data['routes'][0]['summary']['travelTimeInSeconds']
        travel_time_minutes = travel_time_seconds / 60
        return round(travel_time_minutes, 2)
    else:
        raise Exception("Error calling Azure Maps Route API.")
