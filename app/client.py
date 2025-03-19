import asyncio
import json
from pprint import pprint


class VM:
    def __init__(self, vm_id=None, password=None, ram=None, cpu=None, disks=None, reader=None, writer=None):
        self.vm_id = vm_id
        self.password = password
        self.ram = ram
        self.cpu = cpu
        self.disks = disks if disks is not None else []
        self.reader = reader
        self.writer = writer
        self.auth_token = None

    async def send_command(self, command):
        self.writer.write(json.dumps(command).encode())
        await self.writer.drain()

        data = await self.reader.read(4096)
        try:
            json_data = json.loads(data.decode())
        except json.JSONDecodeError:
            json_data = dict()

        print("Server response: ")
        pprint(json_data)
        return json_data

    async def ping(self):
        command = {
            "command": "ping",
            "data": {}
        }
        await self.send_command(command)

    async def register(self):
        command = {
            "command": "register",
            "data": {
                "vm_id": self.vm_id,
                "ram": self.ram,
                "cpu": self.cpu,
                "password": self.password,
                "disks": self.disks
            }
        }
        await self.send_command(command)

    async def authenticate(self):
        command = {
            "command": "authenticate",
            "data": {
                "vm_id": self.vm_id,
                "password": self.password
            }
        }
        json_data = await self.send_command(command)
        auth_token = json_data.get('data', {}).get('token')
        if auth_token:
            self.auth_token = auth_token

    async def list(self, list_type):
        command = {
            "command": "list",
            "data": {
                "token": self.auth_token,
                "list_type": list_type
            }
        }
        await self.send_command(command)

    async def update(self, ram=None, cpu=None, disks=None):
        data = {"token": self.auth_token}
        if ram is not None:
            data["ram"] = ram
        if cpu is not None:
            data["cpu"] = cpu
        if disks is not None:
            data["disks"] = disks

        command = {
            "command": "update",
            "data": data
        }
        await self.send_command(command)

    async def logout(self):
        command = {
            "command": "logout",
            "data": {"token": self.auth_token}
        }
        self.auth_token = None
        await self.send_command(command)


async def main():
    # Create the VM instance
    vm = None

    # Input for creating VM
    while vm is None:
        vm_id = input("Enter VM ID: ")
        password = input("Enter VM password: ")

        ram = int(input("Enter RAM size for VM: "))
        cpu = int(input("Enter number of CPUs for VM: "))

        disks = []
        num_disks = int(input("Enter number of disks: "))
        for i in range(num_disks):
            disk_size = int(input(f"Enter size for disk {i + 1}: "))
            disks.append({"disk_size": disk_size})

        # Create VM object
        reader, writer = await asyncio.open_connection('127.0.0.1', 8888)
        vm = VM(vm_id, password, ram, cpu, disks, reader, writer)
        print(f"VM created with ID {vm_id}.")

    # Main loop to handle commands
    while True:
        try:
            command = input(
                "\nEnter command (register, authenticate, list_active, list_authenticated, list_all, list_all_disks, update, logout, exit): \n").lower()

            if command == "register":
                await vm.register()
            elif command == "authenticate":
                await vm.authenticate()
            elif command == "list_active":
                await vm.list("active_vms")
            elif command == "list_authenticated":
                await vm.list("authenticated_vms")
            elif command == "list_all":
                await vm.list("all_vms")
            elif command == "list_all_disks":
                await vm.list("all_disks")
            elif command == "update":
                new_ram = int(input("Enter new RAM size for VM: "))
                new_cpu = int(input("Enter new number of CPUs for VM: "))
                new_disks = []
                num_new_disks = int(input("Enter number of updated disks: "))
                for i in range(num_new_disks):
                    disk_size = int(input(f"Enter new size for disk {i + 1}: "))
                    new_disks.append({"disk_size": disk_size})
                await vm.update(ram=new_ram, cpu=new_cpu, disks=new_disks)
            elif command == "logout":
                await vm.logout()
            elif command == "exit":
                print("Exiting...")
                break
            else:
                print("Unknown command. Try again.")
        except ConnectionResetError as e:
            print(e, "Trying to reconnect...")
            vm.reader, vm.writer = await asyncio.open_connection('127.0.0.1', 8888)


if __name__ == "__main__":
    asyncio.run(main())
