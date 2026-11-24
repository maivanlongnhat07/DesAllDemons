import pygame
import math
from Projectile import Projectile, Particle
from Utils import AssetManager

"""
Module vật phẩm & hiệu ứng: ExplosionSprite, Bomb, HealthOrb.
Tối ưu:
- Cache ảnh nổ, bom và quả cầu máu -> loại bỏ hoàn toàn disk I/O & scale khi spawn/nổ.
- Tiền tính 40 vector vận tốc mảnh nổ, dùng Particle.spawn (Object Pool).
- Hỗ trợ truy vấn SpatialHashGrid cho vùng sát thương bom và Frustum Culling khi render.
"""


class ExplosionSprite(pygame.sprite.Sprite):
    _surface_cache = {}

    @classmethod
    def _get_image(cls, radius):
        img = cls._surface_cache.get(radius)
        if img is not None:
            return img
        size = (radius * 2, radius * 2)
        try:
            img = AssetManager.get_image("bomb/explosion.png", size=size, alpha=True)
        except Exception:
            img = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.circle(img, (255, 100, 0, 150), (radius, radius), radius)
            img = img.convert_alpha()
        cls._surface_cache[radius] = img
        return img

    def __init__(self, pos, radius, now=None):
        super().__init__()
        self.pos = [pos[0] - radius, pos[1] - radius]
        self.radius = radius
        self.image = self._get_image(radius)
        self.rect = self.image.get_rect(center=pos)
        self.spawn_time = now if now is not None else pygame.time.get_ticks()
        self.duration = 400
        self.alive = True

    def update(self, tDelta, now=None):
        current = now if now is not None else pygame.time.get_ticks()
        if current - self.spawn_time > self.duration:
            self.kill()


class Bomb(pygame.sprite.Sprite):
    _cached_image = None
    _EXPLOSION_VELOCITIES = tuple(
        (math.cos((i / 40) * math.pi * 2) * 5.0, math.sin((i / 40) * math.pi * 2) * 5.0)
        for i in range(40)
    )

    @classmethod
    def _get_image(cls, radius):
        if cls._cached_image is not None:
            return cls._cached_image
        size = (radius * 2, radius * 2)
        try:
            cls._cached_image = AssetManager.get_image("bomb/bomb.png", size=size, alpha=True)
        except Exception:
            surf = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.circle(surf, (30, 30, 30), (radius, radius), radius)
            pygame.draw.circle(surf, (255, 100, 0), (radius, radius), radius, 3)
            font = AssetManager.get_font("arial", 20, bold=True)
            text = font.render("B", True, (255, 150, 0))
            surf.blit(text, text.get_rect(center=(radius, radius)))
            cls._cached_image = surf.convert_alpha()
        return cls._cached_image

    def __init__(self, pos):
        super().__init__()
        self.pos = [float(pos[0]), float(pos[1])]
        self.radius = 20
        self.image = self._get_image(self.radius)
        self.rect = self.image.get_rect(center=(int(pos[0]), int(pos[1])))
        self.health = 4
        self.max_health = 4
        self.blast_radius = 70
        self.alive = True

    def explode(self, enemies, Projectile_module, enemy_grid=None, now=None):
        self.alive = False
        current = now if now is not None else pygame.time.get_ticks()

        explosion = ExplosionSprite(self.pos, self.blast_radius, now=current)
        Projectile_module.particles.add(explosion)

        particles_group = Projectile_module.particles
        pos = self.pos
        for p_vel in self._EXPLOSION_VELOCITIES:
            particles_group.add(Particle.spawn(pos, p_vel, 400, (255, 150, 0), now=current))

        bx, by = pos[0], pos[1]
        blast_sq = self.blast_radius * self.blast_radius
        candidates = (
            enemy_grid.query_radius(bx, by, self.blast_radius)
            if enemy_grid is not None
            else enemies
        )
        for enemy in candidates:
            if not enemy.alive():
                continue
            dx = enemy.pos[0] - bx
            dy = enemy.pos[1] - by
            if dx * dx + dy * dy <= blast_sq:
                enemy.health -= 5
                if enemy.health <= 0:
                    enemy.kill()

    def render(self, surface, camera_offset):
        if not self.alive:
            return
        sw, sh = surface.get_size()
        sx = int(self.pos[0] - camera_offset[0])
        sy = int(self.pos[1] - camera_offset[1])
        margin = self.radius + 25
        if -margin < sx < sw + margin and -margin < sy < sh + margin:
            surface.blit(self.image, (sx - self.radius, sy - self.radius))
            bar_w, bar_h = 40, 5
            bx, by = sx - bar_w // 2, sy - self.radius - 12
            pygame.draw.rect(surface, (50, 50, 50), (bx, by, bar_w, bar_h))
            fill_w = int(bar_w * (max(0, self.health) / self.max_health))
            pygame.draw.rect(surface, (255, 150, 0), (bx, by, fill_w, bar_h))


class HealthOrb(pygame.sprite.Sprite):
    _cached_image = None

    @classmethod
    def _get_image(cls, radius):
        if cls._cached_image is None:
            surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (255, 50, 100), (radius, radius), radius)
            pygame.draw.rect(surf, (255, 255, 255), (radius - 2, 4, 4, radius * 2 - 8))
            pygame.draw.rect(surf, (255, 255, 255), (4, radius - 2, radius * 2 - 8, 4))
            cls._cached_image = surf.convert_alpha()
        return cls._cached_image

    def __init__(self, pos):
        super().__init__()
        self.pos = [float(pos[0]), float(pos[1])]
        self.radius = 10
        self.image = self._get_image(self.radius)
        self.rect = self.image.get_rect(center=(int(pos[0]), int(pos[1])))
        self.bob_time = 0.0
        self.heal_amount = 1

    def update(self, tDelta):
        self.bob_time += tDelta * 0.1

    def render(self, surface, camera_offset):
        sw, sh = surface.get_size()
        sx = int(self.pos[0] - camera_offset[0])
        sy = int(self.pos[1] - camera_offset[1])
        margin = self.radius + 10
        if -margin < sx < sw + margin and -margin < sy < sh + margin:
            bob_offset = int(math.sin(self.bob_time) * 5)
            surface.blit(self.image, (sx - self.radius, sy - self.radius + bob_offset))
