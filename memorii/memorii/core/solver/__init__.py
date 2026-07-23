"""Solver components.

Import concrete components from their owning modules. Keeping this package initializer
side-effect free prevents model modules from pulling the complete runtime graph into
otherwise independent schema imports.
"""
