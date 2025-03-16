import asyncpg
import bcrypt

from schemes import AuthenticateVM
from schemes import VM
from config import DB_CONFIG


def hash_password(password: str) -> str:
    """Hash a password before storing it in the database."""
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode(), salt)
    return hashed_password.decode()


def verify_password(password: str, hashed_password: str) -> bool:
    """Check if the given password matches the stored hash."""
    return bcrypt.checkpw(password.encode(), hashed_password.encode())


async def get_db_pool() -> asyncpg.pool.Pool:
    """ Gets asyncpg pool to acquire db connections """
    return await asyncpg.create_pool(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"]
    )


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


async def get_vm(pool: asyncpg.pool.Pool, vm:AuthenticateVM):
    async with pool.acquire() as conn:
        res = await conn.fetchrow(
            'SELECT vm_id, ram, cpu, password FROM virtual_machines WHERE vm_id=$1', vm.vm_id
        )
        if verify_password(vm.password, res[3]):
            return VM(vm_id=res[0], ram=res[1], cpu=res[2])
        else:
            return None


async def get_vms(pool: asyncpg.pool.Pool):
    async with pool.acquire() as conn:
        return await conn.fetch('SELECT vm_id, ram, cpu FROM virtual_machines')


async def create_vm(pool: asyncpg.pool.Pool, vm: VM):
    vm.password = hash_password(vm.password)
    async with pool.acquire() as conn:
        await conn.execute(
            'INSERT INTO virtual_machines (vm_id, ram, cpu, password) VALUES ($1, $2, $3, $4)',
            vm.vm_id, vm.ram, vm.cpu, vm.password
        )


async def get_disks(pool: asyncpg.pool.Pool):
    pass


async def create_disk(pool: asyncpg.pool.Pool, disk_id, vm_id, size, password):
    pass
