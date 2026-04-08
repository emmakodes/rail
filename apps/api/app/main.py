from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import settings
from app.db import engine, get_db
from app.models import Base, Todo
from app.schemas import TodoCreate, TodoRead

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/todos", response_model=list[TodoRead])
def list_todos(db: Session = Depends(get_db)) -> list[Todo]:
    return db.query(Todo).order_by(Todo.id.desc()).all()


@app.post("/todos", response_model=TodoRead, status_code=status.HTTP_201_CREATED)
def create_todo(payload: TodoCreate, db: Session = Depends(get_db)) -> Todo:
    todo = Todo(title=payload.title.strip())
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo
