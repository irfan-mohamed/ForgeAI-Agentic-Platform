import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
raw_password = "Irfan@123"
encoded_password = urllib.parse.quote_plus(raw_password)

DATABASE_URL = f"postgresql://postgres:{encoded_password}@localhost:5432/got"

engine = create_engine(DATABASE_URL)

class Room(Base):
    __tablename__ = "rooms"

    room_id = Column(Integer, primary_key=True)


Base.metadata.create_all(engine)

localSession = sessionmaker(bind = engine)

session = localSession()

session.add(Room(room_id = 323))
session.commit()