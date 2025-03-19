import jwt
import datetime
import asyncio
import json
import logging

from pydantic import ValidationError

from config import SECRET_KEY
from database import DbPool, create_vm, get_vm, get_vms, create_tables, get_disks, verify_password
from schemes import VM, Request, AuthenticateVM, Response, ListVM, Logout, UpdateVM, Disk


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
        self.commands = {
            "ping": self.ping,
            "register": self.register,
            "authenticate": self.authenticate,
            "list": self.list,
            "update": self.update,
            "logout": self.logout
        }

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
                user_message = await reader.read(4096)
                if not user_message:
                    break

                message_decoded = json.loads(user_message.decode())
                request = Request(**message_decoded)
                request.data['addr'] = addr
                response = await self.process_command(request)

                json_data = response.model_dump_json() + "\n"  # Ensure the receiver knows message boundaries
                writer.write(json_data.encode())
                await writer.drain()

            except ValidationError as e:
                return Response(status="error", message=str(e))

        writer.close()
        self.active_clients.pop(addr, None)
        await writer.wait_closed()
        logging.info(f'Client disconnected: {addr}')

    async def process_command(self, request: Request) -> Response:
        try:
            command = request.command.lower()
            if command in self.commands:
                return await self.commands[command](request.data)

            return Response(status="success", message="Unknown command")
        except Exception as e:
            return Response(status="error", message=str(e), data=request.data)

    async def ping(self, request_data: dict) -> Response:
        return Response(status="success", message=f"PONG", data=request_data)

    async def register(self, request_data: dict) -> Response:
        vm = VM(**request_data)
        connection_pool = await DbPool.get_pool()
        await create_vm(connection_pool, vm)
        return Response(status="success", message="Save the vm_id for authentication", data={"auth_id": vm.vm_id})

    async def authenticate(self, request_data: dict) -> Response:
        logging.info("in auth")
        logging.info(request_data)
        auth_data = AuthenticateVM(**request_data)
        logging.info(auth_data)
        connection_pool = await DbPool.get_pool()
        logging.info(auth_data.password)
        vm = await get_vm(connection_pool, auth_data.vm_id)
        logging.info(vm)
        if vm and verify_password(auth_data.password, vm.password):
            self.active_clients[auth_data.addr]["token"] = Token.generate_token(vm.vm_id)
            return Response(
                status="success", message="Authentication successful",
                data={"token": self.active_clients[auth_data.addr]['token']}
            )
        return Response(status="error", message="Invalid credentials")

    async def list(self, request_data: dict) -> Response:
        command_data = ListVM(**request_data)
        auth_token = self.active_clients[command_data.addr]["token"]
        if auth_token is None:
            return Response(status="error", message="You have to authenticate to do this operation")

        if auth_token != command_data.token:
            return Response(status="error", message="Invalid access token")

        if command_data.list_type == "active_vms":
            return Response(status="success", data={"active_vms": await self.get_active()})

        elif command_data.list_type == "authenticated_vms":
            return Response(status="success", data={"authenticated_vms": await self.get_authenticated()})

        elif command_data.list_type == "all_vms":
            connection_pool = await DbPool.get_pool()
            vms = await get_vms(connection_pool)
            logging.info(vms)
            return Response(status="success", data={"all_vms": [dict(vm) for vm in vms]})

        elif command_data.list_type == "all_disks":
            connection_pool = await DbPool.get_pool()
            discs = await get_disks(connection_pool)
            return Response(status="success", data={"all_disks": [dict(disc) for disc in discs]})
        else:
            return Response(status="success", message="Unknown list type")

    async def update(self, request_data: dict) -> Response:
        command_data = UpdateVM(**request_data)

        auth_token = self.active_clients[command_data.addr]["token"]
        if auth_token is None:
            return Response(status="error", message="You have to authenticate to do this operation")
        if auth_token != command_data.token:
            return Response(status="error", message="Invalid access token")

        update_fields = command_data.model_dump(exclude_none=True, exclude={'addr', 'token', 'disks'})
        token_payload = Token.decode_token(auth_token)
        vm_id = token_payload["vm_id"]

        if not update_fields:
            return {"status": "error", "message": f"No fields to update for VM:{vm_id}"}

        # Build dynamic SQL query
        set_clause = ", ".join([f"{field}=${i + 1}" for i, field in enumerate(update_fields.keys())])
        values = list(update_fields.values()) + [vm_id]

        query = f"UPDATE virtual_machines SET {set_clause} WHERE vm_id=${len(values)}"
        delete_old_disks_query = f"DELETE FROM disks WHERE vm_id=$1"
        create_new_disk_query = f"INSERT INTO disks (vm_id, disk_size) VALUES ($1, $2)"

        async with (await DbPool.get_pool()).acquire() as conn:
            try:
                async with conn.transaction():
                    await conn.execute(query, *values)
                    await conn.execute(delete_old_disks_query, vm_id)
                    for disk in command_data.disks:
                        logging.info(disk)
                        await conn.execute(create_new_disk_query, vm_id, disk.disk_size)
                return Response(status="success", message="VM updated successfully")
            except Exception as e:
                return Response(status="error", message=str(e))

    async def logout(self, request_data: dict):
        command_data = Logout(**request_data)
        auth_token = self.active_clients[command_data.addr]["token"]
        if auth_token is None:
            return Response(status="error", message="You have to authenticate to do this operation")

        if auth_token != command_data.token:
            return Response(status="error", message="Invalid access token")

        self.active_clients[command_data.addr]["token"] = None
        return {"status": "success", "message": "VM logged out successfully"}

    async def get_active(self) -> list:
        active_vms = []
        connection_pool = await DbPool.get_pool()
        for ip, vm in self.active_clients.items():
            if vm["token"]:
                token_payload = Token.decode_token(vm["token"])
                vm: VM = await get_vm(connection_pool, token_payload["vm_id"])
                vm_info = vm.model_dump(exclude_none=True, exclude='password') if vm else None
                active_vms.append({"addr": ip, "vm_info": vm_info})
            else:
                active_vms.append({"addr": ip})

        return active_vms

    async def get_authenticated(self) -> list:
        authenticated_vms = []
        connection_pool = await DbPool.get_pool()
        for ip, vm in self.active_clients.items():
            if vm["token"]:
                token_payload = Token.decode_token(vm["token"])
                vm: VM = await get_vm(connection_pool, token_payload["vm_id"])
                vm_info = vm.model_dump(exclude_none=True, exclude='password') if vm else None
                authenticated_vms.append({"addr": ip, "vm_info": vm_info})

        return authenticated_vms


if __name__ == "__main__":
    server = VMServer(host='0.0.0.0', port=8888)
    asyncio.run(server.init_db())
    asyncio.run(server.start_server())
