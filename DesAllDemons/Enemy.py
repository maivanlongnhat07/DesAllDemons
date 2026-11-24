import random
import pygame
from AStar import a_star_search
from Utils import normalize_vector, AssetManager
import Projectile

"""
Module kẻ địch (Enemy, MonsterType1, MonsterType2).
Tối ưu:
- Cache frame animation cấp Class -> loại bỏ disk I/O + scale (~40ms) mỗi lần spawn.
- Sửa lỗi gọi A* 60 FPS do điều kiện 'or not self.path', rải đều chu kỳ tìm đường (staggering).
- Dùng con trỏ path_index (O(1)) thay vì list.pop(0) (O(L)) và bình phương khoảng cách thay vì hypot.
- Truy vấn vật cản và lực đẩy tách đàn (Separation) qua SpatialHashGrid -> từ O(E^2) xuống O(E).
"""


class Enemy(pygame.sprite.Sprite):
    projectiles = pygame.sprite.Group()
    _default_image = None

    @classmethod
    def _get_default_image(cls):
        if cls._default_image is None:
            surf = pygame.Surface((40, 40), pygame.SRCALPHA)
            pygame.draw.circle(surf, (255, 0, 0), (20, 20), 20)
            cls._default_image = surf.convert_alpha()
        return cls._default_image

    def __init__(self, pos):
        super().__init__()
        self.radius = random.randint(15, 20)
        now = pygame.time.get_ticks()

        self.frames = []
        self.current_frame = 0
        self.animation_speed = 100
        self.last_update = now

        self.image = self._get_default_image()
        self.rect = self.image.get_rect(center=(int(pos[0]), int(pos[1])))
        self.hitbox = self.rect.inflate(-16, -16)

        self.pos = [float(pos[0]), float(pos[1])]
        self.movementVector = [0.0, 0.0]
        self.movementSpeed = 1.5
        self.lastShot = now
        self.weaponCooldown = 1500

        self.health, self.max_health = 2, 2

        self.path = []
        self.path_index = 0
        self.path_update_interval = 400
        # Rải đều thời điểm tính lại đường đi để tránh spike CPU khi nhiều quái cập nhật cùng frame
        self.last_path_update = now - random.randint(0, self.path_update_interval)

    def update_animation(self, now=None):
        if not self.frames:
            return
        current = now if now is not None else pygame.time.get_ticks()
        if current - self.last_update > self.animation_speed:
            self.last_update = current
            self.current_frame = (self.current_frame + 1) % len(self.frames)
            self.image = self.frames[self.current_frame]

    def move(self, enemies, playerPos, tDelta, game_map, enemy_grid=None, now=None):
        current_time = now if now is not None else pygame.time.get_ticks()
        self.update_animation(current_time)

        # Chỉ tính lại đường đi đúng chu kỳ throttling (đã bỏ 'or not self.path' gây spam A*)
        if current_time - self.last_path_update >= self.path_update_interval:
            self.last_path_update = current_time
            self.path = a_star_search(self.pos, playerPos)
            self.path_index = 0

        target_pos = playerPos
        if self.path_index < len(self.path):
            next_node = self.path[self.path_index]
            dx_n = next_node[0] - self.pos[0]
            dy_n = next_node[1] - self.pos[1]
            thresh = self.radius * 1.5
            if dx_n * dx_n + dy_n * dy_n < thresh * thresh:
                self.path_index += 1
                if self.path_index < len(self.path):
                    next_node = self.path[self.path_index]
                else:
                    next_node = playerPos
            target_pos = next_node

        self.movementVector = normalize_vector((target_pos[0] - self.pos[0], target_pos[1] - self.pos[1]))
        vx = self.movementVector[0] * self.movementSpeed * tDelta
        vy = self.movementVector[1] * self.movementSpeed * tDelta

        # Kiểm tra va chạm vật cản O(1) qua SpatialHashGrid
        self.pos[0] += vx
        self.rect.centerx = int(self.pos[0])
        self.hitbox.centerx = self.rect.centerx
        for obs in game_map.get_nearby_obstacles(self.hitbox):
            if self.hitbox.colliderect(obs.rect):
                if vx > 0:
                    self.hitbox.right = obs.rect.left
                elif vx < 0:
                    self.hitbox.left = obs.rect.right
                self.rect.centerx = self.hitbox.centerx
                self.pos[0] = float(self.rect.centerx)

        self.pos[1] += vy
        self.rect.centery = int(self.pos[1])
        self.hitbox.centery = self.rect.centery
        for obs in game_map.get_nearby_obstacles(self.hitbox):
            if self.hitbox.colliderect(obs.rect):
                if vy > 0:
                    self.hitbox.bottom = obs.rect.top
                elif vy < 0:
                    self.hitbox.top = obs.rect.bottom
                self.rect.centery = self.hitbox.centery
                self.pos[1] = float(self.rect.centery)

        # Separation Force O(k) qua SpatialHashGrid thay vì vòng lặp O(E^2)
        pushX, pushY = 0.0, 0.0
        px, py = self.pos[0], self.pos[1]
        my_r = self.radius
        candidates = (
            enemy_grid.query_radius(px, py, my_r * 2 + 10)
            if enemy_grid is not None
            else enemies
        )
        for sprite in candidates:
            if sprite is self:
                continue
            dx = px - sprite.pos[0]
            dy = py - sprite.pos[1]
            r_sum = my_r + sprite.radius
            if dx * dx + dy * dy < r_sum * r_sum:
                pushX += dx
                pushY += dy

        if pushX != 0.0 or pushY != 0.0:
            pv = normalize_vector((pushX, pushY))
            self.pos[0] += pv[0] * 0.5
            self.pos[1] += pv[1] * 0.5
            self.rect.center = (int(self.pos[0]), int(self.pos[1]))
            self.hitbox.center = self.rect.center

    def shoot(self, playerPos, now=None):
        current = now if now is not None else pygame.time.get_ticks()
        if current - self.lastShot > self.weaponCooldown:
            direction = normalize_vector((playerPos[0] - self.pos[0], playerPos[1] - self.pos[1]))
            self.lastShot = current
            self.projectiles.add(
                Projectile.Projectile.spawn(
                    self.pos, direction, 3, 500, (255, 0, 0), is_player=False, now=current
                )
            )

    def draw_health_bar(self, surface, camera_offset):
        screen_x = int(self.pos[0] - camera_offset[0])
        screen_y = int(self.pos[1] - camera_offset[1])
        bar_w, bar_h = 30, 4
        bar_x, bar_y = screen_x - bar_w // 2, screen_y - 25

        pygame.draw.rect(surface, (50, 50, 50), (bar_x, bar_y, bar_w, bar_h))
        pygame.draw.rect(surface, (255, 0, 0), (bar_x, bar_y, int(bar_w * max(0, self.health / self.max_health)), bar_h))
        pygame.draw.rect(surface, (255, 255, 255), (bar_x, bar_y, bar_w, bar_h), 1)


class MonsterType1(Enemy):
    _cached_frames = None

    @classmethod
    def _load_frames(cls):
        if cls._cached_frames is None:
            frames = []
            try:
                for i in range(6):
                    frames.append(AssetManager.get_image(f"enemies/fly/fly_{i}.png", size=(50, 50), alpha=True))
            except Exception:
                frames = []
            cls._cached_frames = frames
        return cls._cached_frames

    def __init__(self, pos):
        super().__init__(pos)
        self.radius = 20
        self.health, self.max_health = 3, 3
        self.movementSpeed = 1.6
        self.weaponCooldown = 2000
        self.animation_speed = 100

        self.frames = self._load_frames()
        if self.frames:
            self.image = self.frames[0]

        self.rect = self.image.get_rect(center=(int(pos[0]), int(pos[1])))
        self.hitbox = self.rect.inflate(-30, -30)


class MonsterType2(Enemy):
    _cached_frames = None

    @classmethod
    def _load_frames(cls):
        if cls._cached_frames is None:
            frames = []
            try:
                for i in range(8):
                    frames.append(AssetManager.get_image(f"enemies/walk/walk_{i}.png", size=(50, 50), alpha=True))
            except Exception:
                frames = []
            cls._cached_frames = frames
        return cls._cached_frames

    def __init__(self, pos):
        super().__init__(pos)
        self.radius = 20
        self.health, self.max_health = 5, 5
        self.movementSpeed = 1.6
        self.weaponCooldown = 2000
        self.animation_speed = 100

        self.frames = self._load_frames()
        if self.frames:
            self.image = self.frames[0]

        self.rect = self.image.get_rect(center=(int(pos[0]), int(pos[1])))
        self.hitbox = self.rect.inflate(-30, -30)
