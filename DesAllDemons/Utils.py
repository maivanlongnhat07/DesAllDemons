import math
import os
import sys
import pygame

"""
Module tiện ích (Utilities).
Cung cấp các hàm toán học 2D, bộ quản lý/cache tài nguyên (AssetManager)
và cấu trúc không gian SpatialHashGrid phục vụ truy vấn va chạm O(1).
"""


def normalize_vector(vector):
    """Chuẩn hóa vector 2D về vector đơn vị có độ lớn bằng 1."""
    x, y = vector[0], vector[1]
    if x == 0 and y == 0:
        return (0.0, 0.0)
    mag = math.hypot(x, y)
    if mag == 0.0:
        return (0.0, 0.0)
    return (x / mag, y / mag)


def rotate_vector(vector, theta):
    """Xoay vector 2D một góc theta (radian). Cache sin/cos để giảm 50% phép lượng giác."""
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    vx, vy = vector[0], vector[1]
    return (
        vx * cos_t - vy * sin_t,
        vx * sin_t + vy * cos_t,
    )


def distance(pos1, pos2):
    """Tính khoảng cách Euclidean giữa 2 tọa độ 2D."""
    return math.hypot(pos1[0] - pos2[0], pos1[1] - pos2[1])


def distance_squared(pos1, pos2):
    """Tính bình phương khoảng cách để so sánh ngưỡng mà không cần căn bậc hai."""
    dx = pos1[0] - pos2[0]
    dy = pos1[1] - pos2[1]
    return dx * dx + dy * dy


def resolve_asset_path(relative_path):
    """
    Chuẩn hóa đường dẫn tài nguyên chạy được đồng thời khi chạy source (.py)
    lẫn khi đóng gói bằng PyInstaller (--onedir / --onefile).
    Tự động tương thích đường dẫn cũ '_internal/assert/...' và mới 'assets/...'.
    """
    normalized = relative_path.replace("\\", "/")
    for prefix in ("_internal/assert/", "_internal/assets/", "assert/", "assets/"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break

    base_dirs = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_dirs.append(sys._MEIPASS)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dirs.extend([script_dir, os.getcwd()])

    candidates = []
    for base in base_dirs:
        candidates.append(os.path.join(base, "assets", normalized))
        candidates.append(os.path.join(base, "_internal", "assets", normalized))
        candidates.append(os.path.join(base, "_internal", "assert", normalized))
        candidates.append(os.path.join(base, relative_path))

    for path in candidates:
        if os.path.exists(path):
            return path
    return os.path.join(script_dir, "assets", normalized)


class AssetManager:
    """Bộ cache tập trung cho Surface ảnh (đã convert/scale) và Font chữ."""
    _image_cache = {}
    _font_cache = {}

    @classmethod
    def get_image(cls, path, size=None, alpha=True):
        """
        Tải ảnh 1 lần duy nhất, ép định dạng pixel (.convert / .convert_alpha)
        và scale sẵn theo kích thước mục tiêu rồi lưu cache.
        """
        key = (path, tuple(size) if size else None, alpha)
        cached = cls._image_cache.get(key)
        if cached is not None:
            return cached

        resolved = resolve_asset_path(path)
        raw_img = pygame.image.load(resolved)
        surface = raw_img.convert_alpha() if alpha else raw_img.convert()

        if size is not None and surface.get_size() != tuple(size):
            try:
                surface = pygame.transform.smoothscale(surface, size)
            except ValueError:
                surface = pygame.transform.scale(surface, size)
            surface = surface.convert_alpha() if alpha else surface.convert()

        cls._image_cache[key] = surface
        return surface

    @classmethod
    def get_font(cls, name, size, bold=False, italic=False):
        """Lấy Font hệ thống đã cache để tuyệt đối không gọi SysFont trong vòng lặp game."""
        key = (name, int(size), bool(bold), bool(italic))
        font = cls._font_cache.get(key)
        if font is None:
            font = pygame.font.SysFont(name, int(size), bold=bold, italic=italic)
            cls._font_cache[key] = font
        return font

    @classmethod
    def clear_cache(cls):
        """Giải phóng toàn bộ cache khi thoát hoặc nạp lại tài nguyên."""
        cls._image_cache.clear()
        cls._font_cache.clear()


class SpatialHashGrid:
    """
    Lưới băm không gian 2D (Spatial Hashing) giúp giảm truy vấn va chạm
    từ O(N * M) hoặc O(N^2) xuống gần O(1) mỗi truy vấn.
    """
    __slots__ = ("cell_size", "cells")

    def __init__(self, cell_size=128):
        self.cell_size = cell_size
        self.cells = {}

    def clear(self):
        self.cells.clear()

    def insert(self, obj, rect):
        cs = self.cell_size
        x0 = rect.left // cs
        y0 = rect.top // cs
        x1 = rect.right // cs
        y1 = rect.bottom // cs
        cells = self.cells
        if x0 == x1 and y0 == y1:
            key = (x0, y0)
            bucket = cells.get(key)
            if bucket is None:
                cells[key] = [obj]
            else:
                bucket.append(obj)
            return
        for cx in range(x0, x1 + 1):
            for cy in range(y0, y1 + 1):
                key = (cx, cy)
                bucket = cells.get(key)
                if bucket is None:
                    cells[key] = [obj]
                else:
                    bucket.append(obj)

    def insert_point(self, obj, x, y, radius):
        cs = self.cell_size
        x0 = int(x - radius) // cs
        y0 = int(y - radius) // cs
        x1 = int(x + radius) // cs
        y1 = int(y + radius) // cs
        cells = self.cells
        if x0 == x1 and y0 == y1:
            key = (x0, y0)
            bucket = cells.get(key)
            if bucket is None:
                cells[key] = [obj]
            else:
                bucket.append(obj)
            return
        for cx in range(x0, x1 + 1):
            for cy in range(y0, y1 + 1):
                key = (cx, cy)
                bucket = cells.get(key)
                if bucket is None:
                    cells[key] = [obj]
                else:
                    bucket.append(obj)

    def query_rect(self, rect):
        """Trả về các thực thể ứng viên trong các ô lưới giao với rect."""
        cs = self.cell_size
        x0 = rect.left // cs
        y0 = rect.top // cs
        x1 = rect.right // cs
        y1 = rect.bottom // cs
        cells = self.cells
        # Fast-path: thực thể nhỏ chỉ nằm gọn trong 1 ô lưới -> không cấp phát set
        if x0 == x1 and y0 == y1:
            return cells.get((x0, y0), ())

        seen = set()
        result = []
        for cx in range(x0, x1 + 1):
            for cy in range(y0, y1 + 1):
                bucket = cells.get((cx, cy))
                if bucket:
                    for obj in bucket:
                        obj_id = id(obj)
                        if obj_id not in seen:
                            seen.add(obj_id)
                            result.append(obj)
        return result

    def query_radius(self, x, y, radius):
        """Trả về các thực thể ứng viên trong vùng bao quanh hình tròn (x, y, radius)."""
        cs = self.cell_size
        x0 = int(x - radius) // cs
        y0 = int(y - radius) // cs
        x1 = int(x + radius) // cs
        y1 = int(y + radius) // cs
        cells = self.cells
        if x0 == x1 and y0 == y1:
            return cells.get((x0, y0), ())

        seen = set()
        result = []
        for cx in range(x0, x1 + 1):
            for cy in range(y0, y1 + 1):
                bucket = cells.get((cx, cy))
                if bucket:
                    for obj in bucket:
                        obj_id = id(obj)
                        if obj_id not in seen:
                            seen.add(obj_id)
                            result.append(obj)
        return result
