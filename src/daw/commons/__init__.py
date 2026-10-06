"""Colloquy: a research commons layered over the bio board and substrate.

The web application is a read-mostly layer over immutable records. Every write
goes through the same board functions agents use, under the board writer lock.
No module here decides biology, schedules scientific work, or runs a research loop.
"""
