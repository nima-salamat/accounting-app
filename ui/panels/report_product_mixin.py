"""Backward-compatible aggregator for product report workflows."""
from ui.panels.report_product_search_mixin import ReportProductSearchMixin
from ui.panels.report_all_products_mixin import ReportAllProductsMixin


class ReportProductMixin(ReportProductSearchMixin, ReportAllProductsMixin):
    """Compose individual-product and all-products reports."""
