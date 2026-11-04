"""
Standalone character library — create/list characters without a project.
Backed by a hidden 'library' project so all existing generation code keeps working.
"""
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks, UploadFile, File, Form
from sqlmodel import Session, select
from app.core.database import get_session
from app.models.models import Project, Character, Task

router = APIRouter()

LIBRARY_TITLE = "__character_library__"


def _char_data(name, style, desc):
    return {
        "type": "character_sheet",
        "name": name,
        "meta_info": {"language": "en-US", "role": "", "personality": "",
                      "age": "", "style": style},
        "design_panels": [{"view": "Reference", "description": desc}],
    }


def get_or_create_library(session: Session) -> Project:
    proj = session.exec(select(Project).where(Project.title == LIBRARY_TITLE)).first()
    if not proj:
        proj = Project(title=LIBRARY_TITLE, description="Standalone character library",
                       color_mode="color", aspect_ratio="2:3", resolution="1K")
        session.add(proj); session.commit(); session.refresh(proj)
    return proj


@router.get("/characters")
def list_library_characters(session: Session = Depends(get_session)):
    lib = get_or_create_library(session)
    return session.exec(select(Character).where(Character.project_id == lib.id)).all()


@router.post("/characters")
def create_library_character(
    background_tasks: BackgroundTasks,
    payload: dict = Body(...),
    session: Session = Depends(get_session),
):
    lib = get_or_create_library(session)
    name = (payload.get("name") or "Character").strip()
    desc = (payload.get("description") or "").strip()
    style = (payload.get("style") or "Modern anime/manga style").strip()
    char = Character(project_id=lib.id, name=name, data=_char_data(name, style, desc))
    session.add(char); session.commit(); session.refresh(char)

    # generate the image from text (FLUX.1 Kontext) in the background
    from app.routers.generation import generate_character_from_text_task
    task = Task(type="image_generation", status="pending", project_id=lib.id,
                name=f"Text→{name}", description="Library character from text")
    session.add(task); session.commit(); session.refresh(task)
    background_tasks.add_task(generate_character_from_text_task, task.id, char.id)
    return {"character_id": char.id, "task_id": task.id}


@router.post("/characters/from-photo")
async def create_library_character_from_photo(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form("Character"),
    style: str = Form("Modern anime/manga style"),
    description: str = Form(""),
    engine: str = Form("flux"),
    session: Session = Depends(get_session),
):
    lib = get_or_create_library(session)
    engine = "nano" if str(engine).lower() == "nano" else "flux"
    char = Character(project_id=lib.id, name=name.strip() or "Character",
                     data=_char_data(name.strip() or "Character", style.strip(), description.strip()))
    session.add(char); session.commit(); session.refresh(char)

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    up_dir = os.path.join(base_dir, "static", lib.id, "uploads")
    os.makedirs(up_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(status_code=400, detail="Unsupported image type")
    photo_path = os.path.join(up_dir, f"src_{char.id}_{uuid.uuid4().hex[:8]}{ext}")
    with open(photo_path, "wb") as f:
        f.write(await file.read())

    from app.routers.generation import generate_character_from_photo_task
    task = Task(type="image_generation", status="pending", project_id=lib.id,
                name=f"Photo→{char.name} ({engine})", description="Library character from photo")
    session.add(task); session.commit(); session.refresh(task)
    background_tasks.add_task(generate_character_from_photo_task, task.id, char.id, photo_path, engine)
    return {"character_id": char.id, "task_id": task.id}


@router.delete("/characters/{char_id}")
def delete_library_character(char_id: int, session: Session = Depends(get_session)):
    c = session.get(Character, char_id)
    if c:
        session.delete(c); session.commit()
    return {"ok": True}
