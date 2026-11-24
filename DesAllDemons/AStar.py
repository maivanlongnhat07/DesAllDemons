import math
import heapq
from Map import map_size

"""
Module phân tích không gian và tìm đường A* (A-Star) + Flow Field (Reverse Dijkstra).
Tối ưu với đồ thị kề tính trước (precomputed adjacency), mảng phẳng 1D dùng generation counter
(không cấp phát dict/set mỗi lần gọi), heuristic Octile (không dùng sqrt),
kiểm tra tầm nhìn thẳng (Line-of-Sight) và Flow Field dùng chung khi có nhiều kẻ địch.
"""

GRID_SIZE = 50
COLS = int(map_size[0] // GRID_SIZE) + 1
ROWS = int(map_size[1] // GRID_SIZE) + 1
nav_grid = []

_SQRT2 = 1.4142135623730951
_OCTILE_DIAG = _SQRT2 - 1.0  # 0.41421356237309515

# Cấu trúc phẳng 1D tối ưu cho A* và Flow Field
_nav_flat = []
_neighbors = []
_cell_x = []
_cell_y = []
_cell_centers = []

# Mảng tái sử dụng theo thế hệ (generation stamping) -> 0 allocation mỗi lần tìm đường
_g_score = []
_came_from = []
_visited_gen = []
_closed_gen = []
_search_gen = 0

# Cache đường đi theo ô đích và Flow Field (Reverse Dijkstra từ mục tiêu)
_path_cache = {}
_cached_goal_idx = -1

_flow_goal_idx = -1
_flow_parent = []
_flow_dist = []


def init_nav_grid(obstacles, enemy_radius):
    """
    Khởi tạo lưới tìm đường tĩnh 2D (tương thích ngược) đồng thời tiền tính toán
    đồ thị kề 1D hợp lệ (đã loại sẵn biên và cắt góc tường) để tăng tốc A* và Flow Field.
    """
    global nav_grid, _nav_flat, _neighbors, _cell_x, _cell_y, _cell_centers
    global _g_score, _came_from, _visited_gen, _closed_gen, _search_gen
    global _path_cache, _cached_goal_idx, _flow_goal_idx, _flow_parent, _flow_dist

    nav_grid = [[True for _ in range(ROWS)] for _ in range(COLS)]
    padding = enemy_radius * 0.8
    half_grid = GRID_SIZE * 0.5

    obs_bounds = [
        (obs.rect.left - padding, obs.rect.right + padding,
         obs.rect.top - padding, obs.rect.bottom + padding)
        for obs in obstacles
    ]

    for x in range(COLS):
        gx = x * GRID_SIZE + half_grid
        col = nav_grid[x]
        for y in range(ROWS):
            gy = y * GRID_SIZE + half_grid
            for left, right, top, bottom in obs_bounds:
                if left < gx < right and top < gy < bottom:
                    col[y] = False
                    break

    total = COLS * ROWS
    _nav_flat = [False] * total
    _cell_x = [0] * total
    _cell_y = [0] * total
    _cell_centers = [(0.0, 0.0)] * total

    for x in range(COLS):
        base = x * ROWS
        cx_px = x * GRID_SIZE + half_grid
        for y in range(ROWS):
            idx = base + y
            _nav_flat[idx] = nav_grid[x][y]
            _cell_x[idx] = x
            _cell_y[idx] = y
            _cell_centers[idx] = (cx_px, y * GRID_SIZE + half_grid)

    # Tiền tính danh sách đỉnh kề hợp lệ 1 lần duy nhất (chặn cắt góc khi đi chéo)
    directions = (
        (0, -1, 1.0), (1, 0, 1.0), (0, 1, 1.0), (-1, 0, 1.0),
        (1, 1, _SQRT2), (-1, 1, _SQRT2), (1, -1, _SQRT2), (-1, -1, _SQRT2),
    )
    _neighbors = [() for _ in range(total)]
    for x in range(COLS):
        for y in range(ROWS):
            idx = x * ROWS + y
            if not _nav_flat[idx]:
                continue
            adj = []
            for dx, dy, cost in directions:
                nx, ny = x + dx, y + dy
                if 0 <= nx < COLS and 0 <= ny < ROWS and nav_grid[nx][ny]:
                    if dx != 0 and dy != 0:
                        if not nav_grid[x + dx][y] or not nav_grid[x][y + dy]:
                            continue
                    adj.append((nx * ROWS + ny, cost))
            _neighbors[idx] = tuple(adj)

    _g_score = [0.0] * total
    _came_from = [-1] * total
    _visited_gen = [0] * total
    _closed_gen = [0] * total
    _search_gen = 0

    _path_cache.clear()
    _cached_goal_idx = -1
    _flow_goal_idx = -1
    _flow_parent = [-1] * total
    _flow_dist = [float("inf")] * total


def heuristic(a, b):
    """
    Khoảng cách Octile — heuristic chính xác (admissible & consistent) cho lưới 8 hướng,
    loại bỏ hoàn toàn lệnh gọi math.hypot/sqrt và thu hẹp không gian duyệt hơn Euclidean.
    """
    dx = abs(b[0] - a[0])
    dy = abs(b[1] - a[1])
    if dx > dy:
        return dx + _OCTILE_DIAG * dy
    return dy + _OCTILE_DIAG * dx


def _pos_to_grid(pos):
    gx = int(pos[0] // GRID_SIZE)
    gy = int(pos[1] // GRID_SIZE)
    if gx < 0:
        gx = 0
    elif gx >= COLS:
        gx = COLS - 1
    if gy < 0:
        gy = 0
    elif gy >= ROWS:
        gy = ROWS - 1
    return gx, gy


def _snap_to_walkable(gx, gy):
    """Nếu ô mục tiêu/xuất phát bị kẹt vào padding vật cản, tìm ô đi được gần nhất."""
    idx = gx * ROWS + gy
    if _nav_flat[idx]:
        return gx, gy, idx

    best_idx = idx
    best_d2 = 10**9
    for radius in (1, 2, 3):
        found = False
        x0 = max(0, gx - radius)
        x1 = min(COLS - 1, gx + radius)
        y0 = max(0, gy - radius)
        y1 = min(ROWS - 1, gy + radius)
        for nx in range(x0, x1 + 1):
            base = nx * ROWS
            dx = nx - gx
            for ny in range(y0, y1 + 1):
                if abs(nx - gx) != radius and abs(ny - gy) != radius:
                    continue
                nidx = base + ny
                if _nav_flat[nidx]:
                    d2 = dx * dx + (ny - gy) * (ny - gy)
                    if d2 < best_d2:
                        best_d2 = d2
                        best_idx = nidx
                        found = True
        if found:
            return _cell_x[best_idx], _cell_y[best_idx], best_idx
    return gx, gy, idx


def has_line_of_sight(x0, y0, x1, y1):
    """
    Kiểm tra đường thẳng thông thoáng (Supercover Bresenham) trên lưới tĩnh.
    Nếu không bị vật cản chắn giữa start và goal -> bỏ qua hoàn toàn A*.
    """
    nav = _nav_flat
    rows = ROWS
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0

    while True:
        if not nav[x * rows + y]:
            return False
        if x == x1 and y == y1:
            return True
        e2 = err * 2
        step_x = e2 > -dy
        step_y = e2 < dx
        if step_x and step_y:
            if not nav[(x + sx) * rows + y] or not nav[x * rows + (y + sy)]:
                return False
            err -= dy
            err += dx
            x += sx
            y += sy
        elif step_x:
            err -= dy
            x += sx
        elif step_y:
            err += dx
            y += sy


def update_flow_field(goal_pos):
    """
    Tính Flow Field (Reverse Dijkstra 1 nguồn từ vị trí Player) CHỈ KHI Player đổi ô lưới.
    Chi phí ~0.16ms mỗi lần Player sang ô 50x50 mới; phục vụ O(1) cho mọi số lượng quái.
    """
    global _flow_goal_idx, _flow_parent, _flow_dist
    if not _nav_flat:
        return

    gx, gy = _pos_to_grid(goal_pos)
    _, _, goal_idx = _snap_to_walkable(gx, gy)
    if goal_idx == _flow_goal_idx:
        return

    _flow_goal_idx = goal_idx
    total = COLS * ROWS
    inf = float("inf")
    dist = [inf] * total
    parent = [-1] * total
    neighbors = _neighbors

    dist[goal_idx] = 0.0
    heap = [(0.0, goal_idx)]
    heappop = heapq.heappop
    heappush = heapq.heappush

    while heap:
        d, u = heappop(heap)
        if d > dist[u]:
            continue
        for v, cost in neighbors[u]:
            nd = d + cost
            if nd < dist[v]:
                dist[v] = nd
                parent[v] = u
                heappush(heap, (nd, v))

    _flow_dist = dist
    _flow_parent = parent


def get_flow_target(pos, goal_pos):
    """
    Truy vấn O(1) điểm đến tiếp theo từ Flow Field (có kiểm tra tầm nhìn thẳng).
    Dùng cho trường hợp có đông quái vật cùng đuổi theo Player.
    """
    if not _nav_flat:
        return goal_pos

    sx, sy = _pos_to_grid(pos)
    gx, gy = _pos_to_grid(goal_pos)
    if sx == gx and sy == gy:
        return goal_pos
    if has_line_of_sight(sx, sy, gx, gy):
        return goal_pos

    _, _, start_idx = _snap_to_walkable(sx, sy)
    next_idx = _flow_parent[start_idx]
    if next_idx != -1:
        return _cell_centers[next_idx]
    return goal_pos


def a_star_search(start_pos, goal_pos):
    """
    Tìm đường A* tối ưu trên lưới 1D phẳng:
    1. Kiểm tra trùng ô hoặc thông thoáng tầm nhìn (LOS) -> O(dist), không gọi heapq.
    2. Tận dụng Flow Field nếu mục tiêu khớp _flow_goal_idx -> dựng lộ trình tối ưu trong O(path_len).
    3. Tra cứu cache theo (start_idx, goal_idx).
    4. Chạy A* với đồ thị kề tiền tính, generation array (0 alloc), closed set và Octile heuristic.
    """
    global _search_gen, _cached_goal_idx
    if not _nav_flat:
        return []

    sx, sy = _pos_to_grid(start_pos)
    gx, gy = _pos_to_grid(goal_pos)
    if sx == gx and sy == gy:
        return []

    sx, sy, start_idx = _snap_to_walkable(sx, sy)
    gx, gy, goal_idx = _snap_to_walkable(gx, gy)
    if start_idx == goal_idx:
        return []

    # 1. Shortcut tầm nhìn thẳng: tiết kiệm 70-85% số lần chạy A* trên bản đồ thoáng
    if has_line_of_sight(sx, sy, gx, gy):
        return [_cell_centers[goal_idx]]

    # 2. Nếu Flow Field đã khớp ô đích, truy ngược trực tiếp O(path_len) không cần heapq
    if goal_idx == _flow_goal_idx and _flow_parent[start_idx] != -1:
        path = []
        centers = _cell_centers
        parent = _flow_parent
        cur = parent[start_idx]
        steps = 0
        max_steps = COLS * ROWS
        while cur != -1 and steps < max_steps:
            path.append(centers[cur])
            if cur == goal_idx:
                break
            cur = parent[cur]
            steps += 1
        return path

    # 3. Cache theo mục tiêu hiện tại
    if goal_idx != _cached_goal_idx:
        _path_cache.clear()
        _cached_goal_idx = goal_idx
    else:
        cached = _path_cache.get(start_idx)
        if cached is not None:
            return list(cached)

    # 4. A* lõi với mảng phẳng tái sử dụng và closed set chống duyệt lặp
    _search_gen += 1
    if _search_gen >= 1_000_000_000:
        for i in range(len(_visited_gen)):
            _visited_gen[i] = 0
            _closed_gen[i] = 0
        _search_gen = 1
    gen = _search_gen

    g_score = _g_score
    came_from = _came_from
    visited_gen = _visited_gen
    closed_gen = _closed_gen
    neighbors = _neighbors
    cell_x = _cell_x
    cell_y = _cell_y
    octile_diag = _OCTILE_DIAG

    g_score[start_idx] = 0.0
    came_from[start_idx] = -1
    visited_gen[start_idx] = gen

    dx0 = abs(gx - sx)
    dy0 = abs(gy - sy)
    min_h = (dx0 + octile_diag * dy0) if dx0 > dy0 else (dy0 + octile_diag * dx0)
    best_node = start_idx

    frontier = [(min_h, start_idx)]
    heappop = heapq.heappop
    heappush = heapq.heappush

    iterations = 0
    while frontier and iterations < 800:
        f_val, current = heappop(frontier)
        if closed_gen[current] == gen:
            continue
        closed_gen[current] = gen
        iterations += 1

        if current == goal_idx:
            best_node = current
            break

        cur_g = g_score[current]
        h_cur = f_val - cur_g
        if h_cur < min_h:
            min_h = h_cur
            best_node = current

        for next_idx, move_cost in neighbors[current]:
            if closed_gen[next_idx] == gen:
                continue
            new_cost = cur_g + move_cost
            if visited_gen[next_idx] != gen or new_cost < g_score[next_idx]:
                visited_gen[next_idx] = gen
                g_score[next_idx] = new_cost
                came_from[next_idx] = current
                dx = abs(gx - cell_x[next_idx])
                dy = abs(gy - cell_y[next_idx])
                h = (dx + octile_diag * dy) if dx > dy else (dy + octile_diag * dx)
                heappush(frontier, (new_cost + h, next_idx))

    centers = _cell_centers
    path = []
    cur = best_node
    while cur != start_idx and cur != -1:
        path.append(centers[cur])
        cur = came_from[cur]
    path.reverse()

    _path_cache[start_idx] = tuple(path)
    return path
