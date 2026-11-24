import pygame
import random
import math
from Projectile import Projectile
from Utils import normalize_vector, rotate_vector

"""
Module quản lý hệ thống vũ khí (Weapon): Pistol, Shotgun, MachineGun.
Tối ưu:
- Dùng Projectile.spawn (Object Pool) thay vì tạo mới đối tượng & Surface.
- Tiền tính mảng góc xoay (cos, sin) cho Shotgun và chỉ normalize vector 1 lần duy nhất.
"""


class Weapon:
    def __init__(self):
        self.lastShot = 0

    def shoot(self, user, mousePos, now=None):
        pass


class Pistol(Weapon):
    def __init__(self):
        super().__init__()
        self.weaponCooldown = 250

    def shoot(self, user, mousePos, now=None):
        currentTime = now if now is not None else pygame.time.get_ticks()
        if currentTime - self.lastShot > self.weaponCooldown:
            dx = mousePos[0] - user.pos[0]
            dy = mousePos[1] - user.pos[1]
            direction = (dx, dy) if (dx != 0 or dy != 0) else (1, 1)
            self.lastShot = currentTime
            user.projectiles.add(
                Projectile.spawn(
                    user.pos, normalize_vector(direction), 5, 2000, (0, 255, 0),
                    is_player=True, now=currentTime
                )
            )


class Shotgun(Weapon):
    def __init__(self):
        super().__init__()
        self.weaponCooldown = 750
        self.spreadArc = 90
        self.projectilesCount = 7
        arc_diff = self.spreadArc / (self.projectilesCount - 1)
        self._spread_rotations = tuple(
            (math.cos(math.radians(arc_diff * i - self.spreadArc / 2)),
             math.sin(math.radians(arc_diff * i - self.spreadArc / 2)))
            for i in range(self.projectilesCount)
        )

    def shoot(self, user, mousePos, now=None):
        currentTime = now if now is not None else pygame.time.get_ticks()
        if currentTime - self.lastShot > self.weaponCooldown:
            dx = mousePos[0] - user.pos[0]
            dy = mousePos[1] - user.pos[1]
            unit_x, unit_y = normalize_vector((dx, dy) if (dx != 0 or dy != 0) else (1, 1))
            self.lastShot = currentTime
            projs = user.projectiles
            pos = user.pos
            for cos_t, sin_t in self._spread_rotations:
                proj_dir = (unit_x * cos_t - unit_y * sin_t, unit_x * sin_t + unit_y * cos_t)
                projs.add(
                    Projectile.spawn(
                        pos, proj_dir, 7, 500, (0, 255, 0),
                        is_player=True, now=currentTime
                    )
                )


class MachineGun(Weapon):
    def __init__(self):
        super().__init__()
        self.weaponCooldown = 150
        self.spreadArc = 25

    def shoot(self, user, mousePos, now=None):
        currentTime = now if now is not None else pygame.time.get_ticks()
        if currentTime - self.lastShot > self.weaponCooldown:
            dx = mousePos[0] - user.pos[0]
            dy = mousePos[1] - user.pos[1]
            unit_dir = normalize_vector((dx, dy) if (dx != 0 or dy != 0) else (1, 1))
            self.lastShot = currentTime
            theta = math.radians(random.random() * self.spreadArc - self.spreadArc / 2)
            projDir = rotate_vector(unit_dir, theta)
            user.projectiles.add(
                Projectile.spawn(
                    user.pos, projDir, 6, 1000, (0, 255, 0),
                    is_player=True, now=currentTime
                )
            )
