"""
simulation/pid.py — Régulateur PID avec anti-windup
Utilisé par le Controller superviseur pour la régulation de puissance active (MW → V1 target %).
"""


class PID:
    """
    PID standard avec :
      - anti-windup par clamp d'intégrale quand la sortie sature
      - transfert sans à-coup MANUAL→AUTO via seed()
    """

    def __init__(self, kp: float, ki: float, kd: float,
                 out_min: float = 0.0, out_max: float = 100.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.out_min = out_min
        self.out_max = out_max
        self._integral   = 0.0
        self._prev_error = 0.0

    def compute(self, setpoint: float, measurement: float, dt: float) -> float:
        """Calcule la sortie PID pour un tick de durée dt (s)."""
        if dt <= 0:
            return self._clamp(self.kp * (setpoint - measurement))

        error      = setpoint - measurement
        derivative = (error - self._prev_error) / dt
        self._prev_error = error

        # Intégration provisoire
        integral_candidate = self._integral + error * dt
        output = self.kp * error + self.ki * integral_candidate + self.kd * derivative

        # Anti-windup : n'intègre pas si la sortie non clampée sature
        if self.out_min <= output <= self.out_max:
            self._integral = integral_candidate

        return self._clamp(output)

    def reset(self):
        self._integral   = 0.0
        self._prev_error = 0.0

    def seed(self, integral_value: float):
        """Initialise l'intégrale pour un transfert sans à-coup lors du passage AUTO."""
        self._integral   = integral_value
        self._prev_error = 0.0

    @property
    def error(self) -> float:
        return self._prev_error

    def _clamp(self, value: float) -> float:
        return max(self.out_min, min(self.out_max, value))
