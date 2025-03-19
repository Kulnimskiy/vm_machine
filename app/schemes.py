from typing import Literal, Optional, List, Tuple
from pydantic import BaseModel, Field, model_validator


class Request(BaseModel):
    """ Main scheme for client's requests validation """
    command: Literal["ping", "register", "authenticate", "list", "update", "logout"]
    data: Optional[dict] = dict()


class Response(BaseModel):
    """ Main scheme for server's responses to clients """
    status: Literal["success", "error"]
    message: Optional[str] = None
    data: Optional[dict] = dict()


class Disk(BaseModel):
    """ Scheme for creating and returning virtual machine disks """
    id: Optional[int] = Field(None, gt=0, description="Unique identifier for the disk")
    vm_id: Optional[str] = Field(None, max_length=50, description="Unique identifier for the vm")
    disk_size: int = Field(..., gt=0, description="Disk size in GB (greater than 0)")


class VM(BaseModel):
    """ Main virtual machine data validation scheme """
    vm_id: str = Field(..., description="Unique identifier for the virtual machine")
    ram: int = Field(..., gt=0, lt=32000, description="RAM size in MB (between 1MB and 2048MB)")
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
    """ Scheme to receive user authentication data"""
    vm_id: str = Field(..., description="VM identifier (integer, greater than 0)")
    password: str = Field(..., min_length=8, max_length=100, description="VM authentication password")
    addr: Optional[Tuple[str, int]] = None  # IP address and port as a tuple


class ListVM(BaseModel):
    """ Scheme for the list command data validation. Needs the access token to let the command be run """
    token: str
    addr: Optional[Tuple[str, int]] = None
    list_type: Literal["active_vms", "authenticated_vms", "all_vms", "all_disks"]


class UpdateVM(BaseModel):
    """ Scheme for the update command data validation. Needs the access token to let the command be run """
    token: str
    addr: Optional[Tuple[str, int]] = None
    ram: Optional[int] = Field(None, gt=0, description="Updated RAM size in MB")
    cpu: Optional[int] = Field(None, gt=0, lt=32, description="Updated number of CPU cores")
    disks: Optional[List[Disk]] = Field(None, description="List of disks associated with the VM")


class Logout(BaseModel):
    """ Scheme for the logout command data validation. Needs the access token to let the command be run """
    token: str
    addr: Optional[Tuple[str, int]]
