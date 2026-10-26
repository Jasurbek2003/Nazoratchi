"""Argon2id parametrlari (TZ 14.3.1): time_cost=3, memory_cost=64 MiB, parallelism=2."""

from django.contrib.auth.hashers import Argon2PasswordHasher


class NazoratchiArgon2PasswordHasher(Argon2PasswordHasher):
    time_cost = 3
    memory_cost = 64 * 1024  # KiB
    parallelism = 2
