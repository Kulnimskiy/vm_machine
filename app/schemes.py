from typing import Literal, Optional, List, Tuple
from pydantic import BaseModel, Field, model_validator


class Request(BaseModel):
    command: Literal["ping", "register", "authenticate", "list", "update", "logout"]
    data: Optional[dict] = dict()


class Response(BaseModel):
    status: Literal["success", "error"]
    message: Optional[str] = None
    data: Optional[dict] = dict()


class Disk(BaseModel):
    id: Optional[int] = Field(None, min_length=3, max_length=50, description="Unique identifier for the disk")
    vm_id: Optional[str] = Field(None, min_length=3, max_length=50, description="Unique identifier for the vm")
    disk_size: int = Field(..., gt=0, description="Disk size in GB (greater than 0)")


class VM(BaseModel):
    vm_id: str = Field(..., description="Unique identifier for the virtual machine")
    ram: int = Field(..., gt=0, lt=2049, description="RAM size in MB (between 1MB and 2048MB)")
    cpu: int = Field(..., gt=0, lt=32, description="Number of CPU cores (between 1 and 32)")
    password: str = Field(..., min_length=8, max_length=100, description="Password for authentication")
    disks: List[Disk] = Field(..., description="List of disks associated with the VM")

    @model_validator(mode="before")
    @classmethod
    def check_vm_id(cls, values):
        if " " in values["vm_id"]:
            raise ValueError("VM ID cannot contain spaces")
        return values


class AuthenticateVM(BaseModel):
    vm_id: str = Field(..., description="VM identifier (integer, greater than 0)")
    password: str = Field(..., min_length=8, max_length=100, description="VM authentication password")
    addr: Optional[Tuple[str, int]] = None  # IP address and port as a tuple


class ListVM(BaseModel):
    addr: Optional[Tuple[str, int]] = None
    list_type: Literal["active_vms", "authenticated_vms", "all_vms", "all_disks"]


class UpdateVM(BaseModel):
    addr: Optional[Tuple[str, int]] = None
    ram: Optional[int] = Field(None, gt=0, lt=1024, description="Updated RAM size in MB")
    cpu: Optional[int] = Field(None, gt=0, lt=32, description="Updated number of CPU cores")
    disks: Optional[List[Disk]] = Field(None, description="List of disks associated with the VM")


class Logout(BaseModel):
    addr: Optional[Tuple[str, int]]
