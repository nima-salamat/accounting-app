"""Backward-compatible aggregator for report analytics tabs."""
from ui.panels.report_overview_mixin import ReportOverviewMixin
from ui.panels.report_inventory_mixin import ReportInventoryMixin


class ReportAnalyticsMixin(ReportOverviewMixin, ReportInventoryMixin):
    """Compose summary, trend, sales, inventory and category report builders."""
