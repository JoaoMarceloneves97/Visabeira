import azure.functions as func
import requests
import json
import uuid
import logging
import time
from datetime import datetime

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# HTTP Trigger Function
@app.function_name(name="http_trigger")
@app.route(route="http_trigger")
def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
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
                "Invalid format for 'Material'.",
                status_code=400
            )
        
        print(materials)
        event_grid_url = "https://startservice.northeurope-1.eventgrid.azure.net/api/events"
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
        headers = {'aeg-sas-key': 'Al2Q+Kw4BgNgwQxefF/07WuCVakzi53orAZEGP3W75s='}
        response = requests.post(event_grid_url, json=[event], headers=headers)
        logging.info(response)
        logging.info(response.text)
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



# Event Grid Trigger Function
EVENT_GRID_ENDPOINT = "https://fieldagentstatus.northeurope-1.eventgrid.azure.net/api/events"  # Replace with your Event Grid endpoint
EVENT_GRID_KEY = "nDRGcdiOTV7YdG9lsNM5Q1tK+rtMvc8q4AZEGMkxwRM="  # Replace with your Event Grid key
AZURE_MAPS_KEY = "CPiS0LsmIo4hpVm9X360A4vwRPreIhUxEsZ7wgrqErIxfKuY8G5xJQQJ99AFACi5YpzxJCnnAAAgAZMPcG7h"


@app.function_name(name="fieldservice_event_grid")
@app.event_grid_trigger(arg_name="event")
def event_grid_trigger(event: func.EventGridEvent):
    logging.info("Event received")
    
    event_data = event.get_json()
    order_id = event_data.get('order_id')
    field_service_id = event_data.get('fieldServiceId')
    materials = event_data.get('Material', [])
    delivery_address = event_data.get('delivery_address')
    status = event_data.get('Status')
    driver_location = event_data.get('driverLocation', {})

    logging.info(f"Order ID: {order_id}")
    logging.info(f"Field Service ID: {field_service_id}")
    logging.info(f"Materials: {materials}")
    logging.info(f"Delivery Address: {delivery_address}")
    logging.info(f"Status: {status}")
    logging.info(f"Driver Location: {driver_location}")

    if status == "pending_warehouse":
        event = {
            "id": str(uuid.uuid4()),
            "eventType": "newOrderReceived",
            "subject": "NewOrder",
            "eventTime": datetime.utcnow().isoformat(),
            "data": {
                "order_id": order_id,
                "fieldServiceId": field_service_id,
                "Material": materials,
                "delivery_address": delivery_address,
                "Status": "waiting_for_warehouse",
                "driverLocation": driver_location
            },
            "dataVersion": "1.0"
        }
        send_to_event_grid(event)
    else:
        warehouse_coords = (39.91344, -8.43924)
        delivery_coords = get_coordinates_from_address(delivery_address)
        
        logging.info(f"Warehouse coordinates: {warehouse_coords}")
        logging.info(f"Delivery coordinates: {delivery_coords}")
        
        route_points = calculate_route(warehouse_coords, delivery_coords)
        
        if route_points:
            logging.info(f"Route calculated. Total points: {len(route_points)}")
            logging.info(f"First point: {route_points[0]}")
            logging.info(f"Last point: {route_points[-1]}")
            
            send_initial_route_data(order_id, field_service_id, materials, delivery_address, 
                                    warehouse_coords, delivery_coords)
            
            send_route_updates(order_id, field_service_id, materials, delivery_address, route_points)
            logging.info(f"Route updates completed for order {order_id}")
        else:
            logging.error("Failed to calculate route")
def calculate_route(start, end):
    url = f"https://atlas.microsoft.com/route/directions/json?api-version=1.0&subscription-key={AZURE_MAPS_KEY}&query={start[0]},{start[1]}:{end[0]},{end[1]}"
    response = requests.get(url)
    route_info = response.json()
    
    if 'routes' in route_info and len(route_info['routes']) > 0:
        return route_info['routes'][0]['legs'][0]['points']
    return None
def send_initial_route_data(order_id, field_service_id, materials, delivery_address, start, end):
    event = {
        "id": str(uuid.uuid4()),
        "eventType": "SendingCoordinates",
        "subject": "NewOrder",
        "eventTime": datetime.utcnow().isoformat(),
        "data": {
            "order_id": order_id,
            "fieldServiceId": field_service_id,
            "Material": materials,
            "delivery_address": delivery_address,
            "Status": "Delivering_Order",
            "driverLocation": {
                "currentLocation": {
                    "latitude": str(start[0]),
                    "longitude": str(start[1])
                },
                "destination": {
                    "latitude": str(end[0]),
                    "longitude": str(end[1])
                },
                "eventType": "RouteData",
            },
        },
        "dataVersion": "1.0"
    }
    send_to_event_grid(event)

def send_route_updates(order_id, field_service_id, materials, delivery_address, route_points):
    total_points = len(route_points)
    num_points_to_send = 9  # We'll send 9 intermediate points + the destination
    
    logging.info(f"Total route points: {total_points}")
    logging.info(f"Start point: {route_points[0]}")
    logging.info(f"End point: {route_points[-1]}")
    
    # Calculate the step size to evenly distribute points
    step = max(1, (total_points - 1) // num_points_to_send)
    
    points_to_send = [
        (i, route_points[i]) 
        for i in range(0, total_points - 1, step)
    ][:num_points_to_send]
    
    # Add the destination point
    points_to_send.append((total_points - 1, route_points[-1]))
    
    logging.info(f"Points to send: {points_to_send}")
    
    start_point = route_points[0]
    end_point = route_points[-1]

    for index, point in points_to_send:
        is_last_point = (index == total_points - 1)
        
        event = {
            "id": str(uuid.uuid4()),
            "eventType": "SendingCoordinates",
            "subject": "RouteUpdate",
            "eventTime": datetime.utcnow().isoformat(),
            "data": {
                "order_id": order_id,
                "fieldServiceId": field_service_id,
                "Material": materials,
                "delivery_address": delivery_address,
                "Status": "Delivering_Order",
                "driverLocation": {
                    "currentLocation": {
                        "latitude": str(point['latitude']),
                        "longitude": str(point['longitude'])
                    },
                    "destination": {
                        "latitude": str(end_point['latitude']),
                        "longitude": str(end_point['longitude'])
                    },
                    "eventType": "RouteData",
                },
            },
            "dataVersion": "1.0"
        }
        
        logging.info(f"Sending event for point {index + 1}/{len(points_to_send)}:")
        logging.info(f"Current location: {point}")
        logging.info(f"Destination: {end_point}")
        logging.info(f"Event data: {json.dumps(event, indent=2)}")
        
        send_to_event_grid(event)
        
        logging.info(f"Sent coordinate {index + 1} of {len(points_to_send)} for order {order_id}")
        
        if is_last_point:
            logging.info(f"Last coordinate (destination) sent for order {order_id}. Ending function.")
            return  # Exit the function after sending the last coordinate
        
        time.sleep(10)  # Wait 10 seconds between each coordinate

    logging.info(f"All selected coordinates sent for order {order_id}. Ending function.")
    
def send_to_event_grid(event):
    headers = {'aeg-sas-key': EVENT_GRID_KEY}
    response = requests.post(EVENT_GRID_ENDPOINT, json=[event], headers=headers)
    logging.info(f"Event Grid Response: {response.status_code}")
    if response.status_code != 200:
        logging.error(f"Failed to send event to Event Grid: {response.text}")

def get_coordinates_from_address(address):
    search_url = f"https://atlas.microsoft.com/search/address/json?api-version=1.0&subscription-key={AZURE_MAPS_KEY}&query={address}"
    response = requests.get(search_url)
    search_results = response.json()
    coordinates = search_results['results'][0]['position']
    return (coordinates['lat'], coordinates['lon'])