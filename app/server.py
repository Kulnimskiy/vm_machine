import asyncio
import json
import logging

from pydantic import ValidationError

from database import get_db_pool, create_vm, get_vm, get_vms, create_tables
from schemes import VM, Request, AuthenticateVM, Response


class VMServer:
    def __init__(self, host='127.0.0.1', port=8888):
        self.host = host
        self.port = port
        self.connection_pool = None
        self.active_clients = {}
        asyncio.run(self.init_db())

    async def init_db(self):
        """ Initialize the database and create necessary tables """
        self.connection_pool = await get_db_pool()
        await create_tables(self.connection_pool)

    async def start_server(self):
        svr = await asyncio.start_server(self.handle_client, self.host, self.port)
        print('Server running on {self.host}:{self.port}')
        async with svr:
            await svr.serve_forever()

    async def handle_client(self, reader, writer):
        addr = writer.get_extra_info('peername')
        self.active_clients[addr] = writer
        print(f'Client connected: {addr}')

        while True:
            try:
                data = await reader.read(1024)
                if not data:
                    break
                message = json.loads(data.decode())
                response = await self.process_command(message)
                json_data = response.model_dump_json() + "\n"  # Ensure the receiver knows message boundaries
                writer.write(json_data.encode())
                await writer.drain()
            except ValidationError as e:
                return Response(status="error", message=str(e))

        print(f'Client disconnected: {addr}')
        writer.close()
        await writer.wait_closed()

    async def process_command(self, message: dict) -> Response:
        try:
            request = Request(**message)
            command = request.command
            if command == 'ping':
                return await self.ping(request.data)
            if command == "register":
                return await self.register(VM(**request.data))
            elif command == "authenticate":
                return await self.authenticate(AuthenticateVM(**request.data))
            elif command == "list":
                return await self.list()
            elif command == "update":
                return await self.update(request.data)
            elif command == "logout":
                return await self.logout(request.data)
            return Response(status="success", message="Unknown command")
        except Exception as e:
            return Response(status="error", message=str(e), data=message)

    async def ping(self, message) -> Response:
        return Response(status="success", message=f"PONG", data=message)

    async def register(self, vm: VM) -> Response:
        await create_vm(self.connection_pool, vm)
        return Response(status="success")
        # except Exception as e:
        #     logging.error(e)
        #     return Response(status="error", message=str(e))

    async def authenticate(self, vm: AuthenticateVM) -> Response:
        vm = await get_vm(self.connection_pool, vm)
        if vm:
            return Response(status="success", message="Authentication successful")
        return Response(status="error", message="Invalid credentials")

    async def list(self) -> Response:
        vms = await get_vms(self.connection_pool)
        return Response(status="success", data=[dict(vm) for vm in vms])

    async def update(self, message):
        async with self.connection_pool.acquire() as conn:
            try:
                await conn.execute(
                    'UPDATE virtual_machines SET ram=$1, cpu=$2 WHERE vm_id=$3',
                    message["ram"], message["cpu"], message["vm_id"]
                )
                return Response(status="success", message="VM updated successfully")
            except Exception as e:
                return Response(status="error", message=str(e))

    async def logout(self, message):
        return {"status": "success", "message": "VM logged out successfully"}


if __name__ == "__main__":
    server = VMServer(host='0.0.0.0', port=8888)
    asyncio.run(server.start_server())
