const express = require('express');
const bodyParser = require('body-parser');
const path = require('path');
const app = express();
const port = process.env.PORT || 3000;

app.use(bodyParser.json());
app.use(express.static(path.join(__dirname, 'public')));

// Add cache-control headers to prevent caching
app.use((req, res, next) => {
  res.set('Cache-Control', 'no-store, no-cache, must-revalidate, private');
  next();
});

let initialRouteData = new Map();

app.post('/eventgrid', (req, res) => {
    console.log('Received request to /eventgrid');
    console.log('Headers:', JSON.stringify(req.headers, null, 2));
    console.log('Body:', JSON.stringify(req.body, null, 2));

    const events = Array.isArray(req.body) ? req.body : [req.body];

    if (events[0] && events[0].eventType === 'Microsoft.EventGrid.SubscriptionValidationEvent') {
        const validationResponse = {
            validationResponse: events[0].data.validationCode
        };
        console.log('Responding to validation request with:', JSON.stringify(validationResponse));
        return res.status(200).json(validationResponse);
    }

    events.forEach((event, index) => {
        console.log(`Processing event ${index + 1}:`, JSON.stringify(event, null, 2));
        if (event.eventType === 'SendingCoordinates') {
            const routeData = event.data.driverLocation;
            const orderId = event.data.order_id;
            if (!initialRouteData.has(orderId)) {
                initialRouteData.set(orderId, { driverLocation: routeData, version: "1.1", order_id: orderId });
                console.log('Emitting initial route data:', JSON.stringify(initialRouteData.get(orderId), null, 2));
                io.emit('initialRoute', initialRouteData.get(orderId));
            } else {
                const currentLocation = routeData.currentLocation;
                console.log('Emitting route update:', JSON.stringify({ driverLocation: routeData, version: "1.1", order_id: orderId }, null, 2));
                io.emit('routeUpdate', { driverLocation: routeData, version: "1.1", order_id: orderId });
            }
        } else {
            console.log(`Unhandled event type: ${event.eventType}`);
        }
    });

    console.log('Finished processing events. Sending 200 response.');
    res.sendStatus(200);
});

app.post('/reset', (req, res) => {
    const orderId = req.body.order_id;
    if (orderId) {
        initialRouteData.delete(orderId);
        io.emit('reset', orderId);
        res.sendStatus(200);
    } else {
        res.status(400).send('Missing order_id in request body');
    }
});

app.post('/reset-all', (req, res) => {
    initialRouteData.clear();
    io.emit('reset-all');
    res.sendStatus(200);
});

const server = app.listen(port, () => {
    console.log(`Server is running on port ${port}`);
});

const io = require('socket.io')(server);

io.on('connection', (socket) => {
    console.log('New client connected');
    socket.on('requestInitialData', () => {
        initialRouteData.forEach((data, orderId) => {
            socket.emit('initialRoute', data);
        });
    });
    socket.on('disconnect', () => {
        console.log('Client disconnected');
    });
});