"""HR manbasidagi tashkilot ↔ filial moslashtirishi (`hr.orgs`): model setting_types'da."""

from app.core.setting_types import HrOrg as HrOrg
from app.core.setting_types import hr_orgs as validate_orgs
from app.core.setting_types import normalize_org as normalize_org

__all__ = ["HrOrg", "normalize_org", "validate_orgs"]
