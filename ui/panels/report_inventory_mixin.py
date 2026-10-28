"""Backward-compatible aggregator for inventory and category reports."""
from ui.panels.report_inventory_tab_mixin import ReportInventoryTabMixin
from ui.panels.report_category_mixin import ReportCategoryMixin


class ReportInventoryMixin(ReportInventoryTabMixin, ReportCategoryMixin):
    """Compose inventory and category report tabs."""
