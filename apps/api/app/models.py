from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    tags: Mapped[list["TodoTag"]] = relationship(
        back_populates="todo",
        cascade="all, delete-orphan",
    )


class TodoTag(Base):
    __tablename__ = "todo_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    todo_id: Mapped[int] = mapped_column(ForeignKey("todos.id"), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)

    todo: Mapped[Todo] = relationship(back_populates="tags")
