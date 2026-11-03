from fastapi import APIRouter
from app.core.layouts import CANVAS, TEMPLATES

router = APIRouter()


@router.get("/")
def list_layouts():
    """Return the page-layout template library for the picker UI."""
    return {"canvas": CANVAS, "templates": TEMPLATES}
