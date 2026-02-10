from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Integer, Float, Date, DateTime, ForeignKey, Text, JSON, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """Модель врача или ассистента (пользователя)"""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    specialization: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    location_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    photo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    subscription_tier: Mapped[int] = mapped_column(Integer, default=0)  # 0=Basic, 1=Standard, 2=Premium
    subscription_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Роль: owner — владелец (врач), assistant — ассистент привязан к врачу
    role: Mapped[str] = mapped_column(String(20), default="owner")
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Relationships (owner/assistant)
    owner: Mapped[Optional["User"]] = relationship("User", remote_side="User.id", back_populates="assistants", foreign_keys=[owner_id])
    assistants: Mapped[list["User"]] = relationship("User", back_populates="owner", foreign_keys=[owner_id])
    doctor_assistant_links: Mapped[list["DoctorAssistant"]] = relationship("DoctorAssistant", back_populates="doctor", foreign_keys="DoctorAssistant.doctor_id")
    assistant_link: Mapped[Optional["DoctorAssistant"]] = relationship("DoctorAssistant", back_populates="assistant_user", foreign_keys="DoctorAssistant.assistant_id", uselist=False)
    invite_codes: Mapped[list["InviteCode"]] = relationship("InviteCode", back_populates="doctor", cascade="all, delete-orphan")
    clinic_locations: Mapped[list["ClinicLocation"]] = relationship(back_populates="doctor", cascade="all, delete-orphan")
    patients: Mapped[list["Patient"]] = relationship(back_populates="doctor", cascade="all, delete-orphan")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="doctor", cascade="all, delete-orphan")
    services: Mapped[list["Service"]] = relationship(back_populates="doctor", cascade="all, delete-orphan")
    treatments: Mapped[list["Treatment"]] = relationship(back_populates="doctor", cascade="all, delete-orphan")
    implant_logs: Mapped[list["ImplantLog"]] = relationship(back_populates="doctor", cascade="all, delete-orphan")


class DoctorAssistant(Base):
    """Связь врач — ассистент с настраиваемыми правами.
    permissions: dict вида {"calendar": "edit", "patients": "view", ...}
    Уровни: "none" | "view" | "edit"
    """
    __tablename__ = "doctor_assistant"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    assistant_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    permissions: Mapped[dict] = mapped_column(JSON, nullable=False)
    invite_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    doctor: Mapped["User"] = relationship("User", back_populates="doctor_assistant_links", foreign_keys=[doctor_id])
    assistant_user: Mapped["User"] = relationship("User", back_populates="doctor_assistant_links", foreign_keys=[assistant_id])


class InviteCode(Base):
    """Временный код приглашения ассистента (врач создаёт, ассистент вводит)."""
    __tablename__ = "invite_codes"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(12), unique=True)
    permissions: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    doctor: Mapped["User"] = relationship("User", back_populates="invite_codes")


class ClinicLocation(Base):
    """Модель локации клиники (мульти-локации)"""
    __tablename__ = "clinic_locations"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    location_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    emoji: Mapped[str] = mapped_column(String(10), default="🏥")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Relationships
    doctor: Mapped["User"] = relationship(back_populates="clinic_locations")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="location", cascade="all, delete-orphan")


class Patient(Base):
    """Модель пациента (Standard+)"""
    __tablename__ = "patients"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    doctor: Mapped["User"] = relationship(back_populates="patients")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="patient", cascade="all, delete-orphan")
    treatments: Mapped[list["Treatment"]] = relationship(back_populates="patient", cascade="all, delete-orphan")
    implant_logs: Mapped[list["ImplantLog"]] = relationship(back_populates="patient", cascade="all, delete-orphan")


class Appointment(Base):
    """Модель записи на прием"""
    __tablename__ = "appointments"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    patient_id: Mapped[Optional[int]] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=True)  # nullable для Basic
    service_id: Mapped[Optional[int]] = mapped_column(ForeignKey("services.id", ondelete="SET NULL"), nullable=True)
    location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clinic_locations.id", ondelete="SET NULL"), nullable=True)
    date_time: Mapped[datetime] = mapped_column(DateTime)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)  # длительность приёма
    service_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned, completed, cancelled
    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # когда отправлено напоминание
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Relationships
    doctor: Mapped["User"] = relationship(back_populates="appointments")
    patient: Mapped[Optional["Patient"]] = relationship(back_populates="appointments")
    service: Mapped[Optional["Service"]] = relationship(back_populates="appointments")
    location: Mapped[Optional["ClinicLocation"]] = relationship(back_populates="appointments")
    treatments: Mapped[list["Treatment"]] = relationship(back_populates="appointment", cascade="all, delete-orphan")


class Treatment(Base):
    """Модель лечения (Premium)"""
    __tablename__ = "treatments"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    appointment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True)
    tooth_number: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    diagnosis: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    treatment_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    service_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discount_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discount_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    paid_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # cash, card, transfer
    payment_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # full, partial, debt
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Relationships
    patient: Mapped["Patient"] = relationship(back_populates="treatments")
    doctor: Mapped["User"] = relationship(back_populates="treatments")
    appointment: Mapped[Optional["Appointment"]] = relationship(back_populates="treatments")


class Service(Base):
    """Модель услуги (прайс-лист по категориям)"""
    __tablename__ = "services"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(50))  # therapy, orthopedics, surgery, orthodontics, endodontics
    name: Mapped[str] = mapped_column(String(255))
    price: Mapped[float] = mapped_column(Float)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)  # длительность в минутах
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    doctor: Mapped["User"] = relationship(back_populates="services")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="service")


class ImplantLog(Base):
    """Модель имплантологической карты (Standard+)"""
    __tablename__ = "implant_logs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))  # обязательный
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))  # для безопасности
    tooth_number: Mapped[str] = mapped_column(String(10))  # например "36", "11"
    system_name: Mapped[str] = mapped_column(String(255))  # название системы
    implant_size: Mapped[str] = mapped_column(String(50))  # например "4.0 x 10.0"
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # доп. заметки
    operation_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Relationships
    patient: Mapped["Patient"] = relationship(back_populates="implant_logs")
    doctor: Mapped["User"] = relationship(back_populates="implant_logs")

