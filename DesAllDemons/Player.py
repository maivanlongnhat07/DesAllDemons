import pygame
import Weapon
from Utils import normalize_vector, AssetManager
from Map import map_size

"""
Module nhân vật chính (Player).
Tối ưu:
- Cache animation Hero cấp Class qua AssetManager (không nạp lại khi restart ván mới).
- Tái sử dụng keys từ game_loop, kiểm tra va chạm vật cản O(1) qua SpatialHashGrid.
"""


class Player(pygame.sprite.Sprite):
    projectiles = pygame.sprite.Group()
    _cached_frames = None

    @classmethod
    def _load_frames(cls):
        if cls._cached_frames is None:
            frames = []
            try:
                for i in range(8):
                    frames.append(AssetManager.get_image(f"hero/hero_{i}.png", size=(40, 40), alpha=True))
            except Exception:
                fallback = pygame.Surface((40, 40), pygame.SRCALPHA)
                pygame.draw.circle(fallback, (0, 200, 255), (20, 20), 20)
                frames = [fallback.convert_alpha()]
            cls._cached_frames = frames
        return cls._cached_frames

    def __init__(self, screenSize):
        super().__init__()
        self.radius = 20
        self.frames = self._load_frames()
        self.current_frame = 0
        self.animation_speed = 100
        self.last_update = pygame.time.get_ticks()

        self.image = self.frames[0]
        self.rect = self.image.get_rect(x=screenSize[0] // 2, y=screenSize[1] // 2)
        self.hitbox = self.rect.inflate(-16, -16)
        self.pos = [float(screenSize[0] // 2), float(screenSize[1] // 2)]
        self.health, self.max_health = 6, 6
        self.alive = True
        self.movementVector, self.movementSpeed = [0.0, 0.0], 5
        self.availableWeapons = [Weapon.Pistol(), Weapon.Shotgun(), Weapon.MachineGun()]
        self.equippedWeapon = self.availableWeapons[0]
        self.target_pos = None
        self.health_bar_width, self.health_bar_height = 40, 6

    def update_animation(self, is_moving, now=None):
        if not self.frames:
            return
        if is_moving:
            current = now if now is not None else pygame.time.get_ticks()
            if current - self.last_update > self.animation_speed:
                self.last_update = current
                self.current_frame = (self.current_frame + 1) % len(self.frames)
                self.image = self.frames[self.current_frame]
        else:
            if self.current_frame != 0:
                self.current_frame = 0
                self.image = self.frames[0]

    def move(self, game_map, screenSize, tDelta, keys=None, now=None):
        if keys is None:
            keys = pygame.key.get_pressed()
        kb_dx = (1 if keys[pygame.K_d] else 0) - (1 if keys[pygame.K_a] else 0)
        kb_dy = (1 if keys[pygame.K_s] else 0) - (1 if keys[pygame.K_w] else 0)

        if kb_dx != 0 or kb_dy != 0:
            self.target_pos = None
            self.movementVector = [kb_dx, kb_dy]
        elif self.target_pos:
            dx = self.target_pos[0] - self.pos[0]
            dy = self.target_pos[1] - self.pos[1]
            if dx * dx + dy * dy > 25:
                self.movementVector = [dx, dy]
            else:
                self.movementVector, self.target_pos = [0.0, 0.0], None
        else:
            self.movementVector = [0.0, 0.0]

        self.movementVector = normalize_vector(self.movementVector)
        vx = self.movementVector[0] * self.movementSpeed * tDelta
        vy = self.movementVector[1] * self.movementSpeed * tDelta

        self.update_animation(vx != 0.0 or vy != 0.0, now=now)

        # Trục X
        self.pos[0] += vx
        self.rect.x = int(self.pos[0])
        self.hitbox.centerx = self.rect.centerx

        if self.rect.left < 0:
            self.rect.left = 0
            self.hitbox.centerx = self.rect.centerx
        elif self.rect.right > map_size[0]:
            self.rect.right = map_size[0]
            self.hitbox.centerx = self.rect.centerx

        for obs in game_map.get_nearby_obstacles(self.hitbox):
            if self.hitbox.colliderect(obs.rect):
                if vx > 0:
                    self.hitbox.right = obs.rect.left
                elif vx < 0:
                    self.hitbox.left = obs.rect.right
                self.rect.centerx = self.hitbox.centerx
        self.pos[0] = float(self.rect.x)

        # Trục Y
        self.pos[1] += vy
        self.rect.y = int(self.pos[1])
        self.hitbox.centery = self.rect.centery

        if self.rect.top < 0:
            self.rect.top = 0
            self.hitbox.centery = self.rect.centery
        elif self.rect.bottom > map_size[1]:
            self.rect.bottom = map_size[1]
            self.hitbox.centery = self.rect.centery

        for obs in game_map.get_nearby_obstacles(self.hitbox):
            if self.hitbox.colliderect(obs.rect):
                if vy > 0:
                    self.hitbox.bottom = obs.rect.top
                elif vy < 0:
                    self.hitbox.top = obs.rect.bottom
                self.rect.centery = self.hitbox.centery
        self.pos[1] = float(self.rect.y)

    def shoot(self, mousePos, now=None):
        self.equippedWeapon.shoot(self, mousePos, now=now)

    def draw_health_bar(self, surface, camera_offset):
        screen_x = int(self.pos[0] - camera_offset[0])
        screen_y = int(self.pos[1] - camera_offset[1])
        center_x = screen_x + 20
        bar_x = center_x - self.health_bar_width // 2
        bar_y = screen_y - 30

        pygame.draw.rect(surface, (50, 50, 50), (bar_x, bar_y, self.health_bar_width, self.health_bar_height))
        hp_perc = max(0, self.health / self.max_health)
        pygame.draw.rect(surface, (0, 255, 0), (bar_x, bar_y, int(self.health_bar_width * hp_perc), self.health_bar_height))
        pygame.draw.rect(surface, (255, 255, 255), (bar_x, bar_y, self.health_bar_width, self.health_bar_height), 1)
