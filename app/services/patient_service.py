from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database.models import Patient


async def search_patients(
    db_session: AsyncSession,
    doctor_id: int,
    query: str
) -> List[Patient]:
    """Умный поиск пациентов по ФИО или телефону"""
    from sqlalchemy import or_
    search_pattern = f"%{query}%"
    
    stmt = select(Patient).where(
        and_(
            Patient.doctor_id == doctor_id,
            or_(
                Patient.full_name.ilike(search_pattern),
                Patient.phone.ilike(search_pattern)
            )
        )
    ).order_by(Patient.full_name)
    
    result = await db_session.execute(stmt)
    return list(result.scalars().all())


async def get_patient_by_id(
    db_session: AsyncSession,
    patient_id: int,
    doctor_id: int
) -> Optional[Patient]:
    """Получить пациента по ID с проверкой принадлежности врачу"""
    stmt = select(Patient).where(
        and_(
            Patient.id == patient_id,
            Patient.doctor_id == doctor_id
        )
    )
    
    result = await db_session.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_patients(
    db_session: AsyncSession,
    doctor_id: int,
    limit: int = 50
) -> List[Patient]:
    """Получить всех пациентов врача"""
    stmt = select(Patient).where(
        Patient.doctor_id == doctor_id
    ).order_by(Patient.created_at.desc()).limit(limit)
    
    result = await db_session.execute(stmt)
    return list(result.scalars().all())

