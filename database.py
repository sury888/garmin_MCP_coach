from datetime import date

from sqlalchemy import create_engine, Column, Integer, Float, String, Date
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = "sqlite:///garmin_coach.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


class DailyHealth(Base):
    __tablename__ = "daily_health"

    date = Column(Date, primary_key=True)

    resting_hr = Column(Integer)
    hrv = Column(Float)

    respiration_avg = Column(Float)
    respiration_min = Column(Float)
    respiration_max = Column(Float)

    sleep_hours = Column(Float)
    sleep_score = Column(Float)

    body_battery = Column(Integer)
    stress = Column(Float)

    training_readiness = Column(Float)
    training_readiness_level = Column(String)

    acute_load = Column(Float)
    chronic_load = Column(Float)
    acwr = Column(Float)

    training_status = Column(String)


def initialize_database():
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()

def save_daily_health(data):
    session = get_session()

    try:
        existing = session.query(DailyHealth).filter_by(
            date=data["date"]
        ).first()

        if existing:
            for key, value in data.items():
                if key != "date":
                    setattr(existing, key, value)

        else:
            health = DailyHealth(**data)
            session.add(health)

        session.commit()

    finally:
        session.close()