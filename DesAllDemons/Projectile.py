import pygame

"""
Module đường đạn (Projectile) và hạt hiệu ứng (Particle).
Tối ưu:
- Cache Surface theo màu sắc & bảng alpha lượng tử hóa (16 mức) -> 0 lần cấp phát Surface khi bắn.
- Áp dụng Object Pooling cho cả Projectile và Particle -> triệt tiêu áp lực Garbage Collector.
- Bổ sung thuộc tính radius cho Projectile để tối ưu pygame.sprite.collide_circle.
"""


class Particle(pygame.sprite.Sprite):
    _ALPHA_STEPS = 16
    _surface_cache = {}
    _pool = []
    _max_pool_size = 1024

    @classmethod
    def _get_alpha_frames(cls, color):
        frames = cls._surface_cache.get(color)
        if frames is None:
            size = 3
            r = size // 2
            base = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(base, color, (r, r), r)
            steps = cls._ALPHA_STEPS
            frames = []
            for i in range(steps):
                surf = base.copy()
                surf.set_alpha(int(255 * i / (steps - 1)))
                frames.append(surf.convert_alpha())
            cls._surface_cache[color] = frames
        return frames

    @classmethod
    def spawn(cls, pos, velocity, lifetime, color, now=None):
        """Lấy Particle từ Object Pool hoặc khởi tạo mới nếu Pool rỗng."""
        if cls._pool:
            p = cls._pool.pop()
            p._in_pool = False
            p.reset(pos, velocity, lifetime, color, now)
            return p
        return cls(pos, velocity, lifetime, color, now=now)

    def __init__(self, pos, velocity, lifetime, color, now=None):
        super().__init__()
        self._in_pool = False
        self.pos = [0.0, 0.0]
        self.rect = pygame.Rect(0, 0, 3, 3)
        self.reset(pos, velocity, lifetime, color, now)

    def reset(self, pos, velocity, lifetime, color, now=None):
        self._alpha_frames = self._get_alpha_frames(color)
        self.image = self._alpha_frames[-1]
        self.pos[0] = float(pos[0])
        self.pos[1] = float(pos[1])
        self.velocity = velocity
        self.lifetime = lifetime
        self.createdAt = now if now is not None else pygame.time.get_ticks()
        self.rect.topleft = (int(pos[0]), int(pos[1]))

    def kill(self):
        super().kill()
        if not self._in_pool and len(self._pool) < self._max_pool_size:
            self._in_pool = True
            self._pool.append(self)

    def update(self, tDelta, now=None):
        current = now if now is not None else pygame.time.get_ticks()
        elapsed = current - self.createdAt
        if elapsed > self.lifetime:
            self.kill()
            return
        scale = tDelta * 0.3
        self.pos[0] += self.velocity[0] * scale
        self.pos[1] += self.velocity[1] * scale
        self.rect.topleft = (int(self.pos[0]), int(self.pos[1]))

        step = int((1.0 - elapsed / self.lifetime) * (self._ALPHA_STEPS - 1))
        if step < 0:
            step = 0
        self.image = self._alpha_frames[step]


class Projectile(pygame.sprite.Sprite):
    particles = pygame.sprite.Group()
    _surface_cache = {}
    _pool = []
    _max_pool_size = 512

    @classmethod
    def _get_surface(cls, color):
        surf = cls._surface_cache.get(color)
        if surf is None:
            surf = pygame.Surface((8, 8), pygame.SRCALPHA)
            pygame.draw.circle(surf, color, (4, 4), 4)
            surf = surf.convert_alpha()
            cls._surface_cache[color] = surf
        return surf

    @classmethod
    def spawn(cls, source, direction, speed, lifetime, color, is_player=False, now=None):
        """Lấy Projectile từ Object Pool hoặc khởi tạo mới nếu Pool rỗng."""
        if cls._pool:
            proj = cls._pool.pop()
            proj._in_pool = False
            proj.reset(source, direction, speed, lifetime, color, is_player, now)
            return proj
        return cls(source, direction, speed, lifetime, color, is_player=is_player, now=now)

    def __init__(self, source, direction, speed, lifetime, color, is_player=False, now=None):
        super().__init__()
        self._in_pool = False
        self.radius = 4
        self.pos = [0.0, 0.0]
        self.movementVector = [0.0, 0.0]
        self.rect = pygame.Rect(0, 0, 8, 8)
        self.reset(source, direction, speed, lifetime, color, is_player, now)

    def reset(self, source, direction, speed, lifetime, color, is_player=False, now=None):
        self.image = self._get_surface(color)
        self.pos[0] = float(source[0])
        self.pos[1] = float(source[1])
        self.movementVector[0] = float(direction[0])
        self.movementVector[1] = float(direction[1])
        self.rect.center = (int(self.pos[0]), int(self.pos[1]))
        self.speed = speed
        self.lifetime = lifetime
        self.color = color
        tick = now if now is not None else pygame.time.get_ticks()
        self.createdAt = tick
        self.last_particle_time = tick
        self.is_player = is_player

    def kill(self):
        super().kill()
        if not self._in_pool and len(self._pool) < self._max_pool_size:
            self._in_pool = True
            self._pool.append(self)

    def move(self, surfaceSize, tDelta, now=None):
        current = now if now is not None else pygame.time.get_ticks()
        if current > self.createdAt + self.lifetime:
            self.kill()
            return

        step = self.speed * tDelta
        self.pos[0] += self.movementVector[0] * step
        self.pos[1] += self.movementVector[1] * step
        self.rect.center = (int(self.pos[0]), int(self.pos[1]))

        if current - self.last_particle_time > 25:
            self.last_particle_time = current
            p_vel = (
                -self.movementVector[0] * self.speed * 0.2,
                -self.movementVector[1] * self.speed * 0.2,
            )
            Projectile.particles.add(Particle.spawn(self.pos, p_vel, 150, self.color, now=current))

        px, py = self.pos[0], self.pos[1]
        if not (-100 < px < surfaceSize[0] + 100) or not (-100 < py < surfaceSize[1] + 100):
            self.kill()
