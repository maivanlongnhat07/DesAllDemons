import pygame
from Utils import AssetManager, SpatialHashGrid

screen_size = (1200, 720)
map_size = (1200, 720)
edge_threshold = 30
camera_speed = 8

"""
Module quản lý bản đồ (Map) và các chướng ngại vật tĩnh (Obstacles).
Tối ưu:
- Cache toàn bộ texture chướng ngại vật & background qua AssetManager.
- Pre-bake các chướng ngại vật tĩnh vào 1 lớp background duy nhất (1 lần blit opaque/frame).
- Dùng SpatialHashGrid cho truy vấn va chạm vật cản O(1).
"""


class Obstacles(pygame.sprite.Sprite):
    def __init__(self, rect, obstacle_type, img_file):
        super().__init__()
        self.rect = pygame.Rect(rect)
        self.type = obstacle_type
        self.image = AssetManager.get_image(
            img_file, size=(self.rect.width, self.rect.height), alpha=True
        )

        hitbox_width = self.rect.width * 0.5
        hitbox_height = self.rect.height * 0.4
        self.hitbox = pygame.Rect(
            self.rect.centerx - hitbox_width / 2,
            self.rect.bottom - hitbox_height,
            hitbox_width,
            hitbox_height,
        )


class Rock(Obstacles):
    def __init__(self, rect, img_file=None):
        super().__init__(rect, obstacle_type="rock", img_file=img_file)
        hb_width = self.rect.width * 0.8
        hb_height = self.rect.height * 0.6
        self.hitbox = pygame.Rect(
            self.rect.centerx - hb_width / 2,
            self.rect.bottom - hb_height,
            hb_width,
            hb_height,
        )


class Tree(Obstacles):
    def __init__(self, rect, img_file=None):
        super().__init__(rect, obstacle_type="tree", img_file=img_file)


class Map:
    def __init__(self, size):
        self.width, self.height = size
        self.obstacles = pygame.sprite.Group()
        self.obstacle_grid = SpatialHashGrid(cell_size=128)
        self.camera_offset = [0, 0]

        self.bg_image = None
        try:
            self.bg_image = AssetManager.get_image(
                "background.png", size=(self.width, self.height), alpha=False
            )
        except Exception:
            self.bg_image = None

        xmastree_w, xmastree_h = 75, 75
        christmas_coords = [(242, 70), (94, 292), (303, 474), (357, 418)]
        for x, y in christmas_coords:
            self.obstacles.add(Tree((x, y, xmastree_w, xmastree_h), img_file="tree/christmas_tree.png"))

        palmtree_w, palmtree_h = 75, 75
        palm_coords = [
            (626, 195), (626, 355), (741, 28), (808, 474),
            (741, 522), (1172, 522), (842, 195), (909, 139),
            (1010, 418), (1077, 474), (1118, 70), (1172, 195),
        ]
        for x, y in palm_coords:
            self.obstacles.add(Tree((x, y, palmtree_w, palmtree_h), img_file="tree/palm_tree.png"))

        brokentree_w, brokentree_h = 40, 40
        broken_coords = [(120, 100), (242, 300), (418, 111)]
        for x, y in broken_coords:
            self.obstacles.add(Tree((x, y, brokentree_w, brokentree_h), img_file="tree/broken_tree.png"))

        mosstree_w, mosstree_h = 75, 75
        for x, y in [(1100, 650)]:
            self.obstacles.add(Tree((x, y, mosstree_w, mosstree_h), img_file="tree/moss_tree.png"))

        red_crystal_w, red_crystal_h = 30, 30
        for x, y in [(780, 450)]:
            self.obstacles.add(Rock((x, y, red_crystal_w, red_crystal_h), img_file="rock/red_crystal.png"))

        # Xây dựng lưới băm tĩnh cho toàn bộ vật cản -> truy vấn O(1)
        for obs in self.obstacles:
            self.obstacle_grid.insert(obs, obs.rect)

        # Pre-bake nền + toàn bộ vật cản tĩnh thành 1 Surface opaque duy nhất
        self._baked_bg = self._build_baked_layer()

    def _build_baked_layer(self):
        if self.width * self.height > 4096 * 4096:
            return None
        baked = pygame.Surface((self.width, self.height)).convert()
        if self.bg_image:
            baked.blit(self.bg_image, (0, 0))
        else:
            baked.fill((20, 20, 30))
        for obs in self.obstacles:
            baked.blit(obs.image, obs.rect)
        return baked

    def render(self, surface):
        """
        Kết xuất bản đồ cắt theo đúng khung nhìn camera (Viewport Area Blit).
        Khi có lớp pre-bake: chỉ tốn đúng 1 lệnh blit không cần alpha-blending mỗi frame.
        """
        sw, sh = surface.get_size()
        cam_x, cam_y = int(self.camera_offset[0]), int(self.camera_offset[1])
        view_rect = pygame.Rect(cam_x, cam_y, sw, sh)

        if self._baked_bg is not None:
            surface.blit(self._baked_bg, (0, 0), view_rect)
            return

        if self.bg_image:
            surface.blit(self.bg_image, (0, 0), view_rect)
        else:
            surface.fill((20, 20, 30))

        # Fallback frustum culling bằng SpatialHashGrid nếu bản đồ quá lớn
        for obstacle in self.obstacle_grid.query_rect(view_rect):
            if view_rect.colliderect(obstacle.rect):
                surface.blit(obstacle.image, (obstacle.rect.x - cam_x, obstacle.rect.y - cam_y))

    def get_obstacles(self):
        return self.obstacles

    def get_nearby_obstacles(self, rect):
        """Trả về danh sách vật cản lân cận theo SpatialHashGrid."""
        return self.obstacle_grid.query_rect(rect)

    def update(self, mouse_pos=None):
        mouse_x, mouse_y = mouse_pos if mouse_pos is not None else pygame.mouse.get_pos()
        if mouse_x < edge_threshold:
            self.camera_offset[0] -= camera_speed
        elif mouse_x > screen_size[0] - edge_threshold:
            self.camera_offset[0] += camera_speed
        if mouse_y < edge_threshold:
            self.camera_offset[1] -= camera_speed
        elif mouse_y > screen_size[1] - edge_threshold:
            self.camera_offset[1] += camera_speed

        self.camera_offset[0] = max(0, min(self.camera_offset[0], self.width - screen_size[0]))
        self.camera_offset[1] = max(0, min(self.camera_offset[1], self.height - screen_size[1]))
