"""Compatibility facade for CORVAX ORM models.

Models are split by business domain to keep each module reviewable and reduce merge risk.
Existing imports from ``app.models.entities`` remain supported.
"""

from app.models.core import *  # noqa: F401,F403
from app.models.finance import *  # noqa: F401,F403
from app.models.audit_banking import *  # noqa: F401,F403
from app.models.supply_chain import *  # noqa: F401,F403
from app.models.cip_projects import *  # noqa: F401,F403  # H13
from app.models.sales_commissions import *  # noqa: F401,F403  # H11
from app.models.new_departments import *  # noqa: F401,F403  # H10
from app.models.inbound_shipment import *  # noqa: F401,F403  # H9
from app.models.revenue_leases import *  # noqa: F401,F403
from app.models.manufacturing_quality import *  # noqa: F401,F403
from app.models.assets_close import *  # noqa: F401,F403
from app.models.hr_pos import *  # noqa: F401,F403
from app.models.operations_compliance import *  # noqa: F401,F403
from app.models.consolidation import *  # noqa: F401,F403
from app.models.governance_enterprise import *  # noqa: F401,F403
from app.models.qms_food_access import *  # noqa: F401,F403
from app.models.advanced_finance import *  # noqa: F401,F403
from app.models.financial_close import *  # noqa: F401,F403
from app.models.advanced_manufacturing import *  # noqa: F401,F403

from app.models.lease_advanced import *  # noqa: F401,F403
from app.models.hr_payroll_advanced import *  # noqa: F401,F403

from app.models.restaurant_pos_advanced import *  # noqa: F401,F403

from app.models.gym_operations_advanced import *  # noqa: F401,F403

from app.models.gym_commercial_activities import *  # noqa: F401,F403

from app.models.ar_ap_allocation import *  # noqa: F401,F403

from app.models.tax_compliance import *  # noqa: F401,F403

from app.models.credit_notes import *  # noqa: F401,F403

from app.models.withholding_tax import *  # noqa: F401,F403

from app.models.excise_tax import *  # noqa: F401,F403

from app.models.zakat_income_tax import *  # noqa: F401,F403

from app.models.internal_completion import *  # noqa: F401,F403
from app.models.external_integrations import *  # noqa: F401,F403
