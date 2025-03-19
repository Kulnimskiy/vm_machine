import jwt
import datetime
from config import SECRET_KEY

class Token:
    @staticmethod
    def generate_token(vm_id):
        payload = {
            "vm_id": vm_id,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)  # Token expiration
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        return token

    @staticmethod
    def decode_token(token):
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

    @staticmethod
    def get_vm_id(token):
        payload = Token.decode_token(token)
        return payload["vm_id"]