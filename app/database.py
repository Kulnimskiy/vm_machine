from typing import Optional

import asyncpg
import bcrypt
import logging

from schemes import Disk, UpdateVM, VM
from config import DB_CONFIG

logging.basicConfig(level=logging.DEBUG)


class DbPool:
    db_pool: Optional[asyncpg.pool.Pool] = None

    @staticmethod
    async def create_pool() -> asyncpg.pool.Pool:
        pool: asyncpg.Pool = await asyncpg.create_pool(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            max_size=10
        )
        return pool

    @staticmethod
    async def get_pool() -> asyncpg.pool.Pool:
        if not DbPool.db_pool:
            DbPool.db_pool = await DbPool.create_pool()
        return DbPool.db_pool

    @staticmethod
    async def terminate_pool() -> None:
        (await DbPool.get_pool()).terminate()
        DbPool.db_pool = None
        logging.info("Pool terminated")


class PasswordHandler:
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password before storing it in the database."""
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(password.encode(), salt)
        return hashed_password.decode()

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        """Check if the given password matches the stored hash."""
        return bcrypt.checkpw(password.encode(), hashed_password.encode())


class DatabaseManager:
    """ Basic queries for managing the database"""

    @staticmethod
    async def create_tables(pool: asyncpg.pool.Pool) -> None:
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS virtual_machines (
                    id SERIAL PRIMARY KEY,
                    vm_id VARCHAR(255) UNIQUE NOT NULL, 
                    ram INTEGER,
                    cpu INTEGER,
                    password VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS disks (
                    id SERIAL PRIMARY KEY,
                    vm_id VARCHAR(255) REFERENCES virtual_machines(vm_id),
                    disk_size INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')
            logging.info("Initialized database tables")

    @staticmethod
    async def get_vm(pool: asyncpg.pool.Pool, vm_id: str) -> VM | None:
        async with pool.acquire() as conn:
            vm_db = await conn.fetchrow(
                'SELECT vm_id, ram, cpu, password FROM virtual_machines WHERE vm_id=$1', vm_id
            )
            if not vm_db:
                return None

            disks_objects = []
            disks = await conn.fetch(
                'SELECT id, disk_size FROM disks WHERE vm_id=$1', vm_id
            )
            for disk in disks:
                disks_objects.append(Disk(id=disk['id'], vm_id=vm_id, disk_size=disk["disk_size"]))

            return VM(
                vm_id=vm_db['vm_id'], ram=vm_db['ram'], cpu=vm_db['cpu'], password=vm_db['password'],
                disks=disks_objects
            )

    @staticmethod
    async def get_vms(pool: asyncpg.pool.Pool, vm_ids: list = None) -> list[VM] | None:
        async with pool.acquire() as conn:
            vms = []
            if vm_ids:
                vms_db = await conn.fetch('SELECT vm_id, ram, cpu, password FROM virtual_machines where vm_id in $1',
                                          vm_ids)
            else:
                vms_db = await conn.fetch('SELECT vm_id, ram, cpu, password FROM virtual_machines')

            for vm_db in vms_db:
                disks = await conn.fetch(
                    'SELECT id, disk_size FROM disks WHERE vm_id=$1', vm_db['vm_id']
                )
                disks_objects = []
                for disk in disks:
                    disks_objects.append(
                        Disk(id=disk['id'], vm_id=vm_db['vm_id'], disk_size=disk["disk_size"])
                    )

                vm = VM(
                    vm_id=vm_db['vm_id'], ram=vm_db['ram'],
                    cpu=vm_db['cpu'], password=vm_db['password'], disks=disks_objects
                )
                vms.append(vm)

            return vms

    @staticmethod
    async def create_vm(pool: asyncpg.pool.Pool, vm: VM):
        vm.password = PasswordHandler.hash_password(vm.password)
        async with pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO virtual_machines (vm_id, ram, cpu, password) VALUES ($1, $2, $3, $4)',
                vm.vm_id, vm.ram, vm.cpu, vm.password
            )

        for disk in vm.disks:
            disk.vm_id = vm.vm_id
            await DatabaseManager.create_disk(pool, disk)

    @staticmethod
    async def update_vm(pool: asyncpg.pool.Pool, vm_id: str, new_vm: UpdateVM) -> None:
        # Build dynamic SQL query for updating only the field with new data
        update_fields = new_vm.model_dump(exclude_none=True, exclude={'addr', 'token', 'disks'})
        if not update_fields:
            raise ValueError("No fields for update")

        set_clause = ", ".join([f"{field}=${i + 1}" for i, field in enumerate(update_fields.keys())])
        set_values = list(update_fields.values()) + [vm_id]

        query = f"UPDATE virtual_machines SET {set_clause} WHERE vm_id=${len(set_values)}"
        delete_old_disks_query = f"DELETE FROM disks WHERE vm_id=$1"
        create_new_disk_query = f"INSERT INTO disks (vm_id, disk_size) VALUES ($1, $2)"

        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(query, *set_values)
                await conn.execute(delete_old_disks_query, vm_id)
                for disk in new_vm.disks:
                    await conn.execute(create_new_disk_query, vm_id, disk.disk_size)

    @staticmethod
    async def create_disk(pool: asyncpg.pool.Pool, disk: Disk):
        async with pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO disks (vm_id, disk_size) VALUES ($1, $2)',
                disk.vm_id, disk.disk_size
            )

    @staticmethod
    async def get_disks(pool: asyncpg.pool.Pool):
        async with pool.acquire() as conn:
            disks = await conn.fetch(
                'SELECT id, vm_id, disk_size FROM disks'
            )
            disks_objects = []
            for disk in disks:
                disks_objects.append(Disk(id=disk['id'], disk_size=disk["disk_size"], vm_id=disk['vm_id']))

            return disks_objects
