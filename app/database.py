from typing import Optional

import asyncpg
import bcrypt
import logging

from schemes import AuthenticateVM
from schemes import VM
from config import DB_CONFIG

logging.basicConfig(level=logging.DEBUG)


class DbPool:
    db_pool: Optional[asyncpg.pool.Pool] = None

    @staticmethod
    async def create_pool():
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
    async def terminate_pool():
        (await DbPool.get_pool()).terminate()
        DbPool.db_pool = None
        logging.info("Pool terminated")


def hash_password(password: str) -> str:
    """Hash a password before storing it in the database."""
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode(), salt)
    return hashed_password.decode()


def verify_password(password: str, hashed_password: str) -> bool:
    """Check if the given password matches the stored hash."""
    return bcrypt.checkpw(password.encode(), hashed_password.encode())


async def create_tables(pool: asyncpg.pool.Pool):
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS virtual_machines (
                id SERIAL PRIMARY KEY,
                vm_id TEXT UNIQUE NOT NULL,
                ram INTEGER,
                cpu INTEGER,
                password TEXT NOT NULL
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS disks (
                id SERIAL PRIMARY KEY,
                disk_id TEXT UNIQUE NOT NULL,
                vm_id TEXT REFERENCES virtual_machines(vm_id),
                size INTEGER
            );
        ''')
        logging.info("Initialized database tables")


async def get_vm(pool: asyncpg.pool.Pool, vm: AuthenticateVM):
    async with pool.acquire() as conn:
        res = await conn.fetchrow(
            'SELECT vm_id, ram, cpu, password FROM virtual_machines WHERE vm_id=$1', vm.vm_id
        )
        if verify_password(vm.password, res[3]):
            return VM(vm_id=res[0], ram=res[1], cpu=res[2], password=res[3])
        else:
            return None


async def get_vms(pool: asyncpg.pool.Pool):
    async with pool.acquire() as conn:
        return await conn.fetch('SELECT vm_id, ram, cpu FROM virtual_machines')


async def create_vm(pool: asyncpg.pool.Pool, vm: VM):
    vm.password = hash_password(vm.password)
    logging.debug(f"Acquiring connection from pool {pool}")
    async with pool.acquire() as conn:
        await conn.execute(
            'INSERT INTO virtual_machines (vm_id, ram, cpu, password) VALUES ($1, $2, $3, $4)',
            vm.vm_id, vm.ram, vm.cpu, vm.password
        )
        logging.info(f"Created virtual machine {vm.vm_id}")


async def get_disks(pool: asyncpg.pool.Pool):
    pass


async def create_disk(pool: asyncpg.pool.Pool, disk_id, vm_id, size, password):
    pass
