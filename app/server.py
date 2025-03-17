import jwt
import datetime
import asyncio
import json
import logging

from pydantic import ValidationError

from app.database import get_disks
from config import SECRET_KEY
from database import DbPool, create_vm, get_vm, get_vms, create_tables
from schemes import VM, Request, AuthenticateVM, Response


class Token:

    @staticmethod
    def generate_token(vm_id):
        payload = {
            "vm_id": vm_id,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)  # Token expiration
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        return token

    @staticmethod
    def decode_token(token):
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])


class VMServer:
    def __init__(self, host='127.0.0.1', port=8888):
        self.host = host
        self.port = port
        self.active_clients = {}  # Stores users with auth tokens "ip": {"token": None, "writer": Writer}

    async def init_db(self):
        """ Initialize the database and create necessary tables """
        connection_pool = await DbPool.create_pool()
        logging.info(f'Database connection pool: {connection_pool}')
        await create_tables(connection_pool)

    async def start_server(self):
        svr = await asyncio.start_server(self.handle_client, self.host, self.port)
        logging.info(f'Server running on {self.host}:{self.port}')
        async with svr:
            await svr.serve_forever()

    async def handle_client(self, reader, writer):
        addr = writer.get_extra_info('peername')
        self.active_clients[addr] = {"token": None, "writer": writer}
        logging.info(f'Client connected: {addr}')

        while True:
            try:
                data = await reader.read(1024)
                if not data:
                    break

                message = json.loads(data.decode())
                response = await self.process_command(message, addr)
                json_data = response.model_dump_json() + "\n"  # Ensure the receiver knows message boundaries
                writer.write(json_data.encode())
                await writer.drain()
            except ValidationError as e:
                return Response(status="error", message=str(e))

        logging.info(f'Client disconnected: {addr}')
        writer.close()
        await writer.wait_closed()

    async def process_command(self, message: dict, addr) -> Response:
        try:
            request = Request(**message)
            command = request.command
            if command == 'ping':
                return await self.ping(request.data)

            if command == "register":
                return await self.register(VM(**request.data))

            elif command == "authenticate":
                return await self.authenticate(AuthenticateVM(**request.data), addr)

            elif command == "list":
                return await self.list(**request.data)

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
        connection_pool = await DbPool.get_pool()
        try:
            await create_vm(connection_pool, vm)
            return Response(status="success")
        except Exception as e:
            logging.error(e)
            return Response(status="error", message=str(e))

    async def authenticate(self, vm: AuthenticateVM, addr: str) -> Response:
        connection_pool = await DbPool.get_pool()
        vm = await get_vm(connection_pool, vm)
        if vm:
            self.active_clients[addr]["token"] = Token.generate_token(vm.vm_id)
            self.active_clients[addr]["parameters"] = vm.dict(exclude="password")
            return Response(
                status="success", message="Authentication successful",
                data={"token": self.active_clients[addr]["token"]}
            )
        return Response(status="error", message="Invalid credentials")

    async def list(self, type: str = None) -> Response:
        if type == "active":
            return Response(
                status="success",
                data={"connected_vms": list(self.active_clients.keys())}
            )
        elif type == "authenticated":
            logging.info(self.active_clients.items())
            return Response(
                status="success",
                data={
                    "connected_vms": {
                        machine: data.get('parameters') for machine, data in self.active_clients.items() if data.get('parameters')}
                }
            )
        elif type == "discs":
            connection_pool = await DbPool.get_pool()
            discs = await get_disks(connection_pool)
            return Response(status="success", data={
                "connected_vms": [dict(disc) for disc in discs]
            })
        else:
            connection_pool = await DbPool.get_pool()
            vms = await get_vms(connection_pool)
            return Response(status="success", data={
                "connected_vms": [dict(vm) for vm in vms]
            })

    async def update(self, message):
        async with (await DbPool.get_pool()).acquire() as conn:
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
    asyncio.run(server.init_db())
    asyncio.run(server.start_server())
