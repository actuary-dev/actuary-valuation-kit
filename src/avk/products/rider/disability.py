"""TPD composition reuses CI's generic claimant components and transition timing."""

from avk.products.rider.critical_illness import CriticalIllness, IfrsCriticalIllness


class Disability(CriticalIllness):
    """Disability incidence is selected by DisabilityFactory before compilation."""

    CODE, LABEL = "DISABILITY_RIDER", "Total and permanent disability rider"


class IfrsDisability(IfrsCriticalIllness, Disability):
    """Disability plus the same claimant and IFRS measurement components."""
