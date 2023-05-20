```python
import asyncio
import websockets
import hashlib
import hmac
import json

async def connect():
    async with websockets.connect('wss://example.com/wsapi/v1/live_notifications') as websocket:
        nonce = str(int(round(time.time() * 1000)))
	api_key = '<YOUR API KEY>'
        secret_key = '<YOUR SECRET KEY>'
        message = api_key + nonce
        signature = hmac.new(
           secret_key.encode(),
           message.encode('utf-8'),
           hashlib.sha256
        ).hexdigest().upper()

        # Construct authentication message
        auth_data = {
            'api_key': api_key,
	    'signature': signature,
            'nonce': nonce
        }
        # Send authentication message
        await websocket.send(json.dumps(auth_data))

        # Wait for server response
        response = await websocket.recv()
        print(response)

        # Send sample messages
        for i in range(5):
            message = {
                'type': 'sample_message',
                'data': {'index': i},
            }
            await websocket.send(json.dumps(message))

            # Wait for server response
            response = await websocket.recv()
            print(response)

asyncio.get_event_loop().run_until_complete(connect())
```
