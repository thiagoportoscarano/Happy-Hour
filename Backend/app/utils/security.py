from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha[:72])

def verificar_senha(senha: str, hash_da_senha: str) -> bool:
    return pwd_context.verify(senha[:72], hash_da_senha)
