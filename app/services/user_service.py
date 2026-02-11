"""Сервис для операций с пользователями (удаление и т.д.)."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database.models import User, DoctorAssistant


async def delete_user_from_db(session: AsyncSession, user: User) -> bool:
    """
    Удалить пользователя из БД. Перед удалением:
    - отвязывает ассистентов (owner_id = None, role = 'owner');
    - удаляет связи DoctorAssistant, где пользователь врач или ассистент.
    После этого удаляется сам пользователь (каскадно удалятся пациенты, записи, услуги и т.д.).
    Возвращает True при успехе.
    """
    if not user or not user.id:
        return False
    user_id = user.id

    # Ассистенты этого врача: отвязать (owner_id = None, role = 'owner')
    stmt_assistants = select(User).where(User.owner_id == user_id)
    res = await session.execute(stmt_assistants)
    for u in res.scalars().all():
        u.owner_id = None
        u.role = "owner"

    # Связи врач–ассистент, где пользователь врач или ассистент
    await session.execute(delete(DoctorAssistant).where(DoctorAssistant.doctor_id == user_id))
    await session.execute(delete(DoctorAssistant).where(DoctorAssistant.assistant_id == user_id))

    session.delete(user)
    await session.commit()
    return True
