"""«Требует внимания» (TZ 4): qoidalar reyestri. Evaluator modullari shu yerda import qilinadi —
keyingi bo'lim rejalari o'z modulini qo'shadi (masalan, `from app.alerts import kredity`)."""

from app.alerts import hr, investment, procurement, treasury  # noqa: F401
