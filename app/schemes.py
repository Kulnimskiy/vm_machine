from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator
import json


class VM(BaseModel):
    vm_id: str = Field(..., min_length=3, max_length=50, description="Unique identifier for the virtual machine")
    ram: int = Field(..., gt=0, lt=1024, description="RAM size in MB (between 1MB and 1024MB)")
    cpu: int = Field(..., gt=0, lt=32, description="Number of CPU cores (between 1 and 32)")
    password: str = Field(..., min_length=8, max_length=100, description="Password for authentication")

    @model_validator(mode="before")
    @classmethod
    def check_vm_id(cls, values):
        if " " in values["vm_id"]:
            raise ValueError("VM ID cannot contain spaces")
        return values

class AuthenticateVM(BaseModel):
    vm_id: str = Field(..., min_length=3, max_length=50, description="VM identifier")
    password: str = Field(..., min_length=8, max_length=100, description="VM authentication password")

# Update VM Schema
class UpdateVMModel(BaseModel):
    vm_id: str = Field(..., min_length=3, max_length=50, description="VM identifier to update")
    ram: Optional[int] = Field(None, gt=0, lt=1024, description="Updated RAM size in MB")
    cpu: Optional[int] = Field(None, gt=0, lt=32, description="Updated number of CPU cores")

class Request(BaseModel):
    command: Literal["ping", "register", "authenticate", "list", "update", "logout"]
    data: Optional[dict] = None

# Model for sending responses back to clients
class Response(BaseModel):
    status: Literal["success", "error"]
    message: Optional[str] = None
    data: Optional[list, dict] = None






