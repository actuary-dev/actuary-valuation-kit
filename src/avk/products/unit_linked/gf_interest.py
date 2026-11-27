"""The general fund's monthly interest rate on each unit-linked basis."""

from avk.model.lang import Component, by_basis, scen


class GeneralFundInterest(Component):
    """The valuation rate (VROI) on the reserving basis, the expected return on investments
    (ROI) on best estimate and the risk-free reference forward rate on the market-consistent
    basis."""

    interest_rate = by_basis(reserving=scen("vroi"), be=scen("roi"), mc=scen("reference_forward"))
