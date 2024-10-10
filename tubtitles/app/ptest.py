import asyncio
import websockets
from multiprocessing import Process
import signal
import sys
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def start_server(port, message):
    """
    Starts a WebSocket server on the specified port that sends the given message
    to all connected clients every 4 seconds.
    """
    clients = set()

    async def handler(websocket, path):
        """
        Handles incoming WebSocket connections.
        Registers the client and keeps the connection open.
        """
        # Register the new client
        clients.add(websocket)
        client_id = uuid.uuid4()
        logger.info(f"Client {client_id} connected to port {port}")
        try:
            # Keep the connection open
            await websocket.wait_closed()
        finally:
            # Unregister the client on disconnect
            clients.remove(websocket)
            logger.info(f"Client {client_id} disconnected from port {port}")

    async def broadcaster():
        """
        Sends the specified message to all connected clients every 4 seconds.
        """
        while True:
            if clients:  # Only send if there are connected clients
                message_to_send = message
                await asyncio.wait([client.send(message_to_send) for client in clients])
                logger.info(f"Sent message on port {port}: {message_to_send}")
            await asyncio.sleep(4)  # Wait for 4 seconds before sending the next message

    async def main():
        """
        Main coroutine to start the WebSocket server and the broadcaster task.
        """
        # Start the WebSocket server
        server = await websockets.serve(handler, "0.0.0.0", port)
        logger.info(f"WebSocket server started on ws://localhost:{port}")

        # Start the broadcaster task
        broadcaster_task = asyncio.create_task(broadcaster())

        # Run the server until it's closed
        await server.wait_closed()

    # Get the current event loop or create a new one
    try:
        asyncio.run(main())
    except asyncio.CancelledError:
        logger.info(f"Server on port {port} has been cancelled.")
    except KeyboardInterrupt:
        logger.info(f"Shutting down server on port {port}")

def main():
    # Define server configurations: (port, message)
    servers = [
        (8566, "from process A"),
        (8567, "from process B")
    ]

    # Create a list to hold the server processes
    processes = []

    # Start each server in its own process
    for port, message in servers:
        process = Process(target=start_server, args=(port, message))
        process.start()
        processes.append(process)
        logger.info(f"Started process for port {port}")

    # Define a signal handler to gracefully shut down servers on Ctrl+C
    def shutdown(signum, frame):
        logger.info("Shutting down servers...")
        for process in processes:
            process.terminate()
            process.join()
            logger.info(f"Terminated process for port {servers[processes.index(process)][0]}")
        sys.exit(0)

    # Register the signal handler for SIGINT (Ctrl+C)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Keep the main process running to listen for signals
    for process in processes:
        process.join()

if __name__ == "__main__":
    main()