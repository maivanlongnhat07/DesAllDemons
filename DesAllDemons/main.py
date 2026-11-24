import pygame
import random
import sys
from Player import Player
from Enemy import Enemy, MonsterType1, MonsterType2
from Projectile import Projectile, Particle
from Map import Map, Obstacles, map_size
from AStar import init_nav_grid, update_flow_field
from Items import Bomb, HealthOrb
from Utils import distance, AssetManager, SpatialHashGrid
from HighScore import HighScoreManager

"""
Module Game Chính (Main Engine Loop).
Tối ưu:
- Cache Font, Surface HUD (dirty-flag) và Gradient nền -> triệt tiêu gọi SysFont 60 FPS.
- Dọn sạch các Group static (Player.projectiles, Enemy.projectiles, Projectile.particles) giữa các ván chơi.
- SpatialHashGrid cho va chạm đạn-quái, đạn-bom và tách đàn quái.
- Frustum/Camera Culling toàn diện cho hạt, vật phẩm, đạn và quái vật.
- Tách logic game_loop thành các hàm/lớp chuyên biệt dễ bảo trì.
"""

high_score_manager = HighScoreManager()
_gradient_cache = {}


# ============ UTILITIES ============
def draw_text(text, font, text_col, surface, x, y):
    textobj = font.render(text, True, text_col)
    textrect = textobj.get_rect(center=(x, y))
    surface.blit(textobj, textrect)


def draw_text_left(text, font, text_col, surface, x, y):
    textobj = font.render(text, True, text_col)
    surface.blit(textobj, (x, y))


def create_gradient_surface(width, height, color1, color2):
    """Tạo gradient dọc nhanh bằng cột 1px rồi scale ngang + convert() + cache."""
    key = (width, height, color1, color2)
    cached = _gradient_cache.get(key)
    if cached is not None:
        return cached

    col_surf = pygame.Surface((1, height))
    r1, g1, b1 = color1
    dr, dg, db = color2[0] - r1, color2[1] - g1, color2[2] - b1
    inv_h = 1.0 / height
    for y in range(height):
        ratio = y * inv_h
        col_surf.set_at((0, y), (int(r1 + dr * ratio), int(g1 + dg * ratio), int(b1 + db * ratio)))

    surface = pygame.transform.scale(col_surf, (width, height)).convert()
    _gradient_cache[key] = surface
    return surface


# ============ HUD & GAME SESSION HELPERS ============
class GameHUD:
    """Quản lý hiển thị HUD tối ưu: chỉ render lại chữ Score khi điểm thực sự thay đổi."""

    def __init__(self):
        self.font_hud = AssetManager.get_font("arial", 32, bold=True)
        self._last_score = None
        self._score_surf = None

        self._box_surf = pygame.Surface((200, 60), pygame.SRCALPHA)
        pygame.draw.rect(self._box_surf, (20, 20, 30, 180), (0, 0, 200, 60), border_radius=10)
        pygame.draw.rect(self._box_surf, (100, 150, 255), (0, 0, 200, 60), 2, border_radius=10)
        self._box_surf = self._box_surf.convert_alpha()

    def render(self, screen, score):
        if score != self._last_score:
            self._last_score = score
            self._score_surf = self.font_hud.render(f"Score: {score}", True, (100, 255, 200))
        screen.blit(self._box_surf, (10, 10))
        screen.blit(self._score_surf, (20, 20))


def _clear_global_groups():
    """Trả toàn bộ đạn/hạt còn sót về Object Pool và làm rỗng Group giữa các ván chơi."""
    for grp in (Player.projectiles, Enemy.projectiles, Projectile.particles):
        for sprite in list(grp):
            sprite.kill()
        grp.empty()


def _load_indicator_image():
    try:
        return AssetManager.get_image("indicator/indicator.png", size=(30, 30), alpha=True)
    except Exception:
        surf = pygame.Surface((10, 10), pygame.SRCALPHA)
        pygame.draw.circle(surf, (0, 255, 255), (5, 5), 4)
        return surf.convert_alpha()


def _handle_game_events(hero_sprite, game_map):
    """Xử lý sự kiện đầu vào. Trả về: None (tiếp tục), 'quit', hoặc 'menu'."""
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return "quit"
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                mx, my = pygame.mouse.get_pos()
                mouse_w = (mx + game_map.camera_offset[0], my + game_map.camera_offset[1])
                hero_sprite.pos = [float(mouse_w[0]), float(mouse_w[1])]
                hero_sprite.rect.x = int(hero_sprite.pos[0])
                hero_sprite.rect.y = int(hero_sprite.pos[1])
                hero_sprite.hitbox.centerx = hero_sprite.rect.centerx
                hero_sprite.hitbox.centery = hero_sprite.rect.centery
                hero_sprite.target_pos = None
            elif event.key == pygame.K_ESCAPE:
                return "menu"
    return None


def _rebuild_spatial_grid(grid, group):
    grid.clear()
    for sprite in group:
        grid.insert(sprite, sprite.rect)


def _update_entities(hero_sprite, enemies, orbs, game_map, enemy_grid, keys, mouse, mouse_pos, delta_time, now):
    game_map.update(mouse_pos)
    camera_offset = game_map.camera_offset

    if keys[pygame.K_1]:
        hero_sprite.equippedWeapon = hero_sprite.availableWeapons[0]
    if keys[pygame.K_2]:
        hero_sprite.equippedWeapon = hero_sprite.availableWeapons[1]
    if keys[pygame.K_3]:
        hero_sprite.equippedWeapon = hero_sprite.availableWeapons[2]

    mouse_world = (mouse_pos[0] + camera_offset[0], mouse_pos[1] + camera_offset[1])
    if mouse[2]:
        hero_sprite.target_pos = [float(mouse_world[0]), float(mouse_world[1])]
    if mouse[0]:
        hero_sprite.shoot(mouse_world, now=now)

    hero_sprite.move(game_map, map_size, delta_time, keys=keys, now=now)

    # Cập nhật Flow Field 1 lần duy nhất nếu Player đổi ô lưới (0ms khi đứng cùng ô)
    update_flow_field(hero_sprite.pos)

    _rebuild_spatial_grid(enemy_grid, enemies)
    for enemy in enemies:
        enemy.move(enemies, hero_sprite.pos, delta_time, game_map, enemy_grid=enemy_grid, now=now)
        enemy.shoot(hero_sprite.pos, now=now)

    Projectile.particles.update(delta_time, now)

    hx, hy = hero_sprite.pos[0], hero_sprite.pos[1]
    hr = hero_sprite.radius
    for orb in list(orbs):
        orb.update(delta_time)
        dx = orb.pos[0] - hx
        dy = orb.pos[1] - hy
        r_sum = orb.radius + hr
        if dx * dx + dy * dy < r_sum * r_sum:
            if hero_sprite.health < hero_sprite.max_health:
                hero_sprite.health += orb.heal_amount
                orb.kill()


def _handle_collisions(hero_sprite, enemies, bombs, orbs, enemy_grid, bomb_grid, delta_time, now, score):
    # Cập nhật lại enemy_grid sau khi enemies đã di chuyển
    _rebuild_spatial_grid(enemy_grid, enemies)

    # 1. Đạn kẻ địch vs Hero
    for proj in list(Enemy.projectiles):
        proj.move(map_size, delta_time, now=now)
        if not proj.alive():
            continue
        if pygame.sprite.collide_circle(proj, hero_sprite):
            proj.kill()
            hero_sprite.health -= 1
            if hero_sprite.health <= 0:
                hero_sprite.alive = False

    # 2. Đạn Hero vs Quái & Bom (SpatialHashGrid O(1)/viên đạn)
    bombs_changed = False
    for proj in list(Player.projectiles):
        proj.move(map_size, delta_time, now=now)
        if not proj.alive():
            continue

        proj_rect = proj.rect
        hit_enemies = [
            e for e in enemy_grid.query_rect(proj_rect)
            if e.alive() and proj_rect.colliderect(e.rect)
        ]
        if hit_enemies:
            proj.kill()
            for e in hit_enemies:
                e.health -= 1
                if e.health <= 0:
                    e.kill()
                    score += 10
                    if random.random() < 0.2:
                        orbs.add(HealthOrb(e.pos))
            continue

        hit_bombs = [
            b for b in bomb_grid.query_rect(proj_rect)
            if b.alive and proj_rect.colliderect(b.rect)
        ]
        if hit_bombs:
            proj.kill()
            for b in hit_bombs:
                b.health -= 1
                if b.health <= 0:
                    b.explode(enemies, Projectile, enemy_grid=enemy_grid, now=now)
                    b.kill()
                    bombs.add(Bomb((random.randint(100, 2300), random.randint(100, 1300))))
                    bombs_changed = True
                    if random.random() < 0.5:
                        orbs.add(HealthOrb(b.pos))

    if bombs_changed:
        _rebuild_spatial_grid(bomb_grid, bombs)

    return score


def _spawn_enemies(enemies, last_enemy_spawn, now):
    if now - last_enemy_spawn > 2000 and len(enemies) < 5:
        s_side = random.random()
        monster_class = random.choices([MonsterType1, MonsterType2], weights=[4, 1])[0]
        if s_side < 0.25:
            enemies.add(monster_class((random.randint(0, 2400), 0)))
        elif s_side < 0.5:
            enemies.add(monster_class((random.randint(0, 2400), 1440)))
        elif s_side < 0.75:
            enemies.add(monster_class((0, random.randint(0, 1440))))
        else:
            enemies.add(monster_class((2400, random.randint(0, 1440))))
        return now
    return last_enemy_spawn


def _render_world(screen, game_map, hero_sprite, enemies, bombs, orbs, indicator_img, hud, score):
    cam_x, cam_y = int(game_map.camera_offset[0]), int(game_map.camera_offset[1])
    sw, sh = screen.get_size()
    view_rect = pygame.Rect(cam_x, cam_y, sw, sh)
    blit = screen.blit

    game_map.render(screen)

    # Frustum Culling cho Particle & ExplosionSprite
    for p in Projectile.particles:
        if view_rect.colliderect(p.rect):
            blit(p.image, (p.pos[0] - cam_x, p.pos[1] - cam_y))

    for orb in orbs:
        orb.render(screen, game_map.camera_offset)
    for bomb in bombs:
        bomb.render(screen, game_map.camera_offset)

    if hero_sprite.target_pos:
        tx = int(hero_sprite.target_pos[0] - cam_x)
        ty = int(hero_sprite.target_pos[1] - cam_y)
        if -30 < tx < sw + 30 and -30 < ty < sh + 30:
            blit(indicator_img, indicator_img.get_rect(center=(tx, ty)))

    # Frustum Culling cho đạn
    for proj in Player.projectiles:
        if view_rect.colliderect(proj.rect):
            blit(proj.image, (proj.pos[0] - cam_x, proj.pos[1] - cam_y))
    for proj in Enemy.projectiles:
        if view_rect.colliderect(proj.rect):
            blit(proj.image, (proj.pos[0] - cam_x, proj.pos[1] - cam_y))

    # Frustum Culling cho quái (bỏ qua cả blit lẫn vẽ thanh máu khi ngoài khung nhìn)
    enemy_view = view_rect.inflate(60, 60)
    for e in enemies:
        if enemy_view.colliderect(e.rect):
            blit(e.image, (e.rect.x - cam_x, e.rect.y - cam_y))
            e.draw_health_bar(screen, game_map.camera_offset)

    blit(hero_sprite.image, (hero_sprite.rect.x - cam_x, hero_sprite.rect.y - cam_y))
    hero_sprite.draw_health_bar(screen, game_map.camera_offset)

    hud.render(screen, score)


# ============ MAIN MENU ============
def main_menu(screen):
    clock = pygame.time.Clock()
    click = False

    font_subtitle = AssetManager.get_font("arial", 40, bold=True)
    font_button = AssetManager.get_font("arial", 50, bold=True)
    gradient = create_gradient_surface(1200, 720, (15, 15, 35), (40, 20, 60))

    # Pre-render toàn bộ các cỡ chữ pulse (90..101) và nhãn nút tĩnh 1 lần duy nhất
    title_surfaces = {}
    for sz in range(90, 102):
        f = AssetManager.get_font("arial", sz, bold=True)
        surf = f.render("TOP DOWN SHOOTER", True, (255, 100, 150))
        title_surfaces[sz] = (surf, surf.get_rect(center=(600, 150)))

    subtitle_surf = font_subtitle.render("Battle for Survival", True, (150, 200, 255))
    subtitle_rect = subtitle_surf.get_rect(center=(600, 280))

    button_start = pygame.Rect(350, 380, 500, 80)
    button_scores = pygame.Rect(350, 500, 500, 80)
    button_quit = pygame.Rect(350, 620, 500, 80)

    lbl_start = font_button.render("START GAME", True, (255, 255, 255))
    lbl_scores = font_button.render("HIGH SCORES", True, (255, 255, 255))
    lbl_quit = font_button.render("QUIT", True, (255, 255, 255))
    lbl_start_rect = lbl_start.get_rect(center=(600, 420))
    lbl_scores_rect = lbl_scores.get_rect(center=(600, 540))
    lbl_quit_rect = lbl_quit.get_rect(center=(600, 660))

    pulse_value = 0
    while True:
        pulse_value = (pulse_value + 1) % 120
        pulse_ratio = 0.5 + 0.5 * abs(pygame.math.Vector2(1, 0).rotate(pulse_value * 3).x)

        screen.blit(gradient, (0, 0))

        now_div = pygame.time.get_ticks() // 20
        for i in range(5):
            x = (now_div + i * 100) % 1200
            y = 80 + i * 40
            pygame.draw.circle(screen, (200, 150, 255), (x, y), 2)

        title_size = int(100 * pulse_ratio * 0.1 + 90)
        t_surf, t_rect = title_surfaces[title_size]
        screen.blit(t_surf, t_rect)
        screen.blit(subtitle_surf, subtitle_rect)

        mx, my = pygame.mouse.get_pos()
        hover_start = button_start.collidepoint((mx, my))
        hover_scores = button_scores.collidepoint((mx, my))
        hover_quit = button_quit.collidepoint((mx, my))

        pygame.draw.rect(screen, (50, 200, 100) if hover_start else (30, 150, 80), button_start, border_radius=15)
        pygame.draw.rect(screen, (100, 255, 150) if hover_start else (70, 200, 120), button_start, 3, border_radius=15)
        screen.blit(lbl_start, lbl_start_rect)

        pygame.draw.rect(screen, (100, 150, 255) if hover_scores else (60, 100, 200), button_scores, border_radius=15)
        pygame.draw.rect(screen, (150, 200, 255) if hover_scores else (100, 150, 220), button_scores, 3, border_radius=15)
        screen.blit(lbl_scores, lbl_scores_rect)

        pygame.draw.rect(screen, (200, 50, 50) if hover_quit else (150, 30, 30), button_quit, border_radius=15)
        pygame.draw.rect(screen, (255, 100, 100) if hover_quit else (200, 80, 80), button_quit, 3, border_radius=15)
        screen.blit(lbl_quit, lbl_quit_rect)

        if click:
            if hover_start:
                return "start"
            if hover_scores:
                return "scores"
            if hover_quit:
                return "quit"

        click = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                click = True

        pygame.display.flip()
        clock.tick(60)


# ============ HIGH SCORES SCREEN ============
def high_scores_screen(screen):
    clock = pygame.time.Clock()
    click = False

    font_title = AssetManager.get_font("arial", 80, bold=True)
    font_score = AssetManager.get_font("arial", 40, bold=True)
    font_small = AssetManager.get_font("arial", 28)
    font_button = AssetManager.get_font("arial", 40, bold=True)

    # Pre-render toàn bộ bảng điểm tĩnh 1 lần thay vì render lại 60 FPS
    static_layer = create_gradient_surface(1200, 720, (15, 15, 35), (40, 20, 60)).copy()
    draw_text("HIGH SCORES", font_title, (255, 200, 100), static_layer, 600, 60)

    top_scores = high_score_manager.get_top_scores(10)
    if top_scores:
        y_pos = 150
        for i, entry in enumerate(top_scores):
            rank_color = (255, 215, 0) if i == 0 else (192, 192, 192) if i == 1 else (205, 127, 50) if i == 2 else (150, 150, 150)
            pygame.draw.circle(static_layer, rank_color, (100, y_pos + 25), 25)
            draw_text(str(i + 1), font_score, (255, 255, 255), static_layer, 100, y_pos + 25)
            score_text = f"{entry['name']:<15} {entry['score']:>8} pts"
            draw_text_left(score_text, font_score, (200, 255, 200), static_layer, 150, y_pos)
            draw_text_left(entry["date"], font_small, (150, 150, 150), static_layer, 150, y_pos + 45)
            y_pos += 55
    else:
        draw_text("Chưa có highscore", font_score, (200, 100, 100), static_layer, 600, 350)

    button_back = pygame.Rect(450, 650, 300, 50)
    lbl_back = font_button.render("BACK", True, (255, 255, 255))
    lbl_back_rect = lbl_back.get_rect(center=(600, 675))

    while True:
        screen.blit(static_layer, (0, 0))
        mx, my = pygame.mouse.get_pos()
        hover = button_back.collidepoint((mx, my))

        pygame.draw.rect(screen, (100, 100, 200) if hover else (60, 60, 150), button_back, border_radius=10)
        pygame.draw.rect(screen, (150, 150, 255) if hover else (100, 100, 200), button_back, 2, border_radius=10)
        screen.blit(lbl_back, lbl_back_rect)

        if click and hover:
            return

        click = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                click = True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return

        pygame.display.flip()
        clock.tick(60)


# ============ GAME OVER SCREEN ============
def game_over_screen(screen, score, is_new_highscore=False):
    clock = pygame.time.Clock()
    click = False

    font_title = AssetManager.get_font("arial", 100, bold=True)
    font_score = AssetManager.get_font("arial", 60, bold=True)
    font_normal = AssetManager.get_font("arial", 40)
    font_button = AssetManager.get_font("arial", 45, bold=True)
    font_input = AssetManager.get_font("arial", 35)

    static_layer = create_gradient_surface(1200, 720, (30, 10, 10), (60, 20, 20)).copy()
    draw_text("GAME OVER", font_title, (255, 100, 100), static_layer, 600, 100)
    draw_text(f"Your Score: {score}", font_score, (200, 255, 200), static_layer, 600, 250)
    if is_new_highscore:
        draw_text("NEW HIGH SCORE!", font_normal, (255, 215, 0), static_layer, 600, 350)
        draw_text("Enter your name:", font_normal, (255, 255, 255), static_layer, 600, 400)

    player_name = ""
    cached_name = None
    name_surf = None
    input_active = is_new_highscore
    input_rect = pygame.Rect(350, 450, 500, 60)
    button_menu = pygame.Rect(250, 600, 250, 70)
    button_quit = pygame.Rect(700, 600, 250, 70)
    lbl_menu = font_button.render("MENU", True, (255, 255, 255))
    lbl_quit = font_button.render("QUIT", True, (255, 255, 255))
    lbl_menu_rect = lbl_menu.get_rect(center=(375, 635))
    lbl_quit_rect = lbl_quit.get_rect(center=(825, 635))

    frame_count = 0
    while True:
        frame_count += 1
        screen.blit(static_layer, (0, 0))

        if is_new_highscore:
            pygame.draw.rect(screen, (100, 100, 100) if input_active else (50, 50, 50), input_rect, border_radius=10)
            pygame.draw.rect(screen, (200, 200, 200) if input_active else (100, 100, 100), input_rect, 3, border_radius=10)
            if player_name != cached_name:
                cached_name = player_name
                name_surf = font_input.render(player_name, True, (255, 255, 255))
            if input_active and (frame_count // 30) % 2:
                cursor_x = input_rect.x + 20 + name_surf.get_width()
                pygame.draw.line(screen, (200, 200, 200), (cursor_x, input_rect.y + 10), (cursor_x, input_rect.y + 50), 2)
            screen.blit(name_surf, (input_rect.x + 20, input_rect.y + 12))

        mx, my = pygame.mouse.get_pos()
        hover_menu = button_menu.collidepoint((mx, my))
        hover_quit = button_quit.collidepoint((mx, my))

        pygame.draw.rect(screen, (100, 150, 255) if hover_menu else (60, 100, 200), button_menu, border_radius=10)
        pygame.draw.rect(screen, (150, 200, 255) if hover_menu else (100, 150, 220), button_menu, 3, border_radius=10)
        screen.blit(lbl_menu, lbl_menu_rect)

        pygame.draw.rect(screen, (200, 100, 100) if hover_quit else (150, 60, 60), button_quit, border_radius=10)
        pygame.draw.rect(screen, (255, 150, 150) if hover_quit else (200, 100, 100), button_quit, 3, border_radius=10)
        screen.blit(lbl_quit, lbl_quit_rect)

        if click:
            if hover_menu:
                if is_new_highscore and player_name:
                    high_score_manager.add_score(score, player_name)
                return "menu"
            if hover_quit:
                if is_new_highscore and player_name:
                    high_score_manager.add_score(score, player_name)
                return "quit"

        click = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if is_new_highscore and player_name:
                    high_score_manager.add_score(score, player_name)
                return "quit"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                click = True
                input_active = input_rect.collidepoint(event.pos)
            if event.type == pygame.KEYDOWN and input_active:
                if event.key == pygame.K_BACKSPACE:
                    player_name = player_name[:-1]
                elif event.key == pygame.K_RETURN:
                    if player_name:
                        high_score_manager.add_score(score, player_name)
                        return "menu"
                elif len(player_name) < 15:
                    player_name += event.unicode

        pygame.display.flip()
        clock.tick(60)


# ============ GAME LOOP ============
def init_game():
    pygame.init()
    screen = pygame.display.set_mode((1200, 720))
    pygame.display.set_caption("Top Down Shooter")
    return screen


def game_loop(screen):
    _clear_global_groups()
    clock = pygame.time.Clock()
    hero = pygame.sprite.GroupSingle(Player(screen.get_size()))
    enemies = pygame.sprite.Group()
    bombs = pygame.sprite.Group()
    orbs = pygame.sprite.Group()

    score = 0
    game_map = Map(map_size)
    init_nav_grid(game_map.obstacles, hero.sprite.radius)

    enemy_grid = SpatialHashGrid(cell_size=128)
    bomb_grid = SpatialHashGrid(cell_size=128)
    for _ in range(5):
        bombs.add(Bomb((random.randint(100, 2300), random.randint(100, 1300))))
    _rebuild_spatial_grid(bomb_grid, bombs)

    hud = GameHUD()
    indicator_img = _load_indicator_image()
    last_enemy_spawn = pygame.time.get_ticks()

    try:
        while hero.sprite.alive:
            now = pygame.time.get_ticks()
            delta_time = min(clock.get_time() / 17.0, 3.0)
            keys = pygame.key.get_pressed()
            mouse = pygame.mouse.get_pressed()
            mouse_pos = pygame.mouse.get_pos()

            action = _handle_game_events(hero.sprite, game_map)
            if action == "quit":
                return score, True
            if action == "menu":
                return score, False

            _update_entities(
                hero.sprite, enemies, orbs, game_map, enemy_grid,
                keys, mouse, mouse_pos, delta_time, now
            )
            score = _handle_collisions(
                hero.sprite, enemies, bombs, orbs, enemy_grid, bomb_grid,
                delta_time, now, score
            )
            last_enemy_spawn = _spawn_enemies(enemies, last_enemy_spawn, now)

            _render_world(screen, game_map, hero.sprite, enemies, bombs, orbs, indicator_img, hud, score)
            pygame.display.flip()
            clock.tick(60)
    finally:
        _clear_global_groups()

    return score, False


# ============ MAIN (ENTRY POINT) ============
if __name__ == "__main__":
    screen = init_game()
    while True:
        result = main_menu(screen)
        if result == "quit":
            break
        elif result == "scores":
            high_scores_screen(screen)
        elif result == "start":
            score, quit_game = game_loop(screen)
            if quit_game:
                break
            is_new_highscore = high_score_manager.is_high_score(score)
            result = game_over_screen(screen, score, is_new_highscore)
            if result == "quit":
                break

    pygame.quit()
    sys.exit()
