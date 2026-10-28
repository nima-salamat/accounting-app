"""Backward-compatible aggregator for overview and sales reports."""
from ui.panels.report_summary_mixin import ReportSummaryMixin
from ui.panels.report_sales_mixins import ReportSalesMixin


class ReportOverviewMixin(ReportSummaryMixin, ReportSalesMixin):
    """Compose the overview and sales report tabs."""
