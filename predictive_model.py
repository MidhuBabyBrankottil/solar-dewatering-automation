"""
predictive_model.py
===================
Hydrological runoff prediction and predictive inflow management for mine sumps.
Uses weather forecasts and catchment topography to pre-emptively calculate
water arrival and compute dynamic pumping thresholds.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class CatchmentParameters:
    area_m2: float = 120_000.0         # 120,000 m^2 open pit catchment area
    runoff_coefficient: float = 0.65    # Hard rock mining face runoff coefficient (0.6 - 0.8)
    base_groundwater_inflow_m3_h: float = 15.0  # Constant aquifer seepage rate
    sump_capacity_m3: float = 4_500.0   # Sump volumetric capacity
    sump_depth_m: float = 6.0           # Sump maximum depth

class PredictiveInflowEngine:
    def __init__(self, params: CatchmentParameters = None):
        self.params = params or CatchmentParameters()

    def estimate_runoff_inflow(self, rain_intensity_mm_h: float) -> float:
        """
        Calculates instantaneous storm water inflow rate using Rational Formula:
        Q = C * I * A (converted to m^3 / hour)
        """
        # rain intensity mm/h = 10^-3 m/h
        rain_volume_m3_h = (rain_intensity_mm_h / 1000.0) * self.params.area_m2
        surface_runoff = self.params.runoff_coefficient * rain_volume_m3_h
        total_inflow = surface_runoff + self.params.base_groundwater_inflow_m3_h
        return total_inflow

    def forecast_inflow_horizon(self, rain_forecast_mm_h: List[float], time_step_hours: float = 1.0) -> np.ndarray:
        """
        Generates a forward-looking hydrograph of anticipated mine inflow
        incorporating soil saturation delay (unit hydrograph dispersion).
        """
        horizon_steps = len(rain_forecast_mm_h)
        inflows = np.zeros(horizon_steps)
        
        # Unit hydrograph convolution weights for runoff lag (delay due to pit geometry)
        lag_weights = np.array([0.45, 0.35, 0.15, 0.05])
        
        for t in range(horizon_steps):
            raw_inflow = self.estimate_runoff_inflow(rain_forecast_mm_h[t])
            # Distribute across current and future steps based on lag
            for l, w in enumerate(lag_weights):
                if t + l < horizon_steps:
                    inflows[t + l] += (raw_inflow - self.params.base_groundwater_inflow_m3_h) * w
            inflows[t] += self.params.base_groundwater_inflow_m3_h
            
        return inflows

    def compute_dynamic_threshold(self, current_level_m: float, forecasted_inflows_m3_h: np.ndarray,
                                   solar_irradiance_wm2: float) -> Tuple[float, str]:
        """
        Determines whether pre-emptive draw-down is required before storm arrival.
        
        Returns:
            (target_pump_speed_pct, recommendation_reason)
        """
        # Convert depth to volume: V = Area_surface * Depth
        area_equiv = self.params.sump_capacity_m3 / self.params.sump_depth_m
        current_volume = current_level_m * area_equiv
        available_headroom_m3 = self.params.sump_capacity_m3 - current_volume

        # Expected 6-hour cumulative storm surge volume
        surge_window = forecasted_inflows_m3_h[:6] if len(forecasted_inflows_m3_h) >= 6 else forecasted_inflows_m3_h
        total_incoming_volume_m3 = np.sum(surge_window)

        # PREDICTIVE TRIGGER: If upcoming surge exceeds 75% of available headroom
        if total_incoming_volume_m3 > 0.75 * available_headroom_m3:
            if solar_irradiance_wm2 > 250.0:
                # Solar available: aggressively pre-drain now to create buffer
                return 100.0, "PREEMPTIVE_SOLAR_DRAINAGE (Imminent storm surge detected)"
            else:
                return 75.0, "PREDICTIVE_BUFFER_PREPARATION (Moderate draw-down)"

        if current_level_m > 3.8:
            return 80.0, "ELEVATED_SUMP_LEVEL (Standard draw-down)"
        elif current_level_m > 2.5 and solar_irradiance_wm2 > 200.0:
            return 45.0, "OPPORTUNISTIC_SOLAR_PUMPING (Utilizing free midday solar PV)"
        
        return 0.0, "NORMAL_STANDBY (Headroom safe, minimal inflow)"

if __name__ == "__main__":
    engine = PredictiveInflowEngine()
    # Simulated 12-hour rain forecast: intense storm peaking at hour 3
    sample_rain = [0.0, 5.0, 22.0, 38.0, 15.0, 4.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    forecast = engine.forecast_inflow_horizon(sample_rain)
    print("Forecasted Inflow Hydrograph (m^3/h):", np.round(forecast, 1))
    
    speed, reason = engine.compute_dynamic_threshold(current_level_m=3.0,
                                                     forecasted_inflows_m3_h=forecast,
                                                     solar_irradiance_wm2=650.0)
    print(f"Action: Pump Speed = {speed}% | Reason: {reason}")
