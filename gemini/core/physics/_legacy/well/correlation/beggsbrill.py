"""Beggs–Brill two-phase pressure drop correlation.

Dukler Flanigan, ref Shoham p 59.
"""

import math


class BeggsBrill:
    """Calculate two-phase dp using Beggs–Brill correlation (per Shoham, p.59)."""

    @staticmethod
    def calculate_dp(us_g, us_l, rho_g, rho_l, theta, eta_g, eta_l, sigma, d_tube, eps_g, l_cel):
        """Calculate the pressure drop due friction and gravity based on various parameters.

        Parameters
        ----------
        us_g: float
            superficial gas flow velocity (m/s)
        us_l: float
            superficial liquid flow velocity (m/s)
        rho_g: float
            gas density (kg/m3)
        rho_l: float
            liquid density (kg/m3)
        theta: float
            Inclination of 1 cell (rad)
        eta_g: float
            gas viscosity (Pa s)
        eta_l: float
            liquid vicosity (Pa s)
        sigma: float
            surface tension (N/m)
        d_tube: float
            well diamater of 1 cell (m)
        eps_g: float
            roughness of 1 cell (m)
        l_cel: float
            length of 1 cell (m)

        Returns
        --------
        dp_fric: float
            pressure drop due to friction (Pa)
        dp_grav: float
            pressure drop due to gravity (Pa)
        """
        # Conversion input parameters
        us_g = us_g / 3.048e-1  # m/s -> ft/s
        us_l = us_l / 3.048e-1  # m/s -> ft/s
        rho_g = rho_g / 1.601846e1  # kg/m3 -> lbm/ft3
        rho_l = rho_l / 1.601846e1  # kg/m3 -> lbm/ft3
        eta_g = eta_g / 1e-3  # Pa s -> cp
        eta_l = eta_l / 1e-3  # Pa s -> cp
        sigma = sigma / 1e-3  # N/m -> dyne/cm
        d_tube = d_tube / 3.048e-1  # m -> ft
        eps_g = eps_g / 3.048e-1  # m -> ft
        l_cel = l_cel / 3.048e-1  # m -> ft
        g = 32.17405  # 32.2 lbm ft/lbf sec**2

        # preprocessing input parameters
        um = us_l + us_g
        Nlv = 1.938 * us_l * (rho_l / sigma) ** 0.25
        Ll = us_l / um

        Frm2 = um**2 / (g * d_tube)

        L1 = 316 * Ll**0.302
        L2 = 0.0009252 * Ll**-2.4684
        L3 = 0.10 * Ll**-1.4516
        L4 = 0.5 * Ll**-6.738

        # reg 1 = segregated
        # reg 2 = intermittend
        # reg 3 = distributed
        # reg 4 = transition
        if (Ll < 0.01) and (Frm2 < L1):
            reg = 1

        elif (Ll >= 0.01) and (Frm2 < L2):
            reg = 1

        elif (Ll >= 0.01) and ((Frm2 >= L2) and (Frm2 <= L3)):
            reg = 4

        elif ((Ll > 0.01) and (Ll < 0.4)) and ((Frm2 >= L3) and (Frm2 <= L1)):
            reg = 2

        elif (Ll > 0.4) and ((Frm2 >= L3) and (Frm2 <= L4)):
            reg = 2

        elif (Ll < 0.4) and (Frm2 >= L1):
            reg = 3

        elif (Ll > 0.4) and (Frm2 >= L4):
            reg = 3

        else:
            reg = 0

        Hl0_1 = 0.98 * (Ll**0.4846) / (Frm2**0.0868)
        Hl0_2 = 0.845 * (Ll**0.5351) / (Frm2**0.0173)
        Hl0_3 = 1.065 * (Ll**0.5824) / (Frm2**0.0609)

        if theta < 0:
            d = 4.7
            e = -0.3692
            f = 0.1244
            h = -0.5056
            C = max(0, (1 - Ll) * math.log(d * (Ll**e) * (Nlv**f) * (Frm2**h)))
            psi = 1 + C * (math.sin(1.8 * theta) - 0.333 * (math.sin(1.8 * theta)) ** 3)
            Hl_down_1 = Hl0_1 * psi
            Hl_down_2 = Hl0_2 * psi

        elif (theta >= 0) and (reg == 1):  # segregated uphill
            d = 0.011
            e = -3.768
            f = 3.539
            h = -1.614
            C = max(0, (1 - Ll) * math.log(d * (Ll**e) * (Nlv**f) * (Frm2**h)))
            psi = 1 + C * (math.sin(1.8 * theta) - 0.333 * (math.sin(1.8 * theta)) ** 3)
            Hl_up_1 = Hl0_1 * psi
        elif (theta >= 0) and (reg == 2):  # intermittend uphill
            d = 2.96
            e = 0.305
            f = -0.4473
            h = 0.0978
            C = max(0, (1 - Ll) * math.log(d * (Ll**e) * (Nlv**f) * (Frm2**h)))
            psi = 1 + C * (math.sin(1.8 * theta) - 0.333 * (math.sin(1.8 * theta)) ** 3)
            Hl_up_2 = Hl0_2 * psi
        elif (theta >= 0) and (reg == 3):  # distributed uphill
            C = 0
            psi = 1
        else:  # transition uphill
            d = 0.011
            e = -3.768
            f = 3.539
            h = -1.614
            C = max(0, (1 - Ll) * math.log(d * (Ll**e) * (Nlv**f) * (Frm2**h)))
            psi = 1 + C * (math.sin(1.8 * theta) - 0.333 * (math.sin(1.8 * theta)) ** 3)
            Hl_up_1 = Hl0_1 * psi
            d = 2.96
            e = 0.305
            f = -0.4473
            h = 0.0978
            C = max(0, (1 - Ll) * math.log(d * (Ll**e) * (Nlv**f) * (Frm2**h)))
            psi = 1 + C * (math.sin(1.8 * theta) - 0.333 * (math.sin(1.8 * theta)) ** 3)
            Hl_up_2 = Hl0_2 * psi

        if reg == 0:
            Hl = 0
        elif reg == 1:
            Hl = Hl0_1 * psi
        elif reg == 2:
            Hl = Hl0_2 * psi
        elif reg == 3:
            Hl = Hl0_3 * psi
        elif reg == 4:
            A = (L3 - Frm2) / (L3 - L2)
            if theta < 0:
                Hl = A * Hl_down_1 + (1 - A) * Hl_down_2
            else:
                Hl = A * Hl_up_1 + (1 - A) * Hl_up_2

        Hl = min(Hl, 1)
        Hl = max(Hl, 0)

        y = Ll / Hl**2
        if (y > 1) and (y < 1.2):
            s = math.log(2.2 * y - 1.2)
        else:
            s = math.log(y) / (
                -0.0523
                + 3.182 * math.log(y)
                - 0.8725 * (math.log(y)) ** 2
                + 0.01853 * (math.log(y)) ** 4
            )

        ftpfn = math.exp(s)

        if Ll == 0:
            ftpfn = 1

        # Conversion output parameter
        us_g = us_g * 3.048e-1  # m/s <- ft/s
        us_l = us_l * 3.048e-1  # m/s <- ft/s
        rho_g = rho_g * 1.601846e1  # kg/m3 <- lbm/ft3
        rho_l = rho_l * 1.601846e1  # kg/m3 <- lbm/ft3
        eta_g = eta_g * 1e-3  # Pa s <- cp
        eta_l = eta_l * 1e-3  # Pa s <- cp
        sigma = sigma * 1e-3  # N/m <- dyne/cm
        d_tube = d_tube * 3.048e-1  # m <- ft
        eps_g = eps_g * 3.048e-1  # m <- ft
        l_cel = l_cel * 3.048e-1  # m <- ft
        g = 9.81  # 32.2 lbm ft/lbf sec**2
        um = us_g + us_l

        # friction
        Ll = us_l / um
        rhom = (Ll * rho_l) + (1 - Ll) * rho_g
        etam = (Ll * eta_l) + (1 - Ll) * eta_g
        Rem = um * rhom * d_tube / etam
        lambdam = (
            -0.8685 * math.log((1.964 * math.log(Rem) - 3.8215) / Rem + eps_g / (d_tube * 3.71))
        ) ** (-2)
        dp_fric = (0.5 * rhom * um * abs(um)) * lambdam * ftpfn * l_cel / d_tube

        # gravity
        rhom = (Hl * rho_l) + (1 - Hl) * rho_g
        dp_grav = rhom * g * l_cel * math.sin(theta)

        return dp_fric, dp_grav
