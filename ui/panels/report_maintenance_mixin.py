"""Backward-compatible aggregator for purge and cheque reports."""
from ui.panels.report_purge_mixin import ReportPurgeMixin
from ui.panels.report_cheque_mixin import ReportChequeMixin


class ReportMaintenanceMixin(ReportPurgeMixin, ReportChequeMixin):
    """Compose maintenance and cheque report tabs."""
