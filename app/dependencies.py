from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.i18n import current_language, language_url, translate, translations

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["_"] = translate
templates.env.globals["current_language"] = current_language
templates.env.globals["language_url"] = language_url
templates.env.globals["translations"] = translations
