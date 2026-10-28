"""Backward-compatible aggregator for report operational tabs."""
from ui.panels.report_product_mixin import ReportProductMixin
from ui.panels.report_maintenance_mixin import ReportMaintenanceMixin


class ReportOperationsMixin(ReportProductMixin, ReportMaintenanceMixin):
    """Compose product-level, maintenance and cheque report builders."""
