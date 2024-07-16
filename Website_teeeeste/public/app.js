const subscriptionKey = 'CPiS0LsmIo4hpVm9X360A4vwRPreIhUxEsZ7wgrqErIxfKuY8G5xJQQJ99AFACi5YpzxJCnnAAAgAZMPcG7h';
let map, popup;
const carMarkers = new Map(); // Map to store car markers by orderID
const routeLines = new Map(); // Map to store route lines by orderID
const destinationMarkers = new Map(); // Map to store destination markers by orderID

function initializeMap() {
    console.log('Initializing map');
    
    map = new atlas.Map('myMap', {
        center: [-8.41476, 40.06037],
        zoom: 9,
        view: 'Auto',
        authOptions: {
            authType: 'subscriptionKey',
            subscriptionKey: subscriptionKey
        }
    });

    map.events.add('ready', () => {
        console.log('Map is ready');
        popup = new atlas.Popup();
    });
}

function createCarMarker(orderId, position) {
    const marker = new atlas.HtmlMarker({
        color: 'DodgerBlue',
        text: '🚗',
        position: position
    });
    map.markers.add(marker);
    carMarkers.set(orderId, { marker, position });

    map.events.add('click', marker, () => {
        const currentPosition = carMarkers.get(orderId).position;
        showPopup(currentPosition, `Car (Order ${orderId})`);
    });
}

function createDestinationMarker(orderId, position) {
    const marker = new atlas.HtmlMarker({
        color: 'Red',
        text: '🏁',
        position: position
    });
    map.markers.add(marker);
    destinationMarkers.set(orderId, marker);

    map.events.add('click', marker, () => showPopup(position, `Destination (Order ${orderId})`));
}

function createRouteLine(orderId, coordinates) {
    const dataSource = new atlas.source.DataSource();
    map.sources.add(dataSource);

    const line = new atlas.data.LineString(coordinates);
    dataSource.add(line);

    const layer = new atlas.layer.LineLayer(dataSource, null, {
        strokeColor: 'DodgerBlue',
        strokeWidth: 3
    });
    map.layers.add(layer);

    routeLines.set(orderId, { dataSource, layer });
}

function showPopup(position, markerType) {
    const content = `
        <div>
            <strong>${markerType}:</strong><br>
            Latitude: ${position[1].toFixed(6)}<br>
            Longitude: ${position[0].toFixed(6)}
        </div>`;
    popup.setOptions({
        position: position,
        content: content
    });
    popup.open(map);
}

async function calculateRoute(start, end) {
    const pipeline = atlas.service.MapsURL.newPipeline(new atlas.service.SubscriptionKeyCredential(atlas.getSubscriptionKey()));
    const routeClient = new atlas.service.RouteURL(pipeline);
    
    try {
        const routeResult = await routeClient.calculateRouteDirections(atlas.service.Aborter.timeout(10000), [start, end]);
        
        if (routeResult.routes.length > 0) {
            const data = routeResult.routes[0].legs[0].points;
            const coordinates = data.map(point => [point.longitude, point.latitude]);
            return coordinates;
        }
    } catch (error) {
        console.error('Error calculating route:', error);
    }
    
    return null;
}

function drawRoute(orderId, route) {
    const routeLine = routeLines.get(orderId);
    if (routeLine) {
        routeLine.dataSource.clear();
        routeLine.dataSource.add(new atlas.data.LineString(route));
    } else {
        createRouteLine(orderId, route);
    }
}

function resetMap() {
    console.log('Resetting map');
    
    // Remove all car markers
    carMarkers.forEach(({ marker }, orderId) => {
        map.markers.remove(marker);
    });
    carMarkers.clear();

    // Remove all destination markers
    destinationMarkers.forEach((marker, orderId) => {
        map.markers.remove(marker);
    });
    destinationMarkers.clear();

    // Remove all route lines
    routeLines.forEach((routeLine, orderId) => {
        map.layers.remove(routeLine.layer);
        map.sources.remove(routeLine.dataSource);
    });
    routeLines.clear();

    // Close any open popup
    if (popup) {
        popup.close();
    }

    // Reset the map view to the initial state
    map.setCamera({
        center: [-8.41476, 40.06037],
        zoom: 9
    });

    console.log('Map reset complete');
}

function clearCache() {
    console.log('Clearing cache and resetting map');
    resetMap();
    
    // Clear initialRouteData on the server
    fetch('/reset-all', { method: 'POST' })
        .then(response => {
            if (response.ok) {
                console.log('Server data reset successfully');
            } else {
                console.error('Failed to reset server data');
            }
        })
        .catch(error => console.error('Error resetting server data:', error));

    // Optionally, you can still try to clear the browser cache
    if ('caches' in window) {
        caches.keys().then((names) => {
            names.forEach(name => {
                caches.delete(name);
            });
        });
    }

    console.log('Cache cleared and map reset');
}

window.onload = function() {
    initializeMap();
};

const socket = io('/', { query: { version: '1.0.1' } });

socket.on('connect', () => {
    console.log('Connected to Socket.IO server');
    socket.emit('requestInitialData');
});

socket.on('initialRoute', async (data) => {
    console.log('Received initial route data:', data);

    if (!data || data.version !== "1.1" || !data.driverLocation) {
        console.error('Invalid or missing initial route data');
        return;
    }

    const { currentLocation, destination } = data.driverLocation;
    const orderId = data.order_id;

    if (currentLocation && destination &&
        currentLocation.longitude && currentLocation.latitude &&
        destination.longitude && destination.latitude) {
        
        const startPosition = [parseFloat(currentLocation.longitude), parseFloat(currentLocation.latitude)];
        const endPosition = [parseFloat(destination.longitude), parseFloat(destination.latitude)];

        createCarMarker(orderId, startPosition);
        createDestinationMarker(orderId, endPosition);

        try {
            const routeCoordinates = await calculateRoute(startPosition, endPosition);
            if (routeCoordinates) {
                createRouteLine(orderId, routeCoordinates);
                map.setCamera({
                    bounds: atlas.data.BoundingBox.fromPositions(routeCoordinates),
                    padding: 50
                });
                console.log('Route calculated and drawn for order:', orderId);
            } else {
                console.error('Failed to calculate route for order:', orderId);
            }
        } catch (error) {
            console.error('Error calculating route for order:', orderId, error);
        }

        console.log('Initial markers set for order:', orderId);
    } else {
        console.error('Invalid coordinates in initial route data for order:', orderId);
    }
});

socket.on('routeUpdate', async (data) => {
    console.log('Received route update:', data);
    if (data && data.version === "1.1" && data.driverLocation) {
        const { currentLocation, destination } = data.driverLocation;
        const orderId = data.order_id;

        if (currentLocation && destination &&
            currentLocation.longitude && currentLocation.latitude &&
            destination.longitude && destination.latitude) {
            
            const currentPosition = [parseFloat(currentLocation.longitude), parseFloat(currentLocation.latitude)];
            const destinationPosition = [parseFloat(destination.longitude), parseFloat(destination.latitude)];

            let carMarkerData = carMarkers.get(orderId);
            if (!carMarkerData) {
                createCarMarker(orderId, currentPosition);
            } else {
                carMarkerData.marker.setOptions({ position: currentPosition });
                carMarkerData.position = currentPosition;  // Update the stored position
            }

            let destinationMarker = destinationMarkers.get(orderId);
            if (!destinationMarker) {
                createDestinationMarker(orderId, destinationPosition);
            } else {
                destinationMarker.setOptions({ position: destinationPosition });
            }

            console.log(`Car marker moved for order ${orderId} to: Latitude: ${currentLocation.latitude}, Longitude: ${currentLocation.longitude}`);

            try {
                const routeCoordinates = await calculateRoute(currentPosition, destinationPosition);
                if (routeCoordinates) {
                    drawRoute(orderId, routeCoordinates);
                    console.log('Route recalculated and redrawn for order:', orderId);
                } else {
                    console.error('Failed to calculate route for order:', orderId);
                }
            } catch (error) {
                console.error('Error calculating route for order:', orderId, error);
            }
        } else {
            console.error('Invalid coordinates in route update for order:', orderId);
        }
    } else {
        console.error('Invalid route update data structure');
    }
});

socket.on('reset', (orderId) => {
    console.log('Received reset signal for order:', orderId);
    const carMarkerData = carMarkers.get(orderId);
    if (carMarkerData) {
        map.markers.remove(carMarkerData.marker);
        carMarkers.delete(orderId);
    }
    const destinationMarker = destinationMarkers.get(orderId);
    if (destinationMarker) {
        map.markers.remove(destinationMarker);
        destinationMarkers.delete(orderId);
    }
    const routeLine = routeLines.get(orderId);
    if (routeLine) {
        map.layers.remove(routeLine.layer);
        map.sources.remove(routeLine.dataSource);
        routeLines.delete(orderId);
    }
    popup.close();
});

socket.on('reset-all', () => {
    console.log('Received reset-all signal');
    resetMap();
});

socket.on('disconnect', () => {
    console.log('Disconnected from Socket.IO server');
});