import asyncio
import json

VM_ID = "vm_123"  # Уникальный идентификатор ВМ


async def send_command(command):
    reader, writer = await asyncio.open_connection('127.0.0.1', 8888)

    writer.write(json.dumps(command).encode())
    await writer.drain()

    data = await reader.read(1024)
    print(f"Server response: {data.decode()}")

    writer.close()
    await writer.wait_closed()


async def main():
    # Аутентификация
    register_command = {"command": "register", "data": {"vm_id": "vm_123", "ram": "800", "cpu": "4", "password": "password"}}
    register_command2 = {"command": "register", "data": {"vm_id": "vm_1234", "ram": "800", "cpu": "4", "password": "password"}}
    auth_command2 = {"command": "authenticate", "data": {"vm_id": "vm_1234", "password": "password"}}
    list_active = {"command": "list", "data": {"type": "active"}}
    list_authenticated = {"command": "list", "data": {"type": "authenticated"}}
    list_all = {"command": "list", "data": {"type": "all"}}
    list_active = {"command": "list", "data": {"type": "active"}}
    auth_command = {
        "command": "auth",
        "vm_id": VM_ID,
        "params": {
            "ram": "8GB",
            "cpu": "4",
            "disks": [{"id": "disk_1", "size": "100GB"}]
        }
    }
    await send_command(auth_command)

    # Запрос списка подключенных ВМ
    await send_command({"command": "list_connected"})


if __name__ == "__main__":
    asyncio.run(main())
