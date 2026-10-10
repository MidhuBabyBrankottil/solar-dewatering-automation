"""
power_manager.py
================
Tri-Source Hybrid Power Arbitrage Optimizer:
Manages Solar PV, LiFePO4 Battery Storage, and Diesel Genset backup.
Minimizes diesel fuel consumption and operational costs while guaranteeing
pumping power demand is met.
"""

from dataclasses import dataclass

@dataclass
class PowerSystemSpec:
    solar_pv_kw: float = 75.0           # 75 kW Solar Photovoltaic Array
    battery_capacity_kwh: float = 120.0 # 120 kWh LiFePO4 Battery Bank
    battery_min_soc: float = 0.20       # 20% minimum depth-of-discharge limit
    battery_charge_efficiency: float = 0.92
    pump_max_power_kw: float = 45.0     # 45 kW heavy-duty submersible slurry pump
    diesel_genset_capacity_kw: float = 60.0
    diesel_fuel_burn_l_per_kwh: float = 0.28  # 0.28 liters diesel per kWh generated

class PowerArbitrageManager:
    def __init__(self, spec: PowerSystemSpec = None):
        self.spec = spec or PowerSystemSpec()
        self.battery_kwh = self.spec.battery_capacity_kwh * 0.85 # Start at 85% SoC
        self.total_diesel_liters_used = 0.0
        self.total_solar_kwh_used = 0.0

    @property
    def battery_soc(self) -> float:
        return self.battery_kwh / self.spec.battery_capacity_kwh

    def calculate_pump_power_demand(self, pump_speed_pct: float) -> float:
        """
        Pump power follows affinity laws (cubic curve with VFD):
        P = P_max * (speed / 100)^3
        """
        if pump_speed_pct <= 0:
            return 0.0
        ratio = max(0.2, pump_speed_pct / 100.0) # VFD minimum speed 20%
        return self.spec.pump_max_power_kw * (ratio ** 3)

    def dispatch_power(self, pump_speed_pct: float, solar_irradiance_wm2: float,
                       time_step_h: float = 1.0) -> dict:
        """
        Dispatches power among Solar, Battery, and Diesel to meet pump demand.
        """
        power_demand_kw = self.calculate_pump_power_demand(pump_speed_pct)
        
        # 1. Available Solar Generation
        # Standard irradiance 1000 W/m^2 yields rated solar_pv_kw
        solar_gen_kw = (solar_irradiance_wm2 / 1000.0) * self.spec.solar_pv_kw
        solar_gen_kw = max(0.0, min(self.spec.solar_pv_kw, solar_gen_kw))

        solar_to_pump = 0.0
        battery_to_pump = 0.0
        diesel_to_pump = 0.0
        solar_to_battery = 0.0
        diesel_active = False

        # --- ARBITRAGE STEP 1: Direct Solar Usage ---
        if solar_gen_kw >= power_demand_kw:
            solar_to_pump = power_demand_kw
            surplus_solar = solar_gen_kw - power_demand_kw
            # Charge battery with surplus solar
            available_battery_room = self.spec.battery_capacity_kwh - self.battery_kwh
            charge_kwh = min(surplus_solar * time_step_h * self.spec.battery_charge_efficiency, available_battery_room)
            self.battery_kwh += charge_kwh
            solar_to_battery = charge_kwh / time_step_h
        else:
            solar_to_pump = solar_gen_kw
            deficit_kw = power_demand_kw - solar_to_pump

            # --- ARBITRAGE STEP 2: Battery Assist ---
            usable_battery_kwh = max(0.0, self.battery_kwh - (self.spec.battery_capacity_kwh * self.spec.battery_min_soc))
            max_battery_draw_kw = usable_battery_kwh / time_step_h

            if max_battery_draw_kw >= deficit_kw:
                battery_to_pump = deficit_kw
                self.battery_kwh -= deficit_kw * time_step_h
            else:
                # Deplete available battery
                battery_to_pump = max_battery_draw_kw
                self.battery_kwh -= usable_battery_kwh
                remaining_deficit_kw = deficit_kw - battery_to_pump

                # --- ARBITRAGE STEP 3: Diesel Genset Fallback ---
                diesel_to_pump = remaining_deficit_kw
                diesel_active = True
                fuel_burned_liters = (diesel_to_pump * time_step_h) * self.spec.diesel_fuel_burn_l_per_kwh
                self.total_diesel_liters_used += fuel_burned_liters

        self.total_solar_kwh_used += (solar_to_pump * time_step_h)

        return {
            "power_demand_kw": power_demand_kw,
            "solar_gen_kw": solar_gen_kw,
            "solar_to_pump_kw": solar_to_pump,
            "battery_to_pump_kw": battery_to_pump,
            "diesel_to_pump_kw": diesel_to_pump,
            "battery_soc_pct": self.battery_soc * 100.0,
            "diesel_active": diesel_active,
            "cumulative_diesel_liters": self.total_diesel_liters_used,
            "cumulative_solar_kwh": self.total_solar_kwh_used
        }

if __name__ == "__main__":
    mgr = PowerArbitrageManager()
    status = mgr.dispatch_power(pump_speed_pct=85.0, solar_irradiance_wm2=700.0)
    print("Power Dispatch Status:")
    for k, v in status.items():
        print(f"  {k}: {round(v, 2) if isinstance(v, float) else v}")
