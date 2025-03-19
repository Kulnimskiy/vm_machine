import json
import asyncio
import logging
from pydantic import ValidationError

from utils import Token
from database import DbPool, DatabaseManager, PasswordHandler
from schemes import VM, Request, AuthenticateVM, Response, ListVM, Logout, UpdateVM, Disk


class VMServer:
    def __init__(self, host='127.0.0.1', port=8888):
        """
        Initializes the VMServer instance.

        Attributes:
            host (str): The server's IP address.
            port (int): The server's listening port.
            active_clients (dict): A dictionary storing connected active
            clients and authenticated clients with tokens.
            commands (dict): A mapping of command strings to their respective handler methods.
        """

        self.host = host
        self.port = port
        self.active_clients = {}
        self.commands = {
            "ping": self.ping,
            "register": self.register,
            "authenticate": self.authenticate,
            "list": self.list,
            "update": self.update,
            "logout": self.logout
        }

    async def init_db(self) -> None:
        """ Initialize the database and create necessary tables """
        connection_pool = await DbPool.create_pool()
        logging.info(f'Database connection pool: {connection_pool}')
        await DatabaseManager.create_tables(connection_pool)

    async def start_server(self) -> None:
        """ Starts the server to accept commands """
        svr = await asyncio.start_server(self.handle_client, self.host, self.port)
        logging.info(f'Server running on {self.host}:{self.port}')
        async with svr:
            await svr.serve_forever()

    async def send_response(self, writer, response: Response) -> None:
        response_data = response.model_dump_json() + "\n"
        writer.write(response_data.encode())
        await writer.drain()

    async def handle_client(self, reader, writer):
        """
        Main client handler. Stores the clients address and tokens in active
        clients variable also listening to clients commands, The commands are accepted in the json format
        that gets validated with pydantic schemes in the commands' logic.
        """
        addr: tuple[str, int] = writer.get_extra_info('peername')
        self.active_clients[addr] = {"token": None, "writer": writer}
        logging.info(f'Client connected: {addr}')

        while True:
            try:
                user_message = await reader.read(4096)
                if not user_message:
                    break

                message_data = json.loads(user_message.decode())
                request = Request(**message_data)
                request.data['addr'] = addr
                response = await self.process_command(request)
                await self.send_response(writer, response)

            except ValidationError as e:
                logging.error(f"User {addr}: {e}")
                await self.send_response(writer, Response(status="error", message=str(e)))
                continue

            except Exception as e:
                logging.error(f"User {addr}: {e}")
                break

        writer.close()
        self.active_clients.pop(addr, None)
        await writer.wait_closed()
        logging.info(f'Client disconnected: {addr}')

    async def process_command(self, request: Request) -> Response:
        """
        Validates and runs server commands
        """
        try:
            command = request.command.lower()
            if command in self.commands:
                return await self.commands[command](request.data)

            return Response(status="success", message="Unknown command")

        except Exception as e:
            return Response(status="error", message=str(e), data=request.data)

    async def ping(self, request_data: dict) -> Response:
        """
        A method for the client to check if the server is running
        """
        logging.info(f"User: {request_data['addr']} pings")
        return Response(status="success", message=f"PONG", data=request_data)

    async def register(self, request_data: dict) -> Response:
        """
        A method for the client to register a new vm machine. Uses VM pydantic scheme for validation
        """
        vm = VM(**request_data)
        connection_pool = await DbPool.get_pool()
        await DatabaseManager.create_vm(connection_pool, vm)
        logging.info(f"Registered VM: {vm.model_dump(exclude={'password'})}")

        return Response(status="success", message="Save the vm_id for authentication", data={"auth_id": vm.vm_id})

    async def authenticate(self, request_data: dict) -> Response:
        """
        Authenticates the user and sends him a jwt token to gain access to protected commands
        """
        auth_data = AuthenticateVM(**request_data)
        connection_pool = await DbPool.get_pool()

        vm = await DatabaseManager.get_vm(connection_pool, auth_data.vm_id)
        if vm and PasswordHandler.verify_password(auth_data.password, vm.password):
            self.active_clients[auth_data.addr]["token"] = Token.generate_token(vm.vm_id)
            logging.info(f'Authenticated user: {auth_data.addr} vm_id: {vm.vm_id}')

            return Response(
                status="success", message="Authentication successful",
                data={"token": self.active_clients[auth_data.addr]['token']}
            )

        return Response(status="error", message="Invalid credentials")

    async def list(self, request_data: dict) -> Response:
        """
        A protected command to display info from the server. Available only for authenticated users.
        They can list:
        - active users (command: active_vms)
        - authenticated users and their virtual machine info (command: authenticated_vms)
        - all virtual machines (command: all_vms)
        - all disks (command: all_disks)
        """
        command_data = ListVM(**request_data)
        auth_token = self.active_clients[command_data.addr]["token"]
        if auth_token is None:
            return Response(status="error", message="You have to authenticate to run this operation")

        if auth_token != command_data.token:
            return Response(
                status="error", message="Invalid access token. Try refreshing with the 'authenticate' command"
            )

        user_vm_id = Token.get_vm_id(auth_token)

        if command_data.list_type == "active_vms":
            logging.info(f"VM({user_vm_id}): active_vms command")
            active, _ = await self.get_users()

            return Response(status="success", data={"active_vms": active})

        elif command_data.list_type == "authenticated_vms":
            logging.info(f"VM({user_vm_id}): authenticated_vms command")
            _, authenticated = await self.get_users()

            return Response(status="success", data={"authenticated_vms": authenticated})

        elif command_data.list_type == "all_vms":
            logging.info(f"VM({user_vm_id}): all_vms command")
            connection_pool = await DbPool.get_pool()
            vms = await DatabaseManager.get_vms(connection_pool)

            return Response(
                status="success",
                data={"all_vms": [vm.model_dump(exclude_none=True, exclude={"password"}) for vm in vms]}
            )

        elif command_data.list_type == "all_disks":
            logging.info(f"VM({user_vm_id}): all_disks command")
            connection_pool = await DbPool.get_pool()
            discs = await DatabaseManager.get_disks(connection_pool)

            return Response(status="success",
                            data={"all_disks": [disc.model_dump(exclude_none=True) for disc in discs]})

        else:
            logging.info(f"VM({user_vm_id}): unknown list command type")
            return Response(status="error", message="Unknown list command type")

    async def get_users(self) -> tuple[list, list]:
        """
        Returns all active users and authenticated users with their virtual machine info
        """
        active_vms = []
        authenticated_vms = []
        connection_pool = await DbPool.get_pool()
        for addr, auth_data in self.active_clients.items():
            token = auth_data.get("token")

            if token:
                vm: VM = await DatabaseManager.get_vm(connection_pool, Token.get_vm_id(token))
                vm_info = vm.model_dump(exclude_none=True, exclude={'password'}) if vm else dict()
                active_vms.append({"addr": addr, "vm_info": vm_info})
                authenticated_vms.append({"addr": addr, "vm_info": vm_info})

            else:
                active_vms.append({"addr": addr})

        return active_vms, authenticated_vms

    async def update(self, request_data: dict) -> Response:
        """
        Updates virtual machine info (ram, cpu, disks) for the authenticated user
        """
        command_data = UpdateVM(**request_data)

        auth_token = self.active_clients[command_data.addr]["token"]
        if auth_token is None:
            return Response(status="error", message="You have to authenticate to run this operation")

        if auth_token != command_data.token:
            return Response(
                status="error", message="Invalid access token. Try refreshing with the 'authenticate' command"
            )

        vm_id = Token.get_vm_id(auth_token)
        try:
            connection_pool = await DbPool.get_pool()
            await DatabaseManager.update_vm(connection_pool, vm_id, command_data)
            logging.info(f"Updated virtual machine info for vm: {vm_id}")
            return Response(status="success", message="VM info updated successfully")

        except Exception as e:
            logging.info(f"Error updating virtual machine info for vm: {vm_id}, {e}")
            return Response(status="error", message=str(e))

    async def logout(self, request_data: dict):
        command_data = Logout(**request_data)
        auth_token = self.active_clients[command_data.addr]["token"]
        if auth_token is None:
            return Response(status="error", message="You have to authenticate to run this operation")

        if auth_token != command_data.token:
            return Response(
                status="error", message="Invalid access token. Try refreshing with the 'authenticate' command"
            )

        vm_id = Token.get_vm_id(auth_token)
        self.active_clients[command_data.addr]["token"] = None

        logging.info(f"Logged out user: {vm_id}")
        return Response(status="success", message=f"VM ({vm_id}) logged out successfully")


if __name__ == "__main__":
    server = VMServer(host='0.0.0.0', port=8888)
    asyncio.run(server.init_db())
    asyncio.run(server.start_server())
