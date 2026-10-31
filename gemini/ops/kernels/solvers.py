"""Root finding on arrays for the NumPy backend, step for step like the scalar algorithms.

``brent_roots`` repeats ``scipy.optimize.brentq`` (Brent's method as in SciPy's C source) and
``newton_roots`` the handwritten Newton iteration of the Python backend, each on all rows at once
with a mask of the rows still iterating. A row stops on its own rule and keeps its own iterate,
so every row gets the iterate the scalar algorithm gives, up to the last bits of the function
evaluations. A row whose bracket has no sign change, that does not converge or whose iterate is
not finite is NaN, never an error.

NOTE(refactor): ``scipy.optimize.elementwise.find_root`` and ``scipy.optimize.newton`` on arrays
were measured and rejected. ``find_root`` stops by another rule, so it lands up to 1.4e-12
relative away from the Brent result (whose error is within ``xtol``), and ``scipy.optimize.newton``
stops after the step on an absolute tolerance, so it returns another iterate than the scalar loop
and moves a pH that is rounded to 0.01 across a rounding boundary.
"""

import numpy as np


def brent_roots(function, low, high, args, xtol, rtol, maxiter):
    """Return the roots of ``function(x, *args)`` in ``[low, high]``, NaN where there is none.

    The operands broadcast to one shape. ``function`` receives the arrays of the rows still
    iterating, so it must evaluate row by row.
    """
    shape, operands = _flatten((low, high, *args))
    state = _Brent(function, operands[:2], operands[2:], xtol, rtol)
    roots = np.full(operands[0].shape, np.nan)
    state.settle_ends(roots)
    for _ in range(maxiter):
        if not state.rows.size:
            break
        state.iterate(roots)
    return _shaped(roots, shape)


def newton_roots(function, derivative, start, args, tolerance, max_iterations):
    """Return the Newton iterates from ``start`` that satisfy the stopping rule of each row.

    A row stops when the step is below ``tolerance`` times the current value, or at iteration
    ``max_iterations``, and keeps the value before that step. The operands broadcast to one shape.
    """
    shape, operands = _flatten((start, *args))
    value, args = operands[0], operands[1:]
    rows = np.arange(value.size)
    roots = np.full(value.shape, np.nan)
    for iteration in range(max_iterations + 1):
        following = value - function(value, *args) / derivative(value, *args)
        done = (np.abs(following - value) < tolerance * value) | (iteration >= max_iterations)
        roots[rows[done]] = value[done]
        keep = ~done
        rows, value, args = rows[keep], following[keep], [argument[keep] for argument in args]
        if not rows.size:
            break
    roots[~np.isfinite(roots)] = np.nan
    return _shaped(roots, shape)


def _flatten(operands):
    """Broadcast the operands, returning the common shape and one flat float array each."""
    arrays = np.broadcast_arrays(*(np.asarray(operand, dtype=float) for operand in operands))
    return arrays[0].shape, [array.ravel() for array in arrays]


def _shaped(roots, shape):
    """Return the roots in the broadcast shape, a scalar for scalar operands."""
    return roots.reshape(shape)[()]


class _Brent:
    """The state of Brent's method for the rows still iterating.

    ``rows`` are the positions of those rows in the result; the other attributes follow the names
    of the C source: the previous, current and blocking points ``x*`` with values ``f*`` and the
    previous and current step sizes ``spre`` and ``scur``.
    """

    def __init__(self, function, bounds, args, xtol, rtol):
        self.function, self.args, self.xtol, self.rtol = function, args, xtol, rtol
        self.rows = np.arange(bounds[0].size)
        self.xpre, self.xcur = bounds
        self.fpre = function(self.xpre, *args)
        self.fcur = function(self.xcur, *args)
        self.xblk = self.fblk = self.spre = self.scur = np.zeros(self.rows.size)

    def settle_ends(self, roots):
        """Finish rows whose bound is a root and drop rows without a sign change."""
        at_low = self.fpre == 0
        at_high = (self.fcur == 0) & ~at_low
        roots[self.rows[at_low]] = self.xpre[at_low]
        roots[self.rows[at_high]] = self.xcur[at_high]
        no_sign_change = np.signbit(self.fpre) == np.signbit(self.fcur)
        unusable = ~np.isfinite(self.fpre) | ~np.isfinite(self.fcur)
        self._keep(~(at_low | at_high | no_sign_change | unusable))

    def iterate(self, roots):
        """Run one iteration of Brent's method, finishing the rows that converge."""
        self._bracket()
        delta = (self.xtol + self.rtol * np.abs(self.xcur)) / 2
        bisection = (self.xblk - self.xcur) / 2
        converged = (self.fcur == 0) | (np.abs(bisection) < delta)
        roots[self.rows[converged]] = self.xcur[converged]
        self._keep(~converged)
        delta, bisection = delta[~converged], bisection[~converged]
        self._choose_step(delta, bisection)
        self.xpre, self.fpre = self.xcur, self.fcur
        forward = np.where(bisection > 0, delta, -delta)
        self.xcur = np.where(np.abs(self.scur) > delta, self.xcur + self.scur, self.xcur + forward)
        self.fcur = self.function(self.xcur, *self.args)

    def _bracket(self):
        """Move the blocking point to the previous point when the sign changed, then swap."""
        opposite = (
            (self.fpre != 0) & (self.fcur != 0) & (np.signbit(self.fpre) != np.signbit(self.fcur))
        )
        step = self.xcur - self.xpre
        self.xblk = np.where(opposite, self.xpre, self.xblk)
        self.fblk = np.where(opposite, self.fpre, self.fblk)
        self.spre = np.where(opposite, step, self.spre)
        self.scur = np.where(opposite, step, self.scur)
        swap = np.abs(self.fblk) < np.abs(self.fcur)
        self.xpre, self.xcur, self.xblk = (
            np.where(swap, self.xcur, self.xpre),
            np.where(swap, self.xblk, self.xcur),
            np.where(swap, self.xcur, self.xblk),
        )
        self.fpre, self.fcur, self.fblk = (
            np.where(swap, self.fcur, self.fpre),
            np.where(swap, self.fblk, self.fcur),
            np.where(swap, self.fcur, self.fblk),
        )

    def _choose_step(self, delta, bisection):
        """Take the interpolated or extrapolated step when it is short enough, else bisect."""
        trial = self._trial_step()
        promising = (np.abs(self.spre) > delta) & (np.abs(self.fcur) < np.abs(self.fpre))
        short = 2 * np.abs(trial) < np.minimum(np.abs(self.spre), 3 * np.abs(bisection) - delta)
        accept = promising & short
        self.spre = np.where(accept, self.scur, bisection)
        self.scur = np.where(accept, trial, bisection)

    def _trial_step(self):
        """Return the inverse-quadratic step, or the secant step when the points coincide."""
        secant = -self.fcur * (self.xcur - self.xpre) / (self.fcur - self.fpre)
        slope_pre = (self.fpre - self.fcur) / (self.xpre - self.xcur)
        slope_blk = (self.fblk - self.fcur) / (self.xblk - self.xcur)
        quadratic = (
            -self.fcur
            * (self.fblk * slope_blk - self.fpre * slope_pre)
            / (slope_blk * slope_pre * (self.fblk - self.fpre))
        )
        return np.where(self.xpre == self.xblk, secant, quadratic)

    def _keep(self, mask):
        """Continue with the rows where ``mask`` holds."""
        self.rows = self.rows[mask]
        self.args = [argument[mask] for argument in self.args]
        for name in ("xpre", "xcur", "xblk", "fpre", "fcur", "fblk", "spre", "scur"):
            setattr(self, name, getattr(self, name)[mask])
