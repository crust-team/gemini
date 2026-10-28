"""CO2 corrosion modeling package.

This package contains models and correlations to estimate CO2 corrosion
rates in production systems. Use the high-level dispatchers
`CO2Corrosion` and `CO2CorrosionOpt` to select between supported
correlations:

- `DLD` (1995): de Waard–Lotz–Dugstad
- `DLM` (1991): de Waard–Lotz–Milliams
- `NORSOK` (M-506): industry standard

Subpackages
-----------
- `correlation`: reference implementations of the correlations
- `correlations_opt`: optimized variants

"""
