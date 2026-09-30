"""参考能量：q=g/L 的角运动 proxy，单位 s⁻²，不是焦耳或拟合能量。"""

from dataclasses import dataclass
from math import cos, isfinite

from ai_physics_tracker.domain.angular_analysis import AngularSeries, AngularAnalysis, angular_series_digest
from ai_physics_tracker.domain.types import canonical_json_digest

CORE_VERSION = "reference-energy-1.0.0"


def energy_config() -> dict[str, object]:
    return {"core_version": CORE_VERSION, "q_source": "physical_g_over_effective_com_length",
            "potential": "q*(1-cos(theta))", "kinetic": "omega**2/2",
            "unit": "s^-2", "meaning": "reference_proxy_not_fitted_energy",
            "sources": ["energy", "policy-student-v1"]}


@dataclass(frozen=True)
class ReferenceEnergy:
    q_s_inv2: float
    potential_s_inv2: tuple[float | None, ...]
    kinetic_s_inv2: tuple[float | None, ...]
    total_s_inv2: tuple[float | None, ...]
    reasons: tuple[str | None, ...]
    input_digest: str


def reference_energy(series: AngularSeries, angular: AngularAnalysis,
                     length_m: float, g_m_s2: float) -> ReferenceEnergy:
    """仅共同 QC 且选定时域内的 θ；导数缺失时势能可用、总能量缺失。"""
    if any(type(v) not in (int, float) or not isfinite(v) or v <= 0
           for v in (length_m, g_m_s2)):
        raise ValueError("reference energy requires positive finite L and g")
    q = float(g_m_s2) / float(length_m)
    if not isfinite(q) or q <= 0:
        raise ValueError("reference energy g/L must be positive finite")
    if angular.source_series_digest != angular_series_digest(series):
        raise ValueError("energy angular source series does not match")
    n = len(series.frame_indices)
    if any(len(a) != n for a in (angular.omega_rad_s, angular.omega_reasons, angular.edge_window)):
        raise ValueError("energy requires aligned angular outputs")
    if any(v is not None and (type(v) not in (int, float) or not isfinite(v))
           for v in angular.omega_rad_s):
        raise ValueError("energy omega must be finite or null")
    potential, kinetic, total, reasons = [], [], [], []
    for theta, qc, omega, reason in zip(series.theta_rad, series.qc_valid,
                                       angular.omega_rad_s, angular.omega_reasons):
        usable = qc and theta is not None and reason != "outside_interval"
        p = q*(1-cos(theta)) if usable else None
        k = omega*omega/2 if usable and omega is not None else None
        value = p+k if p is not None and k is not None else None
        if any(v is not None and not isfinite(v) for v in (p, k, value)):
            p, k, value, reason = None, None, None, "nonfinite_energy"
        potential.append(p); kinetic.append(k); total.append(value)
        reasons.append(None if value is not None else (reason or "qc_excluded"))
    digest = canonical_json_digest({"angular_input_digest": angular.input_digest,
        "omega_rad_s": list(angular.omega_rad_s), "omega_reasons": list(angular.omega_reasons),
        "length_m": float(length_m), "g_m_s2": float(g_m_s2), "config": energy_config()})
    return ReferenceEnergy(q, tuple(potential), tuple(kinetic), tuple(total), tuple(reasons), digest)
