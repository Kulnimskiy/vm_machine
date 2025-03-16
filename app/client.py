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