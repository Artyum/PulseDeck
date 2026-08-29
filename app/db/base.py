from sqlalchemy import BigInteger, Integer
from sqlalchemy.orm import DeclarativeBase

BigInt = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass
